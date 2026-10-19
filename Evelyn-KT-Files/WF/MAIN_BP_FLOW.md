# Names Screening — Main BP Execution Order

Step order of the main **Names Screening** BP.
Captured from the WorkFusion flow diagram (project.xml is XML-escaped mxGraph — node order in the file is NOT execution order; this is the real flow). Keep this updated instead of re-deriving from the zip.

> Source of truth = the BP diagram. If you change the BP, update this file.

## Top-level flow

```
Start
  → input-task-processor
  → [Screening System? gateway — routes by provider id]
        CSV            → csv-schema-producer-processor
        Firco Trust    → Firco Trust Screening (subprocess)
        Dow Jones      → factiva-task-processor
        World Check One→ world-check-one-task-processor
        Thomson Reuters→ Thomson Reuters Provider (subprocess:
                          thomson-reuters-data-prepare → TR sub-process exec
                          → reformat-tr-results → thomson-reuters-response)
  → Screening Systems (subprocess, provider-specific inner steps)
  → [Validate WLE? gateway]
        WLEs Found      → Data Enrichment (subprocess)
                          → Names Classification Model (subprocess)
                          → alert-report-processor
        empty / WLE List Empty → alert-report-processor (skips enrichment + model)
  → [Validate WLE? gateway (again)]
        WLEs Found      → select-for-manual-review-processor
                          → [Manual Review? gateway]
                                Yes → Human-in-the-loop (subprocess)
                                No  → screening-system-report-processor
        WLE List Empty  → screening-system-report-processor
  → screening-system-report-processor
  → html-report-processor
  → finish-transaction-processor        ← sets THIS transaction status = COMPLETED
  → select-master-record-processor      ← first tx to run this wins the master flag
  → [Master transaction? gateway]       ← ONLY a "Yes" outcome — there is NO "No" edge
        Yes → wait-for-completion-processor   ← polls (reprocessAfter 120s) until
                                                 all txns COMPLETED/ERROR
            → [Automatic report? gateway]
                  No (automatic_report EQ false) → send-results-back-to-caller-processor
                  unconditional → Qc Report Sub-process   ← synchronous BP call (qc-signal-id)
                                  (runs the "Names Screening QC Report" BP = qc-report,
                                   aggregates ALL completed txns for the run)
                                → send-results-back-to-caller-processor
            → send-results-back-to-caller-processor   ← @SendResultToCaller step
            → purge-datastore-processor               ← FINAL step
            → Final Results (end)
```

Tail verified from the XML edges, in both `4.4.0-obp-test-dev` and `4.3.0`. Node ids:
- 555 select-master → 437 "Master transaction?" — its **only** edge goes to 556 wait-for-completion.
- 556 → 589 "Automatic report?" — goes to 587 directly (outcome "No"), or to 594 "Qc Report Sub-process" (CallActivity), which then goes to 587.
- 587 send-results-back-to-caller → 559 purge-datastore → 38 Final Results. Node 38 is the only top-level End.

Gateway 437's rule does have a "send unprocessed result to unconditional outcome(s)" clause, but there is no unconditional edge. So **non-master transactions never reach send-results-back-to-caller, purge-datastore or Final Results.** What the platform does with a record that matches no outcome has not been checked at runtime.

Older versions of this note named the step `api-response-processor` and drew a "No → api-response" edge. Neither exists in the BP.

## Subprocess inner steps

**Names Classification Model:**
```
Start → prepare-for-ml-processor → Execute AutoML Model:Bridge → save-model-results-processor → end
```
(Max Data Pairs Drools rule routes oversized alerts straight to save-model-results, skipping AutoML — see CLAUDE.md invariant.)

**Names Screening Human-in-the-loop** (see [MANUAL_TASK.md](MANUAL_TASK.md) for the full manual-task knowledge):
```
Start → prepare-data-for-manual-review-processor
      → HumanTask "Name Screening Manual Review" (WorkFusion Workspace)
      → reformat-mt-results-processor
      → save-manual-review-results-processor → end
```

**Data Enrichment:**
```
Start → ticker-lookup-task-processor
      → [Location Enrichment? gateway] yes → Location Enrichment (subprocess) ; no → skip
      → custom-configuration-task-processor
      → [Custom Enrichment? gateway] no_code → end ; (No Code Rule branch: false positive / sync_trigger sub-process)
      → end
```

## Key ordering facts that matter for bugs

- **`finish-transaction` runs BEFORE `select-master-record`** — every transaction (including the eventual master) is set COMPLETED before master selection.
- **`qc-report` runs only on the master transaction**, after `wait-for-completion`, inside the synchronous "Qc Report Sub-process". It is skipped when `automatic_report=false` (`csv.enable` AND `csv.automatic_generation`, set by `WaitForCompletionProcessor`). `wait-for-completion` passes `bp_uuid`, which makes `ReadContext.isAutomatic=true`. The report reads COMPLETED transactions for that BP whose `extRecordId` matches `request_id` (a blank id matches all of them). The master transaction UUID is only the file timestamp (`findMasterTransactionDate`), not a row filter.
- **Master selection** (`SelectMasterRecordProcessor`): for CSV, the first transaction to insert a `MasterRecord(bpRunId, extRecordId)` row wins (DB unique constraint; `MasterRecordRepositoryService.save` returns false on `DataIntegrityViolationException`). For REST, master = true when a request id is present.
- **`wait-for-completion` gate** (`WaitForCompletionProcessor.areThereTransactionsInProgress`): counts transactions of the run NOT IN (COMPLETED, ERROR) via `countByBpRunUuidAndExtRecordIdAndStatusIsNotIn(bpRunId, extRecordId,...)`. ERROR counts as "done". The query filters `t.extRecordId = :extRecordId`.
- **CSV `extRecordId` = the record's `request_id`** (`CsvSchemaProducerProcessor` line 48, `orElse(StringUtils.EMPTY)`).
  - On the CSV File Ingestion path it is **never empty**: `csv-task` always sets `request_id` (`CsvTaskProcessor` lines 55-61, 74).
  - It uses the data file name when `configuration.keep_input_file_name_for_qc_report` is true, and a random UUID otherwise.
  - Seen on dw-dev2: `request_id = nss_test_data_…`.
  - Every row of one file shares that one id.
- Read side: `TransactionService.findAllByBpRunUuidAndStatusAndExtRecordId` falls back to the no-extRecordId `findAllByBpRunUuidAndStatus` when extRecordId is empty.
- `ConfigurationUtil.getRestRequestIdIfPresent` returns `request_id`, or else `_sys_ext_record_id`, or else `""`. It **never returns null**; EXPERT-35283 (`a07c38a21`) added the `orElse(StringUtils.EMPTY)`. So the old "null param never matches `""` rows" asymmetry in `countByBpRunUuidAndExtRecordIdAndStatusIsNotIn` no longer applies.

## CSV File Ingestion BP (the parent that calls this BP for CSV)

`CSV+File+Ingestion+_v_*.zip`, verified in `4.4.0-obp-test-dev`, identical in `4.3.0` and `4.4.0-dev`:

```
Start → csv-monitor-task → csv-task → [Should proceed?]
      → Yes: ProcessCall "NSS-main-BP" (node 4) → Final Results
      → No:  Final Results
```

- **The call to this BP is ASYNC.** The ProcessCall is `BP_CALL`, template "Asynchronous Sub-process Execution", with config `<signalId>nss-signal-id</signalId><synchronous>false</synchronous>`.
- **So the NSS-main-BP step in the CSV run gets no Names Screening fields back.** In Control Tower, its results show only `screened_data`, `request_id` and `wle_list` (the csv-task output) plus the platform's `_sys_record_order`. See "How results reach a caller" below for why.
- The BP is `SCHEMA_LESS`. Its End node does `export include-original-data="true"` with `_sys_export_columns` unset, so no field filtering happens anywhere.
- CSV results are delivered by the HTML report and the QC report CSV on S3, plus the datastore and analytics. They never come back to the CSV parent.
- The integration tests read the **child** Names Screening run (`NssE2EExtension.waitForFinalResults` → `QC_REPORTS`). On the CSV run they only wait for `csv-task`.
- To see what Names Screening produced for a CSV run, open the child NSS-main-BP run itself: its `send-results-back-to-caller` step, for the master row only.

## How results reach a caller (`@SendResultToCaller`)

**The flag.** `@SendResultToCaller(true)` comes from `jnw-toolkit-common-annotations`. It emits `<sendResultToCaller>true</sendResultToCaller>` into the generated task XML, and it appears in the step's java config inside the BP.
- In the main BP only `send-results-back-to-caller` carries it.
- `qc-report` carries it too, but it runs inside the separate QC Report BP. That BP hands `qc_reports` back to the main BP through the synchronous "Qc Report Sub-process" call.

**What Control Tower does with it.** Read from bytecode of `com.freedomoss.crowdcontrol:*:10.3.3.4-SNAPSHOT` (no sources available). The deployed CT version was not checked.
- A flagged step's output is handed to the run's external record: a REST request, or a parent BP's ProcessCall. It fires only if the run has `_sys_ext_record_id`.
  - Synchronous caller (`SYNC_SUBMITTED`): the result is sent to the reply queue, then the record becomes `SYNC_RESULT_SENT`.
  - Async caller (`ASYNC_IN_PROGRESS`): the result is only stored (`ASYNC_COMPLETED`), never pushed.
  - Only the **first** flagged step's result is delivered; later ones hit `handleResultAlreadySent`.
- How the parent receives a ProcessCall result:
  - **Sync:** the parent step waits for the result. The child's data is copied back with `_sys*` keys dropped, then laid over the parent's record.
  - **Async:** the child immediately replies "Record Processing Started". The parent step completes with an **empty** result, so its output = its own input (`BridgeResultConverter.createStepOut` starts from `new HashMap(stepInput)`).

**Who calls this BP how:**

| Caller | Call | What the caller gets |
|---|---|---|
| REST (Postman/cURL) sync | REST connector | `rest_response` (sanitized `AlertResponse`) |
| OBP Test BP | ProcessCall `nss-signal-id-obp`, `synchronous=true` | the step's output, minus `_sys*` |
| CSV File Ingestion | ProcessCall `nss-signal-id`, `synchronous=false` | nothing; the step output = the CSV record it sent |

**What the processor replies** (`SendResultsBackToCallerProcessor`):
- `shouldRun` requires a non-empty `request_id` / `_sys_ext_record_id` and **no** `rest_response` yet.
- `no_alerts` → "No messages."
- `is_internal_request=true` and the provider is not Firco → typed fields: `wle_list`, `screened_data`, `alert_decision`, `auto_qc`, `html_report_link`, `qc_reports`.
  - `csv-schema-producer` sets `is_internal_request=true` for CSV, because there is no `rest_request`.
- Firco → report links.
- Otherwise → external `rest_response` + `transaction_id`.

For CSV the processor does build the typed reply, but only the master row reaches it (gateway 437), and the async parent never receives it. So switching the CSV call to synchronous would **not** return one decision per row, and might stall the parent. This has not been tested.
