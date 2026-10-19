# Names Screening — Manual Task (Human-in-the-Loop)

How Evelyn (the NSS Digital Worker) sends alerts to a human reviewer in WorkFusion Workspace, and how the review result flows back into the transaction.

"Manual task" = a WorkFusion **HumanTask** step inside the main Names Screening BP. It is NOT a separate BP — it lives in the **"Names Screening Human-in-the-loop"** subprocess of `Names+Screening+_v_*.zip`. None of the other BP zips (CSV File Ingestion, QC Report, Ticker Lookup, Aggregated Analytics) contain a human task or any MT processor. TR Ongoing Monitoring was removed in EXPERT-39627.

> Cross-references: overall BP order in [MAIN_BP_FLOW.md](MAIN_BP_FLOW.md), auto-QC selection in [QC_AUTOQC.md](QC_AUTOQC.md).

---

## 1. When does Evelyn trigger a manual task?

Two gates must both pass:

**Gate 1 — WLEs found.** The `Validate WLE?` gateway routes to `select-for-manual-review-processor` only when the alert has watchlist entities. A no-hit transaction can never produce a manual task.

**Gate 2 — `SelectForManualReviewProcessor` says yes.**

| `manualTask.criteria` | Result |
|---|---|
| `DISABLE_ALL` (default) | MT only if the *request* carries `mt_force=true` in its per-request `configuration` map (REST callers can force a review even when MT is globally off) |
| `ENABLE_ALL` | Always MT |
| `ENABLE_FP` / `ENABLE_NMI` | Fall through to the qualification checks below |

Qualification checks for `ENABLE_FP` / `ENABLE_NMI` (first match wins):
1. Alert category in `manualTask.enable_alert_category` → **MT**
2. Alert category in `manualTask.disable_alert_category` → **no MT**
3. `manualTask.enable_auto_qc` is true AND the alert was selected for auto-QC (`auto_qc` flag set earlier by `AlertReportProcessor` via `AutoQcService`) → **MT**
4. Otherwise match the alert resolution against the criteria:
   - `ENABLE_FP` + resolution `ALL_FP` → MT
   - `ENABLE_NMI` + resolution `NEED_REVIEW` → MT
   - anything else → no MT

The BP gateway is a Drools rule named **"Manual Review?"**: `mt_review EQ "true"` → Yes branch (Human-in-the-loop subprocess); No branch goes straight to `screening-system-report-processor`.

### Configuration surface

| Path | UI label | Notes |
|---|---|---|
| `manualTask.criteria` | Human-in-the-loop (radio) | `ENABLE_ALL` / `ENABLE_NMI` / `ENABLE_FP` / `DISABLE_ALL`; default `DISABLE_ALL` (also in `configuration_payload.json`) |
| `manualTask.enable_alert_category` | Enable for the following alert categories | tags; only shown for FP/NMI criteria |
| `manualTask.disable_alert_category` | Disable for the following alert categories | tags; only shown for FP/NMI criteria |
| `manualTask.enable_auto_qc` | Should alerts flagged for auto QC also be sent to human-in-the-loop? | default `true`; only shown when auto-QC enabled and criteria is FP/NMI |

Per-request overrides (REST `configuration` map on the screening request): `mt_force`, `mt_title`, `mt_assignee`, `mt_priority`. Any other keys in the map are passed through to the human task as data-map attributes.

---

## 2. The Human-in-the-loop subprocess (BP wiring)

```
select-for-manual-review-processor          (writes mt_review)
  → [Manual Review? rule: mt_review == "true"]
       No  → screening-system-report-processor
       Yes → Names Screening Human-in-the-loop (subprocess):
               prepare-data-for-manual-review-processor
               → HumanTask "Name Screening Manual Review v<ver>"   ← the actual manual task
               → reformat-mt-results-processor
               → save-manual-review-results-processor
             → screening-system-report-processor                    (rejoins main flow)
```

Captured from the BP diagram in `Names+Screening+_v_3.10.0-dev.zip` (node ids: 547 select, 429 rule, 464 subprocess, 548 prepare, 562 human task, 549 reformat, 550 save).

### Processors involved (complete list)

| Processor id | Class | Role |
|---|---|---|
| `select-for-manual-review-task` | `SelectForManualReviewProcessor` | Decides `mt_review` true/false (section 1) |
| `prepare-data-for-manual-review` | `PrepareDataForManualReviewProcessor` | Builds `ManualTaskDto` JSON (`data_on_review`), sets hit statuses to `TO_REVIEW`, sets MT title/assignee/priority attributes, marks request `READY_FOR_MT`, stamps analytics `mt_review_start` |
| — (human task, not a processor) | HumanTask "Name Screening Manual Review" | WorkFusion Workspace task rendering the React review UI |
| `reformat-mt-results` | `ReformatMtResultsProcessor` | Type-restoration shim: human task output returns everything as strings; converts `transaction_id` back to UUID, re-emits `request_id` / `provider_id` |
| `save-manual-review-results` | `SaveManualReviewResultsProcessor` | Parses `data_on_review_output`, applies reviewer decisions to `AlertDecision`/`WleDecision`s, recomputes alert resolution, writes analytics + `MT_COMPLETED` status |

Supporting classes: `ManualTaskData` (builds columns/input/hits from `rules.configured_fields`), `IdentifiersMapper`, `AdditionalInformationMapper`, `ManualTaskUtil` (Workspace assignment link), `VersionService` (platform 10.2.8 output quirk), and DTOs under `task/mt/dto/`.

---

## 3. Data contract between worker and human task

| Key | Direction | Content |
|---|---|---|
| `mt_review` | select → gateway | `"true"` / `"false"` |
| `data_on_review` | prepare → human task | JSON-serialized `ManualTaskDto` — everything the reviewer sees |
| `data_on_review_output` | human task → save | Same `ManualTaskDto` shape with reviewer's decisions filled in |
| `_sys_mt_hit_title` | prepare → platform | Task title: `mt_title` request override, else the screened name |
| `_sys_mt_hit_assignee` | prepare → platform | From `mt_assignee` request override |
| `_sys_mt_hit_priority` | prepare → platform | Integer, from `mt_priority` request override |
| `unique_case_id` | prepare → platform | = transaction UUID; used by the Workspace assignment-link filter |
| `worker_id`, `worker_first_name`, `worker_last_name` | human task → save | Injected by the platform; who reviewed |

`ManualTaskDto` (JSON): `columns` (set of column descriptors driven by `rules.configured_fields`), `input` (screened record as key/value), `hits` (per-WLE: `id`, `uuid`, `fields`, `resolution`), `resolution_input_details` (alert-level explanation), `resolution_hit_show_confidence`.

- `resolution_hit_decision` — Evelyn's original decision; `resolution_hit_review_decision` — the human's decision. **0 = False Positive, 1 = More Information Needed** (`WleDecisionUtils.getResolutionFromMtResponse`).
- `resolution_hit_review_status` — `TO_REVIEW` / `SKIPPED` / `REVIEWED`. Only `REVIEWED` hits overwrite the WLE resolution/explanation; `SKIPPED` keeps Evelyn's decision but still counts its original decision toward the alert rollup.
- Alert rollup after review (`AlertDecisionService.getAlertResolution`): any NMI count > 0 (or filtered transaction) → `NEED_REVIEW`, else `ALL_FP`. If the reviewer changed a decision but left the explanation untouched, a canned explanation is generated instead (`ExplanationConstants.HIT_FALSE_POSITIVE` / `HIT_NOT_ENOUGH_INFORMATION`).

---

## 4. The review UI — `names-screening-mt` module

The human task template is Freemarker with an empty `<div id="nss-mt-app">` plus the bundled `nss-dw-mt.js`. That JS is the React app `nss-dw-mt`, built by `frontend-maven-plugin` (`yarn build`).

Binding to the WorkFusion form is DOM-based:
- On load, the layout reads the hidden `data_on_review` answer field.
- On submit, the footer writes JSON into the `data_on_review_output` field, then the standard WF form submit fires.

Modules: `Layout`, `HitsList`, `Hit`, `Footer`; components `CircleChart` (confidence), `DecisionIcon`, `EvaluationChip`.

---

## 5. REST caller integration & status tracking

- `prepare-data-for-manual-review` sets status **`READY_FOR_MT`** with a deep link to the Workspace assignment: `<workspace_url>/workspace/assignments?sortBy=CREATED_DATE&attr[Unique Case ID]=<transactionId>` (`ManualTaskUtil.getAssignmentLink`).
- The Workspace base URL comes from the **secure vault entry aliased `workspace_url`** (`InputParameters.MANUAL_TASK_VAULT_ALIAS`). Missing vault entry → status `ERROR` with message "Secure vault entry workspace_url is missing…" (screening still proceeds; only the link is lost).
- `save-manual-review-results` sets status **`MT_COMPLETED`**. Final `FINISHED` comes later from the normal report/response path.

Platform-version quirk: `VersionService` calls `<workspace_url>/actuator/info`; on WF **10.2.8** the prepare processor writes output attributes with `putString` instead of `putValue` (typed values broke the 10.2.8 human task). Unreachable/missing URL defaults to the 10.2.9+ path.

---

## 6. Analytics

Alert analytics table (`ds_uc_B_AML_PEP_alert_analytics_v3_0`, migration `040_add_mt_start_end_time.yaml`) carries `mt_review_start` / `mt_review_complete` (indexed):
- `prepare-data-for-manual-review` → `AnalyticsService.updateMtStartTime`
- `save-manual-review-results` → `updateHitReviewDecision` (per REVIEWED hit) and `updateAlertReviewDecision` (alert level), both recording reviewer decision, explanation, worker id and full name, and stamping completion time.

`manualReviewStatus` (`TO_REVIEW`/`SKIPPED`/`REVIEWED`) also flows into the QC report schema — see the WLE decision schema in the BP contracts.

---

## 7. Testing

- Fixtures under `mt-steps/` simulate the human step: `data_review_response.json`, `data_review_multiple_FP.json`, `data_review_multiple_NMI.json` are ready-made `data_on_review_output` payloads.
- The MT UI has its own Jest suite (`yarn build-test` via the `run-frontend-tests` maven execution; skip with `-DskipFrontEndTests`).

---

## Gotchas

- **`manualTask.criteria` default is `DISABLE_ALL`** — a fresh deployment never creates manual tasks unless configured or the request sends `mt_force=true`.
- **`DISABLE_ALL` + `mt_force` still works** — "disable in all cases" disables *criteria-based* selection only; the force flag is checked inside the `DISABLE_ALL` branch.
- **Category lists beat everything except ENABLE_ALL/DISABLE_ALL** — an alert whose category is in `disable_alert_category` skips MT even if auto-QC selected it.
- **Human task output is untyped** — that's the whole reason `reformat-mt-results` exists; don't remove it when touching the subprocess.
- **`SKIPPED` hits are not neutral** — their original `resolution_hit_decision` still feeds `needMoreInformationCount`, so a skipped NMI hit keeps the alert at `NEED_REVIEW`.
- MT processors follow the JNW rule: no `@Transactional` on processors; DB work goes through services (`AnalyticsService`, `RequestStatusService`).
