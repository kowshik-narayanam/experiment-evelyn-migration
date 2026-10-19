# Evelyn → UiPath: head start

- **Paths:** `names-screening/…` is the Evelyn repo at
  `NSS/names-screening-copy/names-screening`, branch `master` @ `6dcf7f9d3`.
  `UiPath-WorkFusion/…` is the migration repo. In §3, paths with no
  prefix are in `UiPath-WorkFusion/` too.
- **Status:** no Evelyn port exists, and no file in either repo says one is planned. Everything
  under "likely shape" is **Inference** from how the other ports were done.
- **Method:** read-only. Nothing was changed or run in either repo.

## 1. Evelyn at a glance

- **What:** "WorkFusion Names Sanctions Screening Digital Worker" (`com.workfusion.dw:names-screening`),
  use case `B-AML-PEP`, version `4.4.0-dev` (`names-screening/pom.xml:9,17-18`). It automates
  AML/PEP sanctions-screening alert adjudication:
  - ingest alerts from watchlist providers;
  - enrich them;
  - score each alert-vs-watchlist-entry (WLE) pair with an ML model;
  - route ambiguous cases to human reviewers;
  - emit HTML/CSV reports and analytics (`names-screening/CLAUDE.md:7-11`).
- **Tech:** Java 21, Spring Boot 3.5, Maven. It has 10 modules (`names-screening/pom.xml:132-141`)
  and 547 Java files. The work is done by 33 `@TaskProcessor` classes on a template-method base,
  `NSSTaskProcessor` (`names-screening/CLAUDE.md:38`).
- **Flow** (`names-screening/CLAUDE.md:53-66`):

  ```
  input-task / csv-task / firco-messages-batch                       (ingest)
    → factiva-task / world-check-one-task / thomson-reuters-*        (provider search)
    → address-lookup-* / ticker-lookup-* / custom-configuration-task (enrich)
    → prepare-for-ml-task → save-model-results-task                  (ML scoring)
    → select-for-manual-review-task
    → prepare-data-for-manual-review → save-manual-review-results    (human loop)
    → html-report-task / alert-report-task / qc-report / screening-system-report
    → finish-transaction / send-results-back-to-caller
  ```

- **Ships as a WorkFusion asset bundle** (`names-screening/names-screening-package/src/main/resources/`):
  - 5 business-process zips: Names Screening, CSV File Ingestion, Name Screening Ticker Lookup,
    Names Screening QC Report, and Aggregated Analytics Data Ingestion;
  - `configuration.json`, `configuration_payload.json` and `meta-info.json`;
  - 4 Superset dashboards (`analytics/superset_assets/` in that folder);
  - the datastore migrations and a pointer to the ML model.
- **Providers:**
  - Factiva, from Dow Jones (`factiva-connector`, with an optional database search cache);
  - World-Check One, from Refinitiv (`wc1-connector`, over the `world-check-one` client jar);
  - Firco Trust (`names-screening-firco-trust-connector`, over the `fircosoft-trust` SOAP client jar).
    Evelyn polls the client's Firco Trust Case Manager API and writes decisions back to it. The
    format files only map columns. ; see
    [evelyn-helper-repos.md](evelyn-helper-repos.md);
  - Thomson Reuters (`thomson-reuters-*` tasks; it has no module of its own).

  Credentials come from Vault through `SecretService`.
- **ML model:** `nss-classification-model-v5.3.0` (`names-screening/pom.xml:21`), downloaded from
  S3 at package time (`names-screening/names-screening-package/pom.xml:19`). It is an AutoML model run through
  WorkFusion's Python Bridge (entrypoint `nss_model.app`). Its contract: read
  `data.{input, hits[], configuration}` and return one decision per hit
  (`UiPath-WorkFusion/Isaac/docs/isaac-anatomy.md:703-729`).
- **Data:** MSSQL through Spring Data JPA (H2 in tests).
  - 24 numbered Liquibase migrations (`030`–`046`) plus seed CSVs live in
    `names-screening/names-screening-package/src/main/resources/datastore/migrations/`.
  - Key entities include `Transaction`, `MasterRecord`, the Factiva caches, the Firco message and
    retry tables, alert and hit analytics, `Configuration`, `Ticker`, `QcReportData` and
    `RequestStatus`.
- **Contract:** `nss_schema.yaml` is not in the repo. The build unpacks it from the artifact
  `com.workfusion.dw:names-screening-contract` 4.2.0 (`names-screening/names-screening-schema/pom.xml:117-119,169`).
  The separate `evelyn-nss-api` 4.2.0 dependency (`pom.xml:36`) holds only Java classes.
  Local copies already exist on this machine, in
  `names-screening/names-screening-schema/target/generated-resources/contracts/nss_schema.yaml` and
  `the local Maven cache com/workfusion/dw/names-screening-contract/4.2.0/`. Each processor also has
  in/out contracts in
  `names-screening/names-screening-jnw/src/main/resources/configs/main/`.
- **Entry modes:**
  - business process to business process, returning full data including the watchlist entries;
  - external HTTP clients through WorkFusion's REST input connector (1.0.17), returning a
    sanitized response
    (`names-screening/names-screening-jnw/src/main/java/com/workfusion/dw/nss/task/report/SendResultsBackToCallerProcessor.java:73-84`);
  - CSV batches, and Firco messages polled from the client's case manager.
- **Around it:** a React manual-task UI `nss-dw-mt` (module `names-screening-mt`), Elastic APM,
  and configuration through Zookeeper and Vault. CI is Bitbucket Pipelines (build, bundle import,
  integration, performance and regression tests, Sonar); Jenkins does the bundle deploys.
- **Compliance-sensitive code** (`names-screening/CLAUDE.md:168-177`): `MultiFactorScoringService`,
  `nss/task/ml/`, `ThresholdConfiguration`, `RulesConfiguration`, `nss/utils/validation/rules/`,
  `AlertDecisionService` and `AutoQcService`. These decide whether an alert is auto-cleared or
  escalated, so a port must reproduce them exactly.

## 2. What UiPath-WorkFusion already did with Evelyn

In short: **WorkFusion Isaac never called Evelyn.** The Isaac team briefly wired Evelyn in by
mistake and then took it out. There is no Evelyn integration to build on.

| Date | What happened | Evidence |
|---|---|---|
| | The Isaac team designed Evan and Evelyn provider subflows. Under the heading "Evelyn is active; Evan is dormant", they mapped the counterparty-classification service that WorkFusion Isaac registers (`VERTEXAI`) to Evelyn. They wrote that Evelyn "supplies classification, screening, risk, and resolved-name data", and they built an HTTP adapter for Evelyn's `evelynbw` endpoint | `UiPath-WorkFusion/Isaac/docs/superpowers/specs/-evan-evelyn-counterparty-enrichment-design.md:40,64,117`; commits `1af0a022` to `7b16d071` |
| | A live run reached the real Evelyn service: authentication worked, HTTP 200, `IN_PROGRESS`. Then Evelyn's 30-second UiPath Flow timer never resumed, and the parent Flow stayed `Running` with no incident. They put it down to the UiPath Flow runtime, not Evelyn | `UiPath-WorkFusion/Isaac/docs/evan-evelyn-orchestration-incident-.md:5-11` |
| | Evelyn was replaced with a mock | commits `8d107ac4`, `e1dd44a8` |
| | Reconciled to the WorkFusion baseline: its only active service is `vertexAI` (OrgClas), and it has "no Evelyn invocation". The Evelyn API and Flow were replaced by OrgClas ones, "instead of treating Organisation Classification as an Evelyn call" | `UiPath-WorkFusion/Isaac/docs/superpowers/specs/-baseline-external-model-reconciliation-design.md:11-14,31-34`; `UiPath-WorkFusion/Isaac/evidence/external-adapter-contracts.md:17-18` |
| 08-12, re-checked 08-26 | `nss-classification-model` (Evelyn's model) was assessed as the OrgClas provider and rejected, because it classifies screening hits, a different contract | `UiPath-WorkFusion/Isaac/docs/isaac-anatomy.md:703-729`; `UiPath-WorkFusion/Isaac/IsaacUiPath/README.md:57-60` |

**Leftovers:**
- `FccEvelynScreeningBatchApi` in the old `UiPath-WorkFusion/Isaac/POC/AMLRulesIntegrationShadowCandidate/`.
- An `evan-evelyn-model` adapter binding in
  `UiPath-WorkFusion/Isaac/evidence/config-profiles/verapont-reference.json:93`.
- `nss-classification-model` listed as ruled out in
  `UiPath-WorkFusion/shared/config/workfusion-repositories.json:22`.

**Check:** WorkFusion's Isaac source in `UiPath-WorkFusion/Isaac/workfusion-code-ref/` has no
names-screening calls. The only "Evelyn" hit is in a data file of resolved counterparty names
(`…/transaction_analysis/mitigation/data/resolved_counterparties.json`).

**Useful by-products:**
- A WorkFusion Evelyn endpoint was reachable from a UiPath tenant on `alpha.uipath.com` in August
  (the job links in the 08-08 incident report).
- Evelyn's own contract and model were read and documented by the Isaac team.
- The Flow-timer hang is a known UiPath platform issue: see Isaac's D32 in
  `UiPath-WorkFusion/Isaac/docs/live-run-report.md:164-193`.

## 3. Likely UiPath shape (Inference)

| Evelyn piece | Closest precedent in UiPath-WorkFusion | Likely UiPath shape | Precedent? |
|---|---|---|---|
| 33 task processors, 547 Java files | Every Function there is Java translated to Python, e.g. Evan's `operation` dispatcher (`Evan/EvanUiPath/EvanAmmFunction/entrypoints.py`) | Python coded Function(s) | Yes, but Evelyn is large |
| 5 business processes | Isaac: 10 WorkFusion business processes became 15 Maestro Flows | Maestro Flows | Yes |
| Called by another worker, full response | Isaac starts each provider as an Orchestrator job and polls it (`Isaac/IsaacUiPath/IsaacWorkflowFunctions/isaac_workflow/provider_jobs.py:23-24`) | Evelyn Flow started as a job | Yes |
| Called by external HTTP clients, sanitized response | None: OWS removed its HTTP façade | An API trigger or the job-start API (open question) | **No** |
| CSV batches | `IsaacFlow` sweeps an input bucket | Bucket drop plus a time trigger | Partly |
| Firco: SOAP polling of the client's case manager, with status write-back | None: no SOAP client in UiPath-WorkFusion | Time or API trigger, plus a function that polls and writes back ([evelyn-helper-repos.md](evelyn-helper-repos.md)) | **No** |
| Factiva, World-Check One, Firco Trust, Thomson Reuters; Vault | Evan and OWS: Python HTTP clients plus Secret assets | One client per provider | Yes; licences and rate limits are the risk |
| `nss-classification-model` 5.3.0 (AutoML) | Evan and OrgClas: model files in a bucket, run in a Python 3.11 child process | Same | Yes; size and memory unknown |
| MSSQL, 24 migrations, about 10 key entities | OrgClas uses one Data Fabric entity as a cache; Isaac dropped Data Fabric (`Isaac/docs/isaac-anatomy.md:3878-3890`) | Data Fabric tables or an external database | **No, not at this scale.** The biggest design decision |
| React manual-review UI `nss-dw-mt` | Isaac's `ActionTaskApp` in Action Center; Evan never ported its manual review | Coded action app (screens and mapping: [§11](#11-frontend-the-nss-dw-mt-review-ui-and-the-other-screens)) | Partly |
| HTML, CSV and QC reports | Evan moved FreeMarker templates to Jinja, written to a bucket | Same | Yes |
| 4 Superset dashboards | None | Unknown | **No** |
| `configuration.json` / `configuration_payload.json` | `EvanConfigurationApp` replaced WorkFusion's Form.io page | Config app plus a JSON file in a bucket (size: [§11.5](#115-other-ui-surfaces)) | Yes |
| `nss_schema.yaml` contract | OrgClas and Isaac contract tests against WorkFusion schemas | Contract tests on the same spec | Yes |
| JUnit, integration and Cypress tests | Evan's `Evan/tests/wf_parity/`: WorkFusion tests ported with WorkFusion's expected values | Same; the integration tests are natural sources of reference cases | Yes |
| Bitbucket Pipelines and Jenkins | `pipelines/evan-deploy.yml` | An `evelyn-deploy.yml` | Yes |

### 3.1 Entry points (draft, Inference)

. Evelyn lines are from `master` (`git show master:<path>`). "Entry point" means
two things in UiPath, and Evelyn needs both.

**The code entry point: one `main`, many operations.** This is the pattern of
 and of Isaac's
`IsaacWorkflowFunctions`, which fits about 70 operations behind one `main`. Evelyn's 33
`@TaskProcessor` classes become operations:

| Evelyn processor (WorkFusion) | UiPath |
|---|---|
| `input-task`, `csv-task`, `firco-messages-batch` | `operation: "input"`, `"csv"`, `"firco-batch"` |
| `factiva-task`, `world-check-one-task` | `"factiva-search"`, `"wc1-screen"` |
| `prepare-for-ml-task` → `save-model-results-task` | Probably a **separate** function project, because the ML model needs a bigger robot. Evan split out `EvanScoreFunction` for the same reason |
| `send-results-back-to-caller` | `"send-results"` |

So probably 2–3 function projects, grouped by what they need to run (plain code vs the model), not 33.

**The Flow entry points: how work gets in.** Today the main BP listens on signal `nss-signal-id`,
and work arrives through four channels. UiPath has no signal ids, so each channel gets its own way in:

```
External HTTP client ── API trigger (AsyncRequestReply) ──► EvelynRestFlow ──┐
Another worker (Isaac, Edward…) ── processes.invoke + poll ──────────────────┤
CSV file in a bucket ── time trigger ──► EvelynCsvFlow ── one job per alert ─┤
Firco TCMAPI ◄── SOAP poll ── time trigger ──► EvelynFircoFlow ── per message ┤
                                                                              ▼
                     EvelynScreeningFlow  (the main BP: "Names Screening")
       input → provider search → enrich → ML → manual review? → reports → send results
```

| Channel | WorkFusion today | UiPath | Precedent |
|---|---|---|---|
| Another worker | `BP_CALL` to `nss-signal-id` | Start the Flow's process by name and poll the job | Isaac → Evan, OWS, OrgClas (`Isaac/IsaacUiPath/IsaacWorkflowFunctions/isaac_workflow/provider_jobs.py:23-24`) |
| External REST | `start-record-raw/{signalId}` → status → result | **API trigger**, AsyncRequestReply mode: 202 and a status URL, then a 303 redirect to the output | **None.** Every port's Flow uses a manual trigger ([equivalent.md §4](equivalent.md#4-input-channels)) |
| CSV batch | CSV File Ingestion BP → async `BP_CALL` per alert | Input bucket, plus a sweep function on a time trigger | `IsaacFlow` sweeps its bucket |
| Firco | `download-firco-messages` polls the client's case manager | Time trigger, plus a function that polls over SOAP | None |

**Carry over exactly: the channel decides internal vs external.** Evelyn never trusts the caller on
this (`names-screening/names-screening-jnw/…/task/input/InputTaskProcessor.java:70`):

```java
boolean isInternalRequest = !input.getData().containsKey(RestRequest.REQUEST_FIELD_NAME);
```

- Internal callers get the full answer, including the watchlist entries. External callers get a
  sanitized one (`SendResultsBackToCallerProcessor.java:73-84`).
- In UiPath, give each channel a **thin entry Flow** that sets `internal_request` itself and then
  calls the shared core Flow. Never trust a body field like `"is_internal_request": true`; Example
  10's "Try this 2" shows the hole.
- Precedent:
  - WorkFusion itself: the CSV BP calls the main BP.
  - Isaac: two entry Flows, `IsaacFlow` and `IsaacRestFlow`, feed the same chain
    (`Isaac/docs/input-modes-and-entry-point-parity.md`).
- `input-task` already branches by channel today: `shouldRun` is false for the Firco and CSV
  providers (`InputTaskProcessor.java:60-65`). In UiPath that branch moves into which entry Flow
  started the run.

**What the core Flow carries from its first node.** These are `input-task`'s outputs
(`InputTaskProcessor.java:75-86`):

| Field | Note |
|---|---|
| `transaction_id` | Every later step carries it (45 of the 52 step contracts) |
| `screened_data`, `wle_list`, `wle_count` | Large alerts go as a bucket path instead (the claim-check, Example 6) |
| `configuration` | Per-request settings, e.g. `mt_force` |
| `internal_request` | Set by the entry Flow, never by the caller |
| `request_id` | Only when the caller sent one |
| `provider_id`, `location_enrichment_enabled` | Added in `afterRunning` (`:91-97`) |

**Open questions that decide the shape** (numbers from §7):

| Question | Why it matters |
|---|---|
| Standalone worker or provider? (§7 Q2) | As a provider, "another worker" may be the only entry point |
| Is the external HTTP mode needed? (§7 Q7) | If yes, Evelyn is the first port with an API trigger |
| One job per alert, or batches? | A function that loads the ML model starts slowly; OrgClas batches with `classify-batch` |

## 4. The hard parts

1. **Where the data lives.** Evelyn is stateful: caches, analytics, QC data and request status in
   MSSQL. No port so far has moved a relational store this size. OrgClas uses a single Data Fabric
   cache table.
2. **Several entry channels.** The external HTTP mode has no UiPath precedent in this repo.
3. **Four external providers.** Each needs UiPath-side credentials, vendor terms that allow the new
   host, and rate-limit handling. Evan's Google rate limits cost Isaac run 62 about 35 minutes
   (`UiPath-WorkFusion/Isaac/docs/live-run-report.md:80`).
4. **Model hosting.** The model's size and memory needs are unknown, and they decide the robot size.
   1 GB robots die with no error; OrgClas needs 4 GB and Evan about 5.2 GB.
5. **Exact scoring parity.** The compliance-sensitive classes above make decision-level parity
   non-negotiable.
6. **Volume against job start-up.** Each job pays about 50 s of cold start, so work must be batched
   per job, as OrgClas does with `classify-batch`
   (`UiPath-WorkFusion/OrganisationClassification/OrganisationClassificationUiPath/README.md:624-635`).
7. **Human review and analytics.** Both have only partial precedent (Action Center) or none
   (Superset).

## 5. Lessons from the other ports

- **Don't wait inside Flow timers.** Long Maestro waits can hang with no error: Evelyn's own 08-08
  incident, and Isaac's D32. Poll inside Functions.
- **Batch per job,** because of the ~50 s cold start.
- **Size the robot from measured memory,** not guesses.
- **Deploy gotchas:**
  - A deploy can reset Secret assets to `<unset>`.
  - An unpinned `uip` CLI upgrade once broke 10 of 15 Isaac flows.
  - Studio debug runs execute in your personal workspace folder
    (`UiPath-WorkFusion/IDP/AGENTS.md:100-106`).
- **Capture WorkFusion reference outputs on day one.** OWS and EDE skipped this and can't claim
  parity.
- **Measure performance early.** Performance is the stated reason for these migrations, yet OWS
  still takes 5m 8s against WorkFusion's ~20s.
- **Keep the AI guide current.** Stale `AGENTS.md` files are a recurring problem in
  UiPath-WorkFusion.

## 6. Prep checklist (Evelyn side, read-only)

- [ ] **Contract:** read `nss_schema.yaml` (local copies above) and the per-processor contracts.
- [ ] **Business processes:** list the steps and gates in the 5 zips. Isaac's graph tests compared
      its Flows against these archives.
- [ ] **Reference cases:** real WorkFusion request/response pairs for each channel (REST, CSV,
      Firco), from a shared dev environment. Isaac's skill
      `UiPath-WorkFusion/.claude/skills/start-isaac-investigation/SKILL.md` shows how that team
      produced WorkFusion reference runs.
- [ ] **Model facts:** zip size, Python version and dependencies, memory at inference.
- [ ] **Providers:** which accounts are in scope, their terms for automated or cloud use, and their
      rate limits.
- [ ] **Data:** which tables hold real state and which are caches or analytics, plus the retention
      and purge rules (`purge-datastore-task`).
- [ ] **Tests:** which unit and integration tests have fixed expected values and could become
      ported parity tests, like Evan's `UiPath-WorkFusion/Evan/tests/wf_parity/`.
- [ ] **Configuration:** what `configuration.json` and `configuration_payload.json` control.

## 7. Questions for leads

1. Why Evelyn, and what is the driver (customer, performance, platform)?
2. A standalone port like Isaac, or a provider called by another worker?
3. Which Evelyn version is the baseline: `master` 4.4.0-dev or a release tag?
4. Where will the code live? Inference: a new `Evelyn/` domain in UiPath-WorkFusion would match the
   others.
5. Which providers are in scope, and do UiPath-side accounts exist?
6. Where does the data go: Data Fabric, an external database, or buckets?
7. Is the external HTTP client mode needed on UiPath? If so, how will callers reach it?
8. Is Action Center acceptable for manual review, and who are the reviewers?
9. Should the Superset dashboards be ported, replaced or dropped?
10. Which tenant and environments? Only a staging dev tenant exists today.
11. What counts as parity: identical decisions on reference sets, and what tolerance on model scores?

## 8. Read first in UiPath-WorkFusion

1. : the closest precedent (Java worker, model,
   providers, reports, config app).
2. The OrgClas harness, the template for starting a port:
   ,
   
   and .
3. The three Evelyn documents in §2.
4. : the platform rules.

## 9. Notes on the Evelyn repo (observations only)

- `names-screening/README.md:32` links to `names-screening-bcbs/…`, which is not on `master` and is
  not a module in `pom.xml`.
- A porter needs Maven access to private WorkFusion repositories, or the local copies above, to get
  `nss_schema.yaml`.
- Evelyn's `CLAUDE.md` guardrails (compliance-sensitive code, no shared-environment deploys) already
  suit an AI-driven port. They would carry over to a UiPath-side `AGENTS.md`.
- Jira: both teams use the EXPERT project (Evelyn `EXPERT-39711`; Evan's restructure
  `EXPERT-39741`), so the port tickets are searchable there.

## 10. UiPath onboarding courses

The course list Cosmin Popescu gave the Isaac onboarding group, in Slack `#sw-isaac-onboarding`
(`C0BR086P58S`, message ts `1787063918.582789`). The Academy course pages were read on
 and open without a login, but they show only the overview, objectives and module list.
The lessons need an Academy login. Total is about 20h45m, or 20h without the optional course.

| # | Course | Level · time | Covers |
|---|---|---|---|
| 1 | [Get started with UiPath Studio Web](https://academy.uipath.com/courses/get-started-with-uipath-studio-web) | Beginner · 2h20 | Studio Web interface, variables, debugging, Autopilot, publishing. Start here. |
| 2 | [Unified Build tech updates (L200)](https://academy.uipath.com/courses/uipath-unified-build-technical-updates-october-2025-l200) | Advanced · 35m | Multi-project Solutions, shared Resources, cross-project debugging, packaging and deploy |
| 3 | [The UiPath Maestro collection](https://academy.uipath.com/learning-plans/the-uipath-maestro-collection) | Learning plan · 6h55 | BPMN intro, process implementation, updates, operations, monitoring, Case Management |
| 4 | [Platform tech updates (L200)](https://academy.uipath.com/courses/uipath-platform-technical-updates-july-2026-l200) | Advanced · 1h35 | The Flow course: Flow vs. BPMN, Flow Public Preview, Maestro Case, Coding Agents, Data Fabric Case entities |
| 5 | [Maestro: Process monitoring](https://academy.uipath.com/courses/uipath-maestro-process-monitoring) | Advanced · 25m | Monitoring view, metrics, alerts. Also inside #3. |
| 6 | [API Workflows technical overview (L200)](https://academy.uipath.com/courses/uipath-api-workflows-technical-overview-l200) | Advanced · 1h | What API Workflows are; build, publish, test; calling external APIs |
| 7 | [Get started with API Workflows](https://academy.uipath.com/courses/get-started-with-api-workflows) | Intermediate · 1h15 | Hands-on: JavaScript/JSON transforms, schema-validated endpoints |
| 8 | [Data Fabric technical overview (L200)](https://academy.uipath.com/courses/uipath-data-fabric-technical-overview-l200) | Advanced · 1h | Entities (data models), using them from automations, schema across environments |
| 9 | [Orchestrator overview for developers (v2024.10)](https://academy.uipath.com/courses/orchestrator-overview-for-automation-developers-v2024-10) | Intermediate · 1h35 | Tenants vs. folders, unattended robots, jobs, licensing |
| 10 | [Working with Orchestrator resources](https://academy.uipath.com/courses/working-with-orchestrator-resources-as-an-automation-developer) | Intermediate · 2h05 | Libraries, storage buckets, queues, transaction types. Take #9 first. |
| 11 | [Orchestrator triggers and monitoring (v2024.10)](https://academy.uipath.com/courses/orchestrator-triggers-and-monitoring-v2024-10) | Optional · 50m | Triggers, SLAs, job priorities, monitoring dashboards |
| 12 | [UiPath Coded Apps](https://academy.uipath.com/courses/uipath-coded-apps) | Intermediate · 1h35 | React/TypeScript apps on the UiPath TypeScript SDK |
| 13 | Docs: [coded functions](https://uipath.github.io/uipath-python/core/functions/), [Studio Web](https://uipath.github.io/uipath-python/core/studio_web/), [uipath-python](https://uipath.github.io/uipath-python/) | No course | Typed Python run as Orchestrator jobs; `uipath new/init/run/pack/publish/push/pull` |

- There is no dedicated Flow course yet; #4 is the stand-in.
- #7's page lists "API Workflows Technical *Updates* " as its prerequisite, not #6.
  Probably the same course (**Inference**).
- The same evening Cosmin Sandu posted the Isaac solution archive (`IsaacUiPathNew.uis`), a video on
  importing it into Studio Web, and an invite to the staging org `uipathstgss_updated`. He advised
  doing the courses first.

## 11. Frontend: the `nss-dw-mt` review UI and the other screens

. Why it matters: the migration needs React/TypeScript only at the human-review
boundary. The four Coded Apps in `UiPath-WorkFusion` (`EvanConfigurationApp`, `IsaacWorkspace`,
`IsaacConfigurationApp`, `ActionTaskApp`) are React + TypeScript + Vite + Tailwind on
`@uipath/uipath-typescript`; the agent logic itself stays Python. The GitHub org `UiPath` has 10 TypeScript repos and 5 JavaScript
ones (all archived), by primary language only ().

- **Paths:** `mt/…` is `names-screening/names-screening-mt/src/main/…`. A path with no prefix, such
  as `modules/Hit/…` or `store/epics/epics.js`, is under `mt/src/`.
- **Method:** read-only. The local Evelyn copy was on branch
  `bugfix/EXPERT-39666-fix-qc-reports-overwriting-310` @ `709318dcb`, not `master`.
  The React `mt/src/`, `mt/public/`, `mt/src/temp/` and both manual-review contracts are identical
  to `master` @ `6dcf7f9d3` (`git diff master HEAD` is empty). Facts from the files that differ
  (`mt/package.json`, `mt/pom.xml`, `configuration.json`, the package assembly, the Cypress tests)
  were re-read with `git show master:<path>`, and the numbers below are `master`'s.

### 11.1 Screens

There is no router. `mt/src/modules/Layout/Layout.view.jsx:40` swaps between two screens on
`isHitPage`, and the footer changes with the screen. Two screens, seven components (three on the
summary, four on the hit page).

| # | Screen | What the reviewer sees and does | Source |
|---|---|---|---|
| 1 | **Summary** (hits list) | The "Screening: *name*" card with the input fields. A "Search Results (N)" table: a to-review dot, the display columns, a confidence %, an evaluation chip. A row click opens the hit. | `modules/HitsList/`: `InputCard.view.jsx:7-27`, `List.view.jsx:19-91` |
| 1b | Summary footer | An editable "Alert decision explanation" textarea and a **Finish review** button | `modules/Footer/components/Submit/Submit.view.jsx:16-55` |
| 2 | **Hit evaluation** | A back arrow with the hit title. A Screened / Hit / Details table with collapsible categories, match and mismatch highlighting, "missing data" and "n/a". A circle chart with the overall matching score. A radio: False Positive or Need More Information. An editable "Hit decision explanation" textarea. | `modules/Hit/`: `Matches.view.jsx:11-137`, `Evaluate.view.jsx:14-113`, `Header.view.jsx:7-18` |
| 2b | Hit footer | "Reviewing hits N of M", Cancel & Back to summary, Back, and Submit & Review next hit (Submit & Back to summary on the last one) | `modules/Footer/components/HitNav/HitNav.view.jsx:8-57` |

Shared components: `EvaluationChip`, `DecisionIcon`, `CircleChart`. Every button, table, chip, icon
and input comes from private `@wf/*` packages (`mt/package.json:9-15`). **Inference:** nothing in
the UiPath repos replaces them, so those widgets are rebuilt in the Coded App.

### 11.2 Behaviour to carry over

| Rule | Where |
|---|---|
| Hits sort by decision, highest first, so Need More Information (1) comes before False Positive (0). The sort runs at start, and again on return to the summary only after a submit (the `needToSortHits` flag). | `util/sortHits.js:3-9`, `store/epics/epics.js:21-47`, `HitNav.container.jsx:40,44` |
| Review status goes `TO_REVIEW` → `REVIEWED` on submit and `SKIPPED` on cancel or back | `epics.js:50-67` |
| The effective decision is the reviewer's, or the engine's if there is none | `Evaluate.container.jsx:29-31` |
| A `WS/INIT` message with `submitPermission: false` hides every submit button (read-only mode) | `Layout.view.jsx:11-15,41` |
| Confidence shows only when `resolution_hit_show_confidence` is true | `modules/HitsList/components/List/List.view.jsx:31,66`, `Evaluate.view.jsx:26` |

### 11.3 Data contract

| Direction | Mechanism | Shape |
|---|---|---|
| **In** | Hidden input `[id$="data_on_review"]`, parsed at `Layout.view.jsx:26` | `{hits, input, columns, resolution_hit_show_confidence, resolution_input_details}` (`epics.js:24-31`). Each hit has `fields[id] = {value, match, details}` and a `resolution` object with five `resolution_hit_*` keys (`constant/columns.js`). Each column has `id`, `title`, `category_title`, `display_main`. |
| **Out** | Writes JSON into hidden input `[id$="data_on_review_output"]`, then clicks WorkFusion's `.submit-btn` (`Submit.container.jsx:25-32`) | `{resolution_input_details, hits: [{id, uuid, resolution}]}`. Only `resolution` goes back, not the field data. |

On the Java side (`names-screening/names-screening-jnw/src/main/resources/configs/main/`):

- Task `prepare-data-for-manual-review` produces `data_on_review` plus `_sys_mt_hit_title`,
  `_sys_mt_hit_assignee`, `_sys_mt_hit_priority` and `alert_decision`
  (`prepare-data-for-manual-review-processor.out-contract.yaml`).
- Task `save-manual-review-results` consumes `data_on_review_output`, `alert_decision`,
  `transaction_id` and the `worker_*` fields (`save-manual-review-results-processor.in-contract.yaml`).
- Upstream, `select-for-manual-review-task` decides which alerts reach a person
  (`ProcessingAttributes.MT_REVIEW`).

### 11.4 Mapping to UiPath

| WorkFusion | UiPath | Evidence |
|---|---|---|
| Manual task template `nss-dw-mt` | A **Coded Action App**, as in Isaac's `ActionTaskApp` | `UiPath-WorkFusion/Isaac/IsaacUiPath/ActionTaskApp/source/package.json` depends on `@uipath/coded-action-app` |
| Reading hidden input `data_on_review` | `new CodedActionApp().getTask()`, then `task.data` | `…/ActionTaskApp/source/src/tasks/useActionAppTaskHost.ts:43,59,142` |
| Hidden output input plus `.submit-btn` click | `completeTask(action, data)` | `useActionAppTaskHost.ts:106` |
| `WS/INIT` `submitPermission` | `task.isReadOnly` and `task.status` | `useActionAppTaskHost.ts:152` |
| `prepare-data-for-manual-review` and `save-manual-review-results` bot steps | **Inference:** function nodes before and after the human-task node in a Flow | not verified |

### 11.5 Other UI surfaces

| Item | What it is | Port impact |
|---|---|---|
| **Configuration wizard** | Declarative `names-screening-package/src/main/resources/configuration.json` (about 150 KB, `"display": "wizard"`), rendered by the WorkFusion platform; I found no React source for it (**Inference:** Form.io-style, like the page `EvanConfigurationApp` replaced). Five panels: Input (~44 fields), Enrichment (~16), Model (~36), Human In the Loop (~33), Output (~30). About 159 in all, counted as JSON objects with a `key` and a `type`, so it includes nested layout components. | **Inference:** needs a Coded App like `EvanConfigurationApp` and `IsaacConfigurationApp`. Likely the biggest frontend piece. |
| **Cypress UI tests** | `names-screening-integration-tests/src/test/cypress/ui/` (`ConfigurationForm`, `HumanInTheLoopStep`, `ModelStep`, `ScreeningSystemOptions`) drive the wizard through `src/main/cypress/forms/configuration.html`. They do not test the review UI. | Natural source of reference cases for a config app |
| **Search form macro** | `mt/src/temp/resources/template/macro/nss-use-case-search-mt.js` (92 lines of jQuery, toggles Person and Entity fields) with `nss-use-case-search-mt.css`, plus `Search for Name Screening.zip` (2020). Tracked in git. | Unknown whether it is used: `names-screening-package/assembly/names-screening-package.xml:17-19` ships only `dist/nss-dw-mt.js` |

### 11.6 Gotchas

- **The dev harness is stale.** `mt/public/index.html` holds a flat sample payload
  (`input_full_name`, `resolution_matrix_decision`, …) that does not match the
  `{hits, input, columns}` the code reads. **Inference:** `yarn start` will not render the real
  UI. For a real payload, start from `PrepareDataForManualReviewProcessorIT.java` in
  `names-screening-jnw` (not read).
- **The reducers mutate state in place** (`reducers.js:65-80`). Do not carry that into a React
  hook rewrite.
- **Old stack:** React 16 with react-dom 17 (`mt/package.json:19-20`), `ReactDOM.render`
  (`mt/src/index.js:7`), Redux plus redux-observable for 14 actions (`store/actions/actions.js`), and a build pinned to
  Node v18.18.0 (`mt/pom.xml:20`). **Recommendation:** rewrite on React 19 with `useReducer`
  rather than port Redux and the epics.
- **Tests:** Jest and Testing Library, 80% coverage gate (`mt/package.json:84`). There are tests
  for Layout, List, Evaluate, Header, HitNav, Submit, the store and the utils, but **none for
  `Matches` or `InputCard`**. `Matches.container.jsx:19-101` holds the category grouping, the most
  intricate logic, so write parity cases for it first.
- **Generated:** `mt/dist/` and `mt/coverage/` are gitignored output. `mt/src/` is the source.

### 11.7 Open questions

| Question | Why it matters |
|---|---|
| Is `nss-dw-mt` the only manual-task UI? | The repo shows no other: `TypeConfirmationConfiguration` is a config-path enum, not a screen. Confirm with the team. |
| Is the 2020 search form macro still used? | If yes, it is a third screen |
| Is the configuration wizard rebuilt as a Coded App, or replaced by Flow inputs? | It decides the size of the frontend work. Ties to §7 Q8. |
