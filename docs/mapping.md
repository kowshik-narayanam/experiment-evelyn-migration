# Mapping: Evelyn's CSV path to UiPath (first slice)

Phase 0, 2026-10-16. Read-only work: files and `git` only, nothing ran on a tenant.
The choices behind this mapping, and the open questions, are in [decisions.md](decisions.md).

## 0. Sources and how to check a citation

| Alias | Path | Snapshot read |
|---|---|---|
| `E` | `/Users/knarayanam/WorkfusionRepos/NSS/names-screening` | `master` @ `fa168ccb2` (2026-10-16). No tracked file is modified. Untracked local files are marked *(untracked)* when cited |
| `J` | `E/names-screening-jnw/src/main/java/com/workfusion/dw/nss` | |
| `JT` | `E/names-screening-jnw/src/test/java/com/workfusion/dw/nss` | |
| `JR` | `E/names-screening-jnw/src/main/resources` | |
| `IT` | `E/names-screening-integration-tests/src/test/java/com/workfusion/dw/nss` (end-to-end tests) | |
| `C` | `E/names-screening-core/src/main/java/com/workfusion/dw/nss/core` | |
| `S` | `E/names-screening-schema/src/main/java/com/workfusion/dw/nss` | |
| `M` | `E/names-screening-package/src/main/resources/datastore/migrations` | |
| `P` | `E/names-screening-package/src/main/resources` | |
| `CSVBP`, `MAINBP` | `project.xml` inside `P/business-process/CSV+File+Ingestion+_v_4.5.0-dev.zip` and `Names+Screening+_v_4.5.0-dev.zip` | line numbers of the raw `project.xml` |
| `K` | `/Users/knarayanam/WorkfusionRepos/NSS/names-screening-contract` | `ffc12d6`, branch `feature/EXPERT-39840-update-schema-to-support-original-txn-uuid` |
| `SIM` | `/Users/knarayanam/UiPathRepos/Evelyn Simulation` | `8cc114a` plus uncommitted edits |
| `W` | `/Users/knarayanam/UiPathRepos/UiPath-WorkFusion` (another team's port, read-only) | `1b2dc9f4` (2026-10-15) |
| `L` | `/Users/knarayanam/UiPathRepos/learning` (your notes) | |
| `SDK` | `uipath` 2.14.27 as installed in `SIM/Datastore Simulation/DatastoreSim/DatastoreSimFunction/.venv`, folder `site-packages/uipath/platform` | |
| `CLI` | `/opt/homebrew/lib/node_modules/@uipath/maestro-tool/dist` | `uip` 1.203.0 |
| `SKILL` | `~/.claude/plugins/cache/uipath-marketplace/uipath/1.203.1/skills/uipath-maestro-flow/references` | the UiPath Flow skill |

A citation is `ALIAS:path:LINE` “fragment”, and the fragment is copied from that line (or from a line in a cited
range). Every citation in the docs is checked against the files by `scripts/check_citations.py` (485 on 2026-10-19). To read a BP
line:

```bash
unzip -p "/Users/knarayanam/WorkfusionRepos/NSS/names-screening/names-screening-package/src/main/resources/business-process/CSV+File+Ingestion+_v_4.5.0-dev.zip" project.xml | sed -n '396,397p'
```

**Inference** marks a conclusion that no file states. *Unknown* means the evidence is too thin.

Control Tower (WorkFusion's server) is not in the repo. Its behaviour below was read from bytecode of the jars in
`~/.m2/repository/com/freedomoss/crowdcontrol/` (`control-tower-record-streaming`, `workfusion-service`,
`workfusion-model`, version `10.3.3.4-SNAPSHOT`), for example:

```bash
javap -p -c -constants -cp ~/.m2/repository/com/freedomoss/crowdcontrol/control-tower-record-streaming/10.3.3.4-SNAPSHOT/control-tower-record-streaming-10.3.3.4-SNAPSHOT.jar com.workfusion.controltower.record.streaming.service.ExternalRecordBusinessProcessProvider
```

The deployed Control Tower version is unknown, so every such claim is **Inference**. (A reviewer found the same calls
in the 10.3.1.11, 10.3.2.3, 10.3.3.0 and 10.3.3.4 jars.)

## 1. The path, side by side

| | Evelyn (WorkFusion) | UiPath (this port) |
|---|---|---|
| Entry | BP "CSV File Ingestion"; it takes no input data: `CSVBP:811` “<inputType>NO_DATA</inputType>” (the e2e tests start it with a dummy file) | Flow `EvMigCsvFileIngestionFlow`, manual trigger, no inputs; started by hand (no schedule in this slice) |
| Step 1 | `csv-monitor-task`: one output row per data file | Function `EvMigCsvMonitorTask`, called by node "csv-monitor-task" |
| Fan-out | each output row becomes its own record; the platform does it | Loop "For each data file" over the function's `rows` |
| Step 2 | `csv-task`, once per file: one row per alert, or one `stop` row | Function `EvMigCsvTask`, called by node "csv-task" inside the loop |
| Fan-out | same, per row | Loop "For each record" over the function's `rows` |
| Gate | rule "Should proceed?", per record | Decision "Should proceed?", per record |
| Call | ProcessCall "NSS-main-BP": asynchronous, by signal `nss-signal-id` | Flow-call node "NSS-main-BP" to `EvMigNamesScreeningFlow`, `fireAndForget: true` (decisions DEC-4) |
| End | "Final Results" | End node "Final Results" |
| Main entry | BP "Names Screening", listening on `nss-signal-id` | Flow `EvMigNamesScreeningFlow`; its inputs are one record plus the run context |
| Main step 1 | `input-task`, the shared entry step of the REST, flat and prebuilt inputs: skipped for CSV, but it still stamps `provider_id` | Not ported (out of scope); `provider_id` is a flow input (D-2) |
| Router | rule "Screening System" on `provider_id` | Decision "Screening System" |
| CSV step | `csv-schema-producer` | Function `EvMigCsvSchemaProducer`, called by node "csv-schema-producer" |
| After it | SubEnd "Final Results", then "Validate WLE" and the rest of the main BP | End node "Final Results"; the slice stops here |

## 2. The prompt's §3, checked line by line

| # | Claim in the prompt | Verdict | Evidence |
|---|---|---|---|
| 1 | A step that outputs N rows sends N records on; each goes through the rest of the BP on its own | Confirmed, **Inference** | Control Tower's `JavaWorkerResultConverter` marks a result as split when it has more than one row, and `BotRecordProcessingResultsWriter` makes one record per row (bytecode; the transition code of a schema-less BP such as the CSV BP was not traced). Evelyn's code relies on it: `J:task/csv/CsvMonitorTaskProcessor.java:37` “csvDataFiles.forEach(csvFile ->” adds one row per file |
| 2 | CSV BP: `Start → csv-monitor-task → csv-task → Should proceed? → Yes: ProcessCall "NSS-main-BP" → Final Results`; No goes to Final Results | Confirmed | Nodes `CSVBP:758` “(csv-monitor-task-processor)”, `CSVBP:763` “(csv-task-processor)”, `CSVBP:780` “name="Should proceed?"”, `CSVBP:740` “label="NSS-main-BP"”, `CSVBP:735` “name="Final Results"”. Edges: Yes `CSVBP:785-786` “target="4"”; No `CSVBP:796-797` “target="3"”; call to end `CSVBP:753-754` “source="4" style="link" target="3"” |
| 3 | `csv-monitor-task` reads `provider.FORMAT_FILE_LOCATION` and `provider.CSV_DATA_FILE_LOCATION` | Confirmed | `J:task/csv/CsvMonitorTaskProcessor.java:30-31` “getRequiredProperty(DATA_FILE_LOCATION.getPath())”; key strings `J:constants/CSVConfiguration.java:9` “DATA_FILE_LOCATION("provider.CSV_DATA_FILE_LOCATION")” and `J:constants/CSVConfiguration.java:10` “FORMAT_FILE_LOCATION("provider.FORMAT_FILE_LOCATION")” |
| 4 | It checks that the format file exists | Confirmed: the path is split into bucket and key, the bucket is checked, then the object | `J:task/csv/CsvMonitorTaskProcessor.java:33` “s3DownloadService.validateFileExists(formatFileLocation);”. Reasons: `C:service/S3DownloadService.java:156` “Missing bucket name”, `C:service/S3DownloadService.java:165` “Path to file or folder isn't correct”, `C:service/S3DownloadService.java:49` “Bucket with such name doesn't exist on S3”, `C:service/S3DownloadService.java:46` “Please provide correct path to file”. The full message is `<reason>: <input>` (an `InvalidPathException`), wrapped by the step: `JT:task/csv/it/CsvMonitorTaskProcessorIT.java:218` “Exception was thrown by Evelyn NSS step csv-monitor-task: Missing bucket name: nss_input_format.csv” |
| 5 | It lists the CSV data files in S3 and outputs one row per data file | Confirmed, with details | `J:task/csv/CsvMonitorTaskProcessor.java:34` “getCsvFilesList(csvDataFileLocation)”. A path ending `.csv` is taken as one file and checked like the format file (`C:service/S3DownloadService.java:71-72` “validateFileExists(fullPath);”); otherwise every key under the prefix, at any depth, ending in lower-case `.csv` (`C:service/S3DownloadService.java:84` “.filter(s3Object -> s3Object.getKey().endsWith(CSV_EXTENSION))”); the format file is not excluded. A listing failure raised by the AWS SDK is swallowed (`C:service/S3DownloadService.java:87` “} catch (SdkClientException e) {”; in AWS SDK v1 service errors such as a missing bucket are `SdkClientException`s too, per `javap` on aws-java-sdk-core 1.12.792 from `~/.m2`, **Inference** for the deployed version), so a missing bucket and an empty folder both end in `C:service/S3DownloadService.java:93` “There are no csv files in ”. Row keys are the lower-cased enum names, not the config keys: `J:task/csv/CsvMonitorTaskProcessor.java:40` “.put(DATA_FILE_LOCATION.name().toLowerCase(), csvFile)” |
| 6 | `csv-task` runs once per file | Confirmed, **Inference** (follows from claim 1) | It reads one file pair per run: `J:task/csv/CsvTaskProcessor.java:44` “.get(FORMAT_FILE_LOCATION.name()” and `J:task/csv/CsvTaskProcessor.java:47` “.get(DATA_FILE_LOCATION.name()” |
| 7 | It maps the format file and the data file into screened records, each with its WLE list | Confirmed | `J:task/csv/CsvTaskProcessor.java:51` “csvDataService.mapFileFormat(formatFileLocation)” and `J:task/csv/CsvTaskProcessor.java:53` “csvDataService.mapDataFile(dataFileLocation, format, configuration)”. The rules are in section 5.4 |
| 8 | `request_id` = the data file's name if `configuration.keep_input_file_name_for_qc_report` is true, else a random UUID | Confirmed, with details | `J:task/csv/CsvTaskProcessor.java:56-57` “dataFileLocation.substring(dataFileLocation.lastIndexOf('/') + 1)” (name with its extension); `J:task/csv/CsvTaskProcessor.java:59` “requestId = UUID.randomUUID()”. One value per file, so every record of a file shares it. The key is required with no code default, and it is not in `configuration_payload.json` (section 7) |
| 9 | One row per screened record with `screened_data`, `wle_list`, `request_id`, or a single `stop=true` row when the file has no data | Confirmed, with details | `J:task/csv/CsvTaskProcessor.java:72-74` “.put(REQUEST_ID, requestId)”; `J:task/csv/CsvTaskProcessor.java:77` “put("stop", "true")” (the value is the string `"true"`). The stop row comes whenever no alert survives: the file has no data rows; or every alert was dropped (even with `proceed_with_error_data` true: `JT:task/csv/it/CsvTaskProcessorIT.java:353` “shouldReleaseStopSignalWhenAllRecordsHaveErrors_proceedWithCorrectRecordsOn”); or that key is false and any row had a parse error (`J:task/csv/service/CsvDataService.java:196` “Stopping processing due to parsing errors.”) |
| 10 | The ProcessCall is asynchronous (`nss-signal-id`, `synchronous=false`) | Confirmed | `CSVBP:393` “<botTaskType>BP_CALL</botTaskType>”; `CSVBP:396` “nss-signal-id”; `CSVBP:397` “&lt;synchronous&gt;false&lt;/synchronous&gt;”. The main BP listens on that signal: `MAINBP:13141` “<externalSignalId>nss-signal-id</externalSignalId>” |
| 11 | "There is one main-BP run per row, and the parent gets nothing back" | **Half corrected, Inference.** The parent gets nothing back: yes. One run per row: **no** | The call publishes one message per record (`QueueProcessCallChannel`). On the receiving side, `ExternalRecordBusinessProcessProvider` first calls `findMostRecentRunningBp(signalId)` and adds the record to that running instance; it starts a new instance (`copyAndRunBusinessProcess`) only when none is running. So many records (one file, several files, even REST calls) share one main-BP run id. Evelyn's code presumes it: the master record is unique per (run, request id) `C:domain/MasterRecord.java:21` “columnNames = {"bp_run_id", "ext_record_id"}”, wait-for-completion counts per (run, request id) `J:task/finalizetransaction/WaitForCompletionProcessor.java:100` “countByBpRunUuidAndExtRecordIdAndStatusIsNotIn”, `J:utils/ExecutionUtils.java:41` “makes an HTTP call to Control Tower for every transaction.”, and the e2e tests pair one main run with one CSV run: `IT:extension/NssE2EExtension.java:589` “new CsvFlowRuns(runBusinessProcessAsIs(), runCsvBusinessProcess())”. Nothing back: Control Tower answers the call with "Record Processing Started" (`ExternalRecordListener`), and `ProcessCallResultListener` then completes the parent step with an empty result; an error answer (for example "BP Definition with external signal id [%s] can't be found") fails the parent step |
| 12 | Main BP: `Start → input-task (skipped for CSV) → Screening System? (by provider id) → CSV: csv-schema-producer → …` | Confirmed, with corrections | Start `MAINBP:13056` “Start id="585"”; group "Screening Systems" `MAINBP:12436` “name="Screening Systems"” holds input-task `MAINBP:12754` “(input-task-processor)”, the rule (named "Screening System", no question mark) `MAINBP:12448` “name="Screening System"” and the producer `MAINBP:12769` “(csv-schema-producer-processor)”. CSV outcome `MAINBP:800` “checkValue("provider_id", "EQ", "CSV")”, edge `MAINBP:12471-12472` “source="349" style="link" target="560"”. After the producer: SubEnd "Final Results" `MAINBP:12774-12775` “source="560" style="link" target="398"” |
| 12a | (how input-task is skipped, and where `provider_id` comes from) | Detail the prompt leaves out | `J:task/input/InputTaskProcessor.java:63` “!CSV.name().equalsIgnoreCase(providerId) &&”. Skipped or not, its `afterRunning` stamps `provider_id`: `J:task/input/InputTaskProcessor.java:95` “putValue(PROVIDER_ID, providerId)”. The value comes from the configuration, not from the record: `J:utils/ConfigurationUtil.java:23` “configuration.getRequiredProperty(INPUT_TYPE.getPath())”, returned as is unless it is `SCREENING_SYSTEM`, in which case `configuration.PROVIDER_ID` is returned. So in Evelyn a CSV record reaches `csv-schema-producer` only if the deployment's `INPUT_TYPE` is `CSV` |
| 13 | After `csv-schema-producer` come enrichment, the model, reports, master selection, QC, send results and purge | Confirmed by two research agents' decodes of the main BP; not cited line by line here (out of scope) | |
| 14 | `csv-schema-producer` parses `screened_data` and `wle_list` | Confirmed (Gson) | `J:task/csv/CsvSchemaProducerProcessor.java:46` “gson.fromJson(input.getData().get(SCREENED_DATA).toString(), ScreenedData.class)”; `J:task/csv/CsvSchemaProducerProcessor.java:47` “gson.fromJson(input.getData().get(WLE_LIST).toString(), listType)” |
| 15 | It calls `startNewTransaction(clientId, uuid, requestId)`: status NEW, the BP run id, the times and versions, `ext_record_id` = `request_id` | Confirmed, with details | `J:task/csv/CsvSchemaProducerProcessor.java:50` “startNewTransaction(screenedData.getClientId(), screenedData.getUuid(), requestId)”. The 3-argument overload passes no original transaction: `J:service/TransactionService.java:54` “return startNewTransaction(clientId, uuid, extRecordId, null);”. Column by column in section 8.1. The transaction id is `screened_data.uuid`, minted by `csv-task`: `S:ScreenedDataUtils.java:65` “.setUuid(UUID.randomUUID())”. The BP run id is the **main** BP's run (the step runs there): `J:utils/ExecutionUtils.java:45` “taskExecutionContext.getBpExecutionUuid()” |
| 15a | (what a repeated call does) | Detail the prompt leaves out; **Inference** for production | `J:service/TransactionService.java:74` “return transactionRepository.save(newTransaction);”. The uuid is assigned by the caller, so Spring Data runs a JPA merge: a second call with the same uuid **overwrites** the row (status back to NEW, end and error fields cleared). A research agent showed it with Hibernate 6.6 on H2, not on SQL Server; the team's own comment says the same: `J:task/input/service/PrebuiltInputDataService.java:82` “would overwrite that”. A database integrity error (for example two inserts racing on one uuid) is caught, logged and ignored, and the step goes on: `J:service/TransactionService.java:76` “logger.warn("transaction '{}' already exist", newTransaction.getUuid());”. Repeated calls happen when the platform retries a failed step: the retry limit comes from the task context, default 10 (`J:exceptions/CustomErrorHandling.java:60` “getStepExecutionRetryLimit()).orElse(10)”); who retries is not in the repo |
| 16 | It calls `initFullAnalytics`: one `alert_analytics` row, and one `hit_analytics` row per WLE | Confirmed, with details | `J:task/csv/CsvSchemaProducerProcessor.java:52` “analyticsService.initFullAnalytics(transaction, screenedData, wleDataList);”, one database transaction for both tables: `J:service/AnalyticsService.java:83` “@Transactional”. The alert row is written only if none exists for the transaction: `J:service/AnalyticsService.java:49` “getAlertAnalyticsByTransactionUuid(transaction.getUuid())”. Hit rows have no check (`J:service/AnalyticsService.java:77` “hitAnalyticsRepository.save(newHitAnalytics);”), so a repeated call duplicates them |
| 17 | It outputs `transaction_id`, `screened_data`, `wle_list`, `request_id`, `wle_count` and `is_internal_request` (true for CSV) | Confirmed for the code | `J:task/csv/CsvSchemaProducerProcessor.java:56` “.putValue(TRANSACTION_ID, transaction.getUuid())” to `J:task/csv/CsvSchemaProducerProcessor.java:61` “.putValue(INTERNAL_REQUEST, isInternalRequest)”. True for CSV because the record has no `rest_request` key: `J:task/csv/CsvSchemaProducerProcessor.java:49` “!input.getData().containsKey(RestRequest.REQUEST_FIELD_NAME)”. The step's declared out-contract in the BP lists five fields, without `wle_count` (`MAINBP:9901-9925` “transaction_id:”); whether Control Tower drops undeclared fields is unknown, and nothing reads `wle_count` |
| 18 | (§5) The analytics rows link to the transaction by a text `transaction_uuid`, no foreign key | Confirmed | `M:034_1_alert_analytics_table.yaml:17` “name: transaction_uuid”, `M:034_2_hit_analytics_table.yaml:17` “name: transaction_uuid”; no changeset declares a foreign or primary key (all 29 changesets, and the DDL from three Liquibase versions) |
| 19 | (§5) Evelyn wraps `initFullAnalytics` in `@Transactional` | Confirmed | row 16. `startNewTransaction` is not inside it: `TransactionService` has no `@Transactional`, so the transaction row is committed first |

## 3. CSV File Ingestion BP → `EvMigCsvFileIngestionFlow`

Node labels keep Evelyn's step names. A node's id comes from its label (the CLI derives it), so the ids below are the
expected ones; the build script records the real ones.

| Evelyn node (mxGraph id) | Evidence | UiPath node: label → id, type | Wiring and notes |
|---|---|---|---|
| Start (2) | `CSVBP:746` “source="2" style="link" target="11"” | trigger `start`, `core.trigger.manual` | No flow inputs, like the BP's `NO_DATA` start |
| csv-monitor-task (11) | `CSVBP:39` “&lt;processor&gt;csv-monitor-task&lt;/processor&gt;” | "csv-monitor-task" → `csvMonitorTask1`, `uipath.core.function.<key of EvMigCsvMonitorTask>` | no inputs |
| (implicit fan-out over rows) | claim 1 above | "For each data file" → `forEachDataFile1`, `core.logic.loop` | `collection` = `=js:$vars.csvMonitorTask1.output.rows`, `parallel: false` |
| csv-task (12) | `CSVBP:228` “&lt;processor&gt;csv-task&lt;/processor&gt;”; its worker runs with the high-memory profile, `CSVBP:227` “:high-memory”, a 4 GB heap: `JR:META-INF/worker/worker-high-memory.yml:4` “heap: 4096” | "csv-task" → `csvTask1`, function node of `EvMigCsvTask`, `--parent forEachDataFile1` | inputs `data_file_location`, `format_file_location` from `$vars.forEachDataFile1.currentItem` |
| (implicit fan-out over rows) | claim 1 | "For each record" → `forEachRecord1`, loop, `--parent forEachDataFile1` | `collection` = `=js:$vars.csvTask1.output.rows`, `parallel: false` |
| Should proceed? (15) | `CSVBP:188` “checkValue("stop", "EQ", "true")” sends to No; `CSVBP:205` “sendResultToUnconditionalOutcomes($item, true)” sends the rest to Yes | "Should proceed?" → `shouldProceed1`, `core.logic.decision`, `--parent forEachRecord1` | expression `$vars.forEachRecord1.currentItem.stop !== "true"` (no `=js:` on a Decision). Control Tower's `EQ` trims and ignores case (bytecode, **Inference**); the exact `!==` is equivalent because `csv-task` writes exactly `"true"` |
| NSS-main-BP (4), `BP_CALL` | `CSVBP:740` “label="NSS-main-BP"”; `CSVBP:396-397` “&lt;synchronous&gt;false&lt;/synchronous&gt;” | "NSS-main-BP" → id from the CLI, `uipath.core.flow.<key of EvMigNamesScreeningFlow>`, `--parent forEachRecord1` | `fireAndForget: true`; inputs in section 10; true edge from `shouldProceed1`, then back to the loop's `continue` port. Its error port is armed and also goes to the loop's `continue` (Q17, D-18) |
| Final Results (3), End | `CSVBP:735` “id="3" name="Final Results" type="end"” | "Final Results" → `finalResults1`, `core.control.end` | after `forEachDataFile1`'s `success` port. Evelyn's End step also exports the run's records (a WebHarvest config); nothing in this slice reads that export, and whether anything outside it does is unknown (D-10) |
| Link 17, No → Final Results | `CSVBP:796-797` “source="15" style="link" target="3"” | false edge of `shouldProceed1` → `forEachRecord1` `continue` port | the record's path ends, as in Evelyn; the loop moves to the next record |

## 4. Names Screening BP → `EvMigNamesScreeningFlow`

| Evelyn node (mxGraph id) | Evidence | UiPath node: label → id, type | Notes |
|---|---|---|---|
| Start (585), SubStart (348) of group "Screening Systems" (347) | `MAINBP:13056` “Start id="585" name="Start" type="start"”; `MAINBP:12443` “id="348" name="Start" type="sub_start"” | trigger `start` | flow inputs in section 10. The group has no equivalent; the slice is flat |
| input-task (531) | `MAINBP:909` “&lt;processor&gt;input-task&lt;/processor&gt;” | not ported | the shared entry step of the REST, flat and prebuilt inputs, out of scope. For CSV it only stamps `provider_id` and `location_enrichment_enabled` (`J:task/input/InputTaskProcessor.java:96` “putValue(LOCATION_ENRICHMENT_ENABLED”); `provider_id` becomes a flow input (D-2); `location_enrichment_enabled` is not needed before enrichment |
| Screening System (349), rule | `MAINBP:12448` “name="Screening System"”; CSV outcome `MAINBP:793` “rule "5. Send records to 'CSV' when provider_id EQ 'CSV'"” | "Screening System" → `screeningSystem1`, `core.logic.decision` | expression `$vars.start.output.provider_id === "CSV"` (exact, see the note on `EQ` in section 3). The other six outcomes (Factiva, Firco, WC1, TR, TR monitoring, Rest API) are out of scope; the false branch goes to an End node labelled "Other providers (not ported)" |
| csv-schema-producer (560) | `MAINBP:9795` “&lt;processor&gt;csv-schema-producer&lt;/processor&gt;”; edge in `MAINBP:12471` “label="CSV"” | "csv-schema-producer" → `csvSchemaProducer1`, function node of `EvMigCsvSchemaProducer` | inputs in section 10 |
| SubEnd "Final Results" (398) | `MAINBP:12513` “id="398" name="Final Results" type="sub_end"” | "Final Results" → `finalResults1`, `core.control.end` | the slice ends here; the flow declares no outputs, because the caller does not wait (the async parent gets nothing either) |

## 5. Task processors → Functions

### 5.1 `csv-monitor-task` → `EvMigCsvMonitorTask`

| | Evelyn | UiPath |
|---|---|---|
| Class | `J:task/csv/CsvMonitorTaskProcessor.java:19` “@TaskProcessor(id = "csv-monitor-task")” | `EvMigCsvMonitorTask/main.py` |
| Input | none: `run` never reads `input` (`J:task/csv/CsvMonitorTaskProcessor.java:27` “public TaskOutputData run(TaskInputData input) {”) | an input model with no fields |
| Configuration | `provider.FORMAT_FILE_LOCATION`, `provider.CSV_DATA_FILE_LOCATION` (claim 3) | the same keys, from the bucket file (DEC-8) |
| External calls | `validateFileExists`, `getCsvFilesList` on S3 | the bucket store's `validate_file_exists`, `get_csv_files_list` on `EvMigFiles` (DEC-7) |
| Output | one row per file: `data_file_location` and `format_file_location` (claim 5) | `rows: [{data_file_location, format_file_location}]`, plus `bp_start_time` (DEC-5, D-2) |
| Errors | `<reason>: <input>` (claim 4), wrapped as `J:exceptions/CustomErrorHandling.java:56` “Exception was thrown by Evelyn NSS step %s: %s” and thrown as `NSSProcessingException`, so a failed job shows `com.workfusion.dw.nss.exceptions.NSSProcessingException: Exception was thrown by Evelyn NSS step csv-monitor-task: …` (`JT:task/csv/it/CsvMonitorTaskProcessorIT.java:107` “Please provide correct path to file: test-bucket/nss_input_format”) | the same message from “Exception was thrown …” on, raised; the Java class name in front is not reproduced (D-8) |

### 5.2 `csv-task` → `EvMigCsvTask`

| | Evelyn | UiPath |
|---|---|---|
| Class | `J:task/csv/CsvTaskProcessor.java:34` “@TaskProcessor(id = "csv-task")”, high-memory profile `J:task/csv/CsvTaskProcessor.java:33` “@WorkerProfile("high-memory")” (4 GB heap, section 3) | `EvMigCsvTask/main.py`; the default robot size (1 GB) first, because the mock files are small; robot size is set on the process after deploy, not in the package (D-11) |
| Input | `format_file_location`, `data_file_location` (claim 6) | the same two strings |
| Configuration | `model.thresholds.location_wle_enable` (`J:task/csv/service/CsvDataService.java:75` “ENABLE_LOCATION_WLE.getPath()”), `configuration.proceed_with_error_data` (`J:task/csv/service/CsvDataService.java:76` “PROCEED_WITH_ERROR_DATA.getPath()”), `configuration.keep_input_file_name_for_qc_report` (claim 8) | the same keys |
| Helpers | `CsvDataService`, the format-file validators, the schema utils (section 6) | `EvMigCsvTask/csv_data_service.py`, `EvMigCsvTask/file_format_validation.py`, the library's `evmig_nss.schema` |
| Output | rows of `screened_data`, `wle_list` (Gson JSON text), `request_id`, or one `stop` row (claim 9) | `rows: [{screened_data, wle_list, request_id, stop}]`: every row always carries all four keys, null when unused, so a record row has `stop: null` and the stop row has `stop: "true"` and the other three null; `screened_data` and `wle_list` travel as objects (D-8) |
| Logging | `J:task/csv/service/CsvDataService.java:180` “Parsing completed. {} out of {} alerts will proceed to NSS main Business Process.” (INFO; ERROR with the same text when rows had errors) | the same texts, Python `logging` (D-9) |

### 5.3 `csv-schema-producer` → `EvMigCsvSchemaProducer`

| | Evelyn | UiPath |
|---|---|---|
| Class | `J:task/csv/CsvSchemaProducerProcessor.java:35` “@TaskProcessor(id = "csv-schema-producer")” | `EvMigCsvSchemaProducer/main.py` |
| Input | `screened_data`, `wle_list`; `request_id`, "" when absent (`J:task/csv/CsvSchemaProducerProcessor.java:48` “.orElse(StringUtils.EMPTY);”); the presence of a `rest_request` key (claim 17) | `screened_data`, `wle_list`, `request_id`, optional `rest_request`; plus `bp_run_id`, `bp_start_time` (D-2) |
| Context the platform supplies | run id and run start time (`J:utils/ExecutionUtils.java:45` “getBpExecutionUuid()”), variation id (`J:utils/ExecutionUtils.java:59` “public String getVariationId()”), versions (`J:service/TransactionService.java:69-70` “nssProperties.getMlVersion()”) | flow inputs, the job's folder key, library constants (DEC-5) |
| Calls | `startNewTransaction`, then `initFullAnalytics` (claims 15-16) | `TransactionService.start_new_transaction`, then `AnalyticsService.init_full_analytics`, over Data Fabric (DEC-6) |
| Output | six fields (claim 17) | the same six fields |
| On error | rethrown; no transaction is marked ERROR, because the input has no `transaction_id` (`J:exceptions/CustomErrorHandling.java:49` “inputData.getData().get(TRANSACTION_ID)”) | raised; same outcome (DEC-3) |

### 5.4 The format file and the data file (what `CsvDataService` does)

| Rule | Evidence |
|---|---|
| Both files are parsed by commons-csv `EXCEL` with a header row and a comma delimiter; a UTF-8 BOM is removed first; a zero-byte file fails with "File <path> is empty" | `C:service/S3DownloadService.java:126` “CSVFormat.EXCEL.builder()”; `C:service/S3DownloadService.java:120` “is empty” |
| Format file: the first line is a header and is skipped; column 0 is the NSS name, column 1 the client's column name; both lower-cased and trimmed; rows with an empty column 1 are ignored; two rows with the same client column make the step fail (a duplicate-key exception) | `J:task/csv/service/CsvDataService.java:45` “CLIENT_COLUMN = 1”, `J:task/csv/service/CsvDataService.java:46` “NSS_COLUMN = 0”, `J:task/csv/service/CsvDataService.java:65` “!csvRecord.get(CLIENT_COLUMN).isEmpty()” |
| Format file must map `input_full_name`, `input_id` and `hit_matched_name`, checked as substrings of the NSS names; else "Errors found: [...]" | `J:task/csv/service/CsvDataService.java:70` “validateFormat(result);” |
| Data file: header names are matched lower-cased and trimmed; values are trimmed and a blank value counts as absent; a blank line is a record (with no values), so it raises a name error | `J:task/csv/service/CsvDataService.java:158` “toLowerCase().trim()” |
| Rows are grouped by `input_id` (trimmed, case-sensitive); a blank id makes its own alert with a random id; the first row of an id builds the alert, every row with a valid WLE adds one; if the first row of an id is invalid, every row of that id is dropped | `J:task/csv/service/CsvDataService.java:133` “boolean canCreateNewAlert = isFirstRowForAlert && isScreenedDataPartValid && isWlePartValid;”; `J:task/csv/service/CsvDataService.java:137` “failedSourceInputIds.add(sourceInputId);” |
| A LOCATION-type WLE is dropped when `location_wle_enable` is false (no error is recorded, but an alert whose first row is such a WLE is dropped) | `J:task/csv/service/CsvDataService.java:75` “ENABLE_LOCATION_WLE.getPath()” |
| Dates are month-first (`06/10/1991` is 10 June); aliases, dates and locations come out in Java `HashMap` order, not file order | the schema utils in `S` (`DateUtils`, `NameUtils`, `LocationUtils`); verified by a research agent who ran the real classes |

## 6. Java classes → Python modules

The table is the plan. A class with logic gets its own module, named in snake_case; small related classes share one
module where the table says so. Only the methods this path calls are ported.

| Evelyn class (module) | UiPath home | Why there |
|---|---|---|
| `CsvMonitorTaskProcessor` (jnw) | `EvMigCsvMonitorTask/main.py` | the processor is the function |
| `CsvTaskProcessor` (jnw) | `EvMigCsvTask/main.py` | |
| `CsvDataService` (jnw) | `EvMigCsvTask/csv_data_service.py` | used only by `csv-task` |
| `DataSizeValidation`, `FileFormatInputIdValidator`, `FileFormatInputFullNameValidator`, `FileFormatHitMatchedNameValidator` (jnw `utils/validation/rules`) | `EvMigCsvTask/file_format_validation.py` | four tiny classes used only by `CsvDataService` |
| `CsvSchemaProducerProcessor` (jnw) | `EvMigCsvSchemaProducer/main.py` | |
| `TransactionService`, `AnalyticsService` (jnw) | `evmig_nss/service/transaction_service.py`, `analytics_service.py` | used by both inputs (`input-task` and `csv-schema-producer`) |
| `ExecutionUtils` (jnw) | not ported | its values arrive as inputs (D-2) |
| `CustomErrorHandling` (jnw), message text only | `evmig_nss/core/errors.py` | all three functions |
| `ProcessingAttributes` (jnw constants) | `evmig_nss/core/processing_attributes.py` | record keys shared by all steps |
| `CSVConfiguration`, `NssConfiguration`, `ThresholdConfiguration` (jnw constants, the keys this path reads) and the toolkit's `TaskConfigurationProvider` / `JsonConfiguration` | `evmig_nss/core/configuration.py` | keys plus the loader (DEC-8) |
| `usecase.properties` via `NssProperties` | `evmig_nss/core/usecase.py` | `dw_version`, `model_version` (DEC-5) |
| `S3DownloadService` (core) | `evmig_nss/core/bucket_store.py` | the S3 stand-in (DEC-7) |
| `Transaction`, `TransactionStatus`, `AlertAnalytics`, `HitAnalytics` (core domain) | `evmig_nss/core/transaction.py`, `evmig_nss/core/analytics.py` | |
| `TransactionRepository`, `AlertAnalyticsRepository`, `HitAnalyticsRepository` (core, Spring Data) | `evmig_nss/core/repository.py` | the store class over Data Fabric |
| `InputParameters`, `HitParameters`, `AttributeNames` (core constants), `InputAttribute` | `evmig_nss/core/constants.py` | used by the schema utils |
| `ScreenedData`, `WleData` and their nested types (generated from `nss_schema.yaml`) | `evmig_nss/schema/models.py` | section 9 |
| `ScreenedDataUtils`, `WleDataUtils`, `NameUtils`, `DateUtils`, `DateFormat`, `LocationUtils`, `EntityTypeUtils`, `GenderUtils`, `AdditionalDataUtils`, `ErrorUtils` (schema) | `evmig_nss/schema/<name>.py` | Evelyn keeps them in `names-screening-schema`, shared by the CSV and REST inputs |

## 7. Configuration keys

The three processors read five keys, every one with `getRequiredProperty` (no code default; a missing key fails the
step). Only one of the five is in Evelyn's `configuration_payload.json`; the others come from the form
(`configuration.json`) and the saved configuration of a deployment.

| Key | Read by | Type | In `configuration_payload.json` | Form key, and the form's default |
|---|---|---|---|---|
| `provider.FORMAT_FILE_LOCATION` | monitor | string `bucket/key` | no | `P:configuration.json:795` “"key": "provider.FORMAT_FILE_LOCATION"”; default `P:configuration.json:788` “doc-upload/name_sanctions_screening/example_input_format.csv” (must end `.csv`) |
| `provider.CSV_DATA_FILE_LOCATION` | monitor | string `bucket/key` or `bucket/prefix/` | no | `P:configuration.json:825` “"key": "provider.CSV_DATA_FILE_LOCATION"”; default `P:configuration.json:820` “doc-upload/name_sanctions_screening/example_historical_data.csv” |
| `configuration.proceed_with_error_data` | csv-task | boolean | no | `P:configuration.json:868` “"key": "configuration.proceed_with_error_data"”; default true at `P:configuration.json:851` “"defaultValue": true,” |
| `configuration.keep_input_file_name_for_qc_report` | csv-task | boolean | no | `P:configuration.json:895` “"key": "configuration.keep_input_file_name_for_qc_report"”; default true at `P:configuration.json:878` “"defaultValue": true,” |
| `model.thresholds.location_wle_enable` | csv-task | boolean | yes, false: `P:configuration_payload.json:161` “"location_wle_enable": false,” | `P:configuration.json:2496` “"key": "model.thresholds.location_wle_enable"” |

Keys that `input-task` reads on the main BP's path, which this slice does not port:

| Key | Use | Evidence |
|---|---|---|
| `configuration.INPUT_TYPE` (required) | decides `provider_id`; must be `CSV` for a record to reach `csv-schema-producer`. The shipped default is `SCREENING_SYSTEM` | `J:utils/ConfigurationUtil.java:23` “getRequiredProperty(INPUT_TYPE.getPath())”; `P:configuration_payload.json:3` “"INPUT_TYPE": "SCREENING_SYSTEM",” |
| `configuration.ongoing_monitoring` (optional) | also skips `input-task` when true | `J:task/input/InputTaskProcessor.java:56` “ONGOING_MONITORING.getPath()” |
| `enrichment.location.provider` (optional) | sets `location_enrichment_enabled` | read in `InputTaskProcessor.isLocationEnrichmentEnabled` |

The Java reader accepts JSON booleans and the strings `"true"`/`"false"` (the form's radio buttons store strings),
and resolves `a.b` as a nested path with a flat-key fallback. The port keeps both behaviours (DEC-8).

## 8. Tables → Data Fabric entities

Final state after the 29 changesets that `M:install.changelog.xml:5` “_changelist-3-0.yaml” includes, in the order
`M:_changelist-3-0.yaml` lists them (034_x run before 033). The untracked
`048_add_bp_name_to_transaction_table.yaml` *(untracked)* is **not** in that list
(`M:_changelist-3-0.yaml:79` “file: 048_add_original_transaction_uuid_to_transaction_table.yaml” is the last entry), so `bp_name` is left out.
A research agent cross-checked this state with Liquibase 3.6.3, 4.31.1 and 5.0.1 and a real apply on H2.

The cited line is the column's `name:` line; its `type:` is on the next line. Field names are PascalCase because Data
Fabric field names allow letters and digits only: `SDK:entities/_entity_schema_service.py:48` “_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9]*$")”.
Types follow DEC-6 (`NVARCHAR(n)` → `STRING(n)`, `NVARCHAR(MAX)` → `MULTILINE_TEXT` 10,000, `DATETIME2` →
`DATETIME_WITH_TZ` in UTC). Data Fabric adds its own `Id`, `CreatedBy`, `CreateTime`, `UpdatedBy`, `UpdateTime`.
Each table's own `uuid` column is named after its entity (`TransactionUuid`, `AlertUuid`, `HitUuid`), not `Uuid`:
Data Fabric refuses `Uuid` as a reserved SQL word (owner's tenant run, 2026-10-19; D-5). The transaction's field has
the same name as the analytics entities' link field `TransactionUuid`, which holds the same value.

### 8.1 `ds_uc_B_AML_PEP_transaction_v3_0` → `EvMigTransaction` (14 columns)

Table name: `M:030_transaction_table.yaml:7` “tableName: ds_uc_B_AML_PEP_transaction_v3_0”.

| Column | Evidence | SQL type | Null | Field | Data Fabric type | Value written by `csv-schema-producer` |
|---|---|---|---|---|---|---|
| `uuid` | `M:030_transaction_table.yaml:10` “name: uuid” | NVARCHAR(36), unique, default NEWID() | no | `TransactionUuid` | STRING(36), required, unique | `screened_data.uuid` |
| `start_time` | `M:030_transaction_table.yaml:17` “name: start_time” | DATETIME2 | yes | `StartTime` | DATETIME_WITH_TZ | now (`J:service/TransactionService.java:67` “.setStartTime(new Date())”) |
| `end_time` | `M:030_transaction_table.yaml:20` “name: end_time” | DATETIME2 | yes | `EndTime` | DATETIME_WITH_TZ | not set |
| `status` | `M:030_transaction_table.yaml:23` “name: status” | NVARCHAR(36) | yes | `Status` | STRING(36) | `NEW` (`J:service/TransactionService.java:68` “TransactionStatus.NEW”) |
| `start_bp_uuid` | `M:030_transaction_table.yaml:26` “name: start_bp_uuid” | NVARCHAR(36) | yes | `StartBpUuid` | STRING(36) | the run id (`J:service/TransactionService.java:64` “.setBpRunUuid(bpDetails.getBpRunId())”; DEC-5) |
| `bp_start_time` | `M:034_3_alter_transaction_table.yaml:10` “name: bp_start_time” | DATETIME2 | yes | `BpStartTime` | DATETIME_WITH_TZ | the run start (`J:service/TransactionService.java:65` “new Date(bpDetails.getStartDate())”; DEC-5) |
| `error_message` | `M:034_3_alter_transaction_table.yaml:13` “name: error_message” | NVARCHAR(MAX) | yes | `ErrorMessage` | MULTILINE_TEXT 10,000 | not set |
| `error_step` | `M:034_3_alter_transaction_table.yaml:16` “name: error_step” | NVARCHAR(MAX) | yes | `ErrorStep` | MULTILINE_TEXT 10,000 | not set |
| `dw_variation` | `M:034_3_alter_transaction_table.yaml:19` “name: dw_variation” | NVARCHAR(255) | yes | `DwVariation` | STRING(255) | variation id (`J:service/TransactionService.java:66` “executionUtils.getVariationId()”; DEC-5) |
| `dw_version` | `M:034_3_alter_transaction_table.yaml:22` “name: dw_version” | NVARCHAR(255) | yes | `DwVersion` | STRING(255) | build version (`JR:usecase.properties:3` “version=${usecase.version}”; DEC-5) |
| `model_version` | `M:034_3_alter_transaction_table.yaml:25` “name: model_version” | NVARCHAR(255) | yes | `ModelVersion` | STRING(255) | `ml-model` (`E:pom.xml:21` “nss-classification-model-v5.3.0”; DEC-5) |
| `ext_record_id` | `M:036_add_ext_record_id_to_transaction_table.yaml:10` “name: ext_record_id” | NVARCHAR(255) | yes | `ExtRecordId` | STRING(255) | `request_id` (`J:service/TransactionService.java:71` “.setExtRecordId(extRecordId);”) |
| `client_id` | `M:044_add_client_id_column.yaml:16` “name: client_id” | NVARCHAR(255), default '1' | no | `ClientId` | STRING(255), required, default "1" | `screened_data.clientId` |
| `original_transaction_uuid` | `M:048_add_original_transaction_uuid_to_transaction_table.yaml:16` “name: original_transaction_uuid” | NVARCHAR(36) | yes | `OriginalTransactionUuid` | STRING(36) | null on this path (claim 15) |

Java mapping: `C:domain/Transaction.java:19` “@Table(name = "ds_uc_B_AML_PEP_transaction_v3_0")”; the run id field
is `bpRunUuid` on column `start_bp_uuid`: `C:domain/Transaction.java:32` “@Column(name = "start_bp_uuid", length = 36)”.

### 8.2 `ds_uc_B_AML_PEP_alert_analytics_v3_0` → `EvMigAlertAnalytics` (20 columns)

Table name: `M:034_1_alert_analytics_table.yaml:7` “tableName: ds_uc_B_AML_PEP_alert_analytics_v3_0”. One row per
transaction, written only if none exists (claim 16). Java: `C:domain/analytics/AlertAnalytics.java:20` “@Table(name = "ds_uc_B_AML_PEP_alert_analytics_v3_0")”.

| Column | Evidence | SQL type | Field | Data Fabric type | Written at init (value) |
|---|---|---|---|---|---|
| `uuid` | `M:034_1_alert_analytics_table.yaml:10` “name: uuid” | NVARCHAR(36), unique, NOT NULL, default NEWID() (`M:034_1_alert_analytics_table.yaml:12` “defaultValueComputed: NEWID()”) | `AlertUuid` | STRING(36), required, unique | new random uuid (Hibernate generates it: `C:domain/analytics/AlertAnalytics.java:24` “@GeneratedValue(strategy = GenerationType.AUTO)”) |
| `transaction_uuid` | `M:034_1_alert_analytics_table.yaml:17` “name: transaction_uuid” | NVARCHAR(36) | `TransactionUuid` | STRING(36) | the transaction uuid |
| `alert_id` | `M:034_1_alert_analytics_table.yaml:20` “name: alert_id” | NVARCHAR(MAX) | `AlertId` | MULTILINE_TEXT 10,000 | `screened_data.id` |
| `alert_category` | `M:034_1_alert_analytics_table.yaml:23` “name: alert_category” | NVARCHAR(MAX) | `AlertCategory` | MULTILINE_TEXT 10,000 | `screened_data.category` |
| `alert_entity_type` | `M:034_1_alert_analytics_table.yaml:26` “name: alert_entity_type” | NVARCHAR(255) | `AlertEntityType` | STRING(255) | entity type name, or null |
| `alert_dw_decision` | `M:034_1_alert_analytics_table.yaml:29` “name: alert_dw_decision” | NVARCHAR(255) | `AlertDwDecision` | STRING(255) | not set |
| `alert_dw_explanation` | `M:034_1_alert_analytics_table.yaml:32` “name: alert_dw_explanation” | NVARCHAR(MAX) | `AlertDwExplanation` | MULTILINE_TEXT 10,000 | not set |
| `alert_mt_decision` | `M:034_1_alert_analytics_table.yaml:35` “name: alert_mt_decision” | NVARCHAR(255) | `AlertMtDecision` | STRING(255) | not set |
| `alert_mt_explanation` | `M:034_1_alert_analytics_table.yaml:38` “name: alert_mt_explanation” | NVARCHAR(MAX) | `AlertMtExplanation` | MULTILINE_TEXT 10,000 | not set |
| `worker_full_name` | `M:034_1_alert_analytics_table.yaml:41` “name: worker_full_name” | NVARCHAR(255) | `WorkerFullName` | STRING(255) | not set |
| `worker_id` | `M:034_1_alert_analytics_table.yaml:44` “name: worker_id” | NVARCHAR(36) | `WorkerId` | STRING(36) | not set |
| `html_report_link` | `M:034_1_alert_analytics_table.yaml:47` “name: html_report_link” | NVARCHAR(MAX) | `HtmlReportLink` | MULTILINE_TEXT 10,000 | not set |
| `csv_report_link` | `M:034_1_alert_analytics_table.yaml:50` “name: csv_report_link” | NVARCHAR(MAX) | `CsvReportLink` | MULTILINE_TEXT 10,000 | not set |
| `autoQC` | `M:034_1_alert_analytics_table.yaml:53` “name: autoQC” | NVARCHAR(5) | `AutoQC` | BOOLEAN (DEC-6, D-5) | Java `false` (`C:domain/analytics/AlertAnalytics.java:71` “private boolean selectedForAutoQC;”). The stored text is probably `0`: Evelyn's dashboards compare `P:analytics/superset_assets/Name Sanction Screening Alert Details.json:573` “autoQC=0” (**Inference**) |
| `ticker` | `M:034_1_alert_analytics_table.yaml:56` “name: ticker” | NVARCHAR(5) | `Ticker` | BOOLEAN (DEC-6, D-5) | Java `false` (`C:domain/analytics/AlertAnalytics.java:74` “private boolean tickerUsed;”), probably stored as `0` |
| `gold_decision` | `M:039_add_gold_value_to_analytics_table.yaml:10` “name: gold_decision” | NVARCHAR(36) | `GoldDecision` | STRING(36) | `screened_data.goldDecision` |
| `mt_review_start` | `M:040_add_mt_start_end_time.yaml:10` “name: mt_review_start” | DATETIME2 | `MtReviewStart` | DATETIME_WITH_TZ | not set |
| `mt_review_complete` | `M:040_add_mt_start_end_time.yaml:13` “name: mt_review_complete” | DATETIME2 | `MtReviewComplete` | DATETIME_WITH_TZ | not set |
| `client_id` | `M:044_add_client_id_column.yaml:54` “name: client_id” | NVARCHAR(255), NOT NULL, default '1' | `ClientId` | STRING(255), required, default "1" | `screened_data.clientId` |
| `original_transaction_uuid` | `M:047_add_original_transaction_uuid_to_alert_analytics.yaml:16` “name: original_transaction_uuid” | NVARCHAR(36) | `OriginalTransactionUuid` | STRING(36) | `screened_data.originalTransaction` (null on this path) |

Values at init: `J:service/AnalyticsService.java:51-57` “.setGoldDecision(goldDecision);”.

### 8.3 `ds_uc_B_AML_PEP_hit_analytics_v3_0` → `EvMigHitAnalytics` (14 columns)

Table name: `M:034_2_hit_analytics_table.yaml:7` “tableName: ds_uc_B_AML_PEP_hit_analytics_v3_0”. One row per
WLE. Java: `C:domain/analytics/HitAnalytics.java:19` “@Table(name = "ds_uc_B_AML_PEP_hit_analytics_v3_0")”.

| Column | Evidence | SQL type | Field | Data Fabric type | Written at init (value) |
|---|---|---|---|---|---|
| `uuid` | `M:034_2_hit_analytics_table.yaml:10` “name: uuid” | NVARCHAR(36), unique, NOT NULL, default NEWID() (`M:034_2_hit_analytics_table.yaml:12` “defaultValueComputed: NEWID()”) | `HitUuid` | STRING(36), required, unique | new random uuid (`C:domain/analytics/HitAnalytics.java:23` “@GeneratedValue(strategy = GenerationType.AUTO)”) |
| `transaction_uuid` | `M:034_2_hit_analytics_table.yaml:17` “name: transaction_uuid” | NVARCHAR(36) | `TransactionUuid` | STRING(36) | the transaction uuid |
| `wle_id` | `M:034_2_hit_analytics_table.yaml:20` “name: wle_id” | NVARCHAR(255) | `WleId` | STRING(255) | `wle.id` |
| `wle_category` | `M:034_2_hit_analytics_table.yaml:23` “name: wle_category” | NVARCHAR(255) | `WleCategory` | STRING(255) | `wle.category` |
| `wle_entity_type` | `M:034_2_hit_analytics_table.yaml:26` “name: wle_entity_type” | NVARCHAR(255) | `WleEntityType` | STRING(255) | entity type name, or null |
| `wle_dw_decision` | `M:034_2_hit_analytics_table.yaml:29` “name: wle_dw_decision” | NVARCHAR(255) | `WleDwDecision` | STRING(255) | not set |
| `wle_dw_explanation` | `M:034_2_hit_analytics_table.yaml:32` “name: wle_dw_explanation” | NVARCHAR(MAX) | `WleDwExplanation` | MULTILINE_TEXT 10,000 | not set |
| `wle_mt_decision` | `M:034_2_hit_analytics_table.yaml:35` “name: wle_mt_decision” | NVARCHAR(255) | `WleMtDecision` | STRING(255) | not set |
| `wle_mt_explanation` | `M:034_2_hit_analytics_table.yaml:38` “name: wle_mt_explanation” | NVARCHAR(MAX) | `WleMtExplanation` | MULTILINE_TEXT 10,000 | not set |
| `worker_full_name` | `M:034_2_hit_analytics_table.yaml:41` “name: worker_full_name” | NVARCHAR(255) | `WorkerFullName` | STRING(255) | not set |
| `worker_id` | `M:034_2_hit_analytics_table.yaml:44` “name: worker_id” | NVARCHAR(36) | `WorkerId` | STRING(36) | not set |
| `gold_decision` | `M:039_add_gold_value_to_analytics_table.yaml:18` “name: gold_decision” | NVARCHAR(36) | `GoldDecision` | STRING(36) | `wle.goldDecision` |
| `name_matching_score` | `M:043_add_scores_to_hit_analytics_table.yaml:10` “name: name_matching_score” | NVARCHAR(50) | `NameMatchingScore` | STRING(50) | not set |
| `wle_decision_score` | `M:043_add_scores_to_hit_analytics_table.yaml:13` “name: wle_decision_score” | NVARCHAR(5) | `WleDecisionScore` | STRING(5) | not set |

Values at init: `J:service/AnalyticsService.java:71-75` “.setGoldDecision(wle.getGoldDecision());”. `(transaction_uuid, wle_id)`
is not unique in Evelyn: a CSV may hold identical hit ids, and the e2e suite tests it
(`IT:e2e/CsvProviderTest.java:233` “CSV: Identical hit ids”).

### 8.4 Evelyn's indexes, which Data Fabric cannot carry (D-5)

All ten are non-unique. Data Fabric offers only a single-field `isUnique`, used for each table's own uuid field (`TransactionUuid`,
`AlertUuid`, `HitUuid`; each table's unique column).

| Table | Index (columns in the changeset) | Evidence |
|---|---|---|
| transaction | `idx_transaction_uuid_status` (uuid, status) | `M:030_transaction_table.yaml:35` “indexName: idx_transaction_uuid_status” |
| transaction | `idx_bp_uuid_status` (start_bp_uuid, status) | `M:034_3_alter_transaction_table.yaml:34` “indexName: idx_bp_uuid_status” |
| transaction | `idx_bp_uuid_status_ext_record_id` (ext_record_id, status, bp_start_time) | `M:036_add_ext_record_id_to_transaction_table.yaml:24` “indexName: idx_bp_uuid_status_ext_record_id” |
| transaction | `idx_bp_uuid_status_start_end_time` | `M:045_add_indexes_for_qc_report.yaml:23` “indexName: idx_bp_uuid_status_start_end_time” |
| transaction | `idx_variations_status_start_end_time` | `M:045_add_indexes_for_qc_report.yaml:46` “indexName: idx_variations_status_start_end_time” |
| alert_analytics | `idx_alert_analytics_transaction_uuid` | `M:034_1_alert_analytics_table.yaml:63` “indexName: idx_alert_analytics_transaction_uuid” |
| alert_analytics | `idx_gold_decision` | `M:039_add_gold_value_to_analytics_table.yaml:38` “indexName: idx_gold_decision” |
| alert_analytics | `idx_mt_review_times` | `M:040_add_mt_start_end_time.yaml:22` “indexName: idx_mt_review_times” |
| hit_analytics | `idx_wle_analytics_transaction_uuid_wle_id` | `M:034_2_hit_analytics_table.yaml:53` “indexName: idx_wle_analytics_transaction_uuid_wle_id” |
| hit_analytics | `idx_gold_model_mt_decision` | `M:039_add_gold_value_to_analytics_table.yaml:31` “indexName: idx_gold_model_mt_decision” |

## 9. `ScreenedData` and `WleData` → pydantic models

Source: `K:src/main/resources/nss_schema.yaml`. Evelyn pins the contract artifact `4.4.0`
(`E:pom.xml:23` “<usecase.schema-contract-version>4.4.0</usecase.schema-contract-version>”), which is not on this
machine; `ffc12d6` is the version you chose. That the two agree for these types is **Inference** (decisions, Q12). One
pointer: the copy of the yaml in Evelyn's last local build (`E/names-screening-schema/target/generated-resources/`,
built from a `4.3.0-SNAPSHOT` jar) differs from `ffc12d6` only in its version line.

Evelyn's Java classes are generated from the yaml with no `@SerializedName`, and its Gson has no naming policy
(`C:config/AppConfig.java:49` “return new GsonBuilder().serializeNulls().create();”), so `csv-task` writes the Java
field names, and a research agent who ran the real classes saw exactly that. Three differ from the yaml:

| yaml key | Evidence | Key `csv-task` writes (Java field) | Python attribute (DEC-3) |
|---|---|---|---|
| `client_id`, default "1" | `K:src/main/resources/nss_schema.yaml:98-100` “default: "1"” | `clientId` | `clientId` |
| `additional_data` | `K:src/main/resources/nss_schema.yaml:125` “additional_data:” | `additionalData` | `additionalData` |
| `add_to_ongoing_monitor`, default false | `K:src/main/resources/nss_schema.yaml:131-133` “default: false” | `addToOngoingMonitor` | `addToOngoingMonitor` |

Whether Control Tower changes these keys between the two BPs is unknown (**Inference** that it does not: the producer
parses them with the same Gson). The main BP's own embedded copy of the schema spells them in snake_case
(`MAINBP:608` “client_id:”, `MAINBP:635` “additional_data:”), and it is older than the code: it has no
`originalTransaction`.

All 15 `ScreenedData` keys (`K:src/main/resources/nss_schema.yaml:90` “ScreenedData:”): `uuid` (string, format
uuid), `id`, `clientId`, `category`, `entityType` (enum INDIVIDUAL, ORGANIZATION, SECURITIES, LOCATION), `gender`
(enum MALE, FEMALE, OTHER), `name` (NameEntity), `dates` (list of DateEntity), `locations` (list of LocationEntity),
`aliases` (list of NameEntity), `identifiers` (string map), `additionalData` (string map), `goldDecision`,
`addToOngoingMonitor`, `originalTransaction` (string, format uuid, added on this branch:
`K:src/main/resources/nss_schema.yaml:134` “originalTransaction:”). The 12 `WleData` keys
(`K:src/main/resources/nss_schema.yaml:138` “WleData:”) are the same minus `clientId`, `addToOngoingMonitor` and
`originalTransaction`. Nested types: NameEntity {fullName, firstName, lastName, middleName, derived, source};
DateEntity {original, derived, source} of DetailedDate {type, full, year, month, day}, all strings; LocationEntity
{original, enriched (list), source} of Location {type, country, state, city, street, address, latitude, longitude},
all strings. The yaml declares no `required` and no `nullable`. The generated classes start lists and maps empty,
`clientId` as "1" and `addToOngoingMonitor` as false; Gson keeps those values when a key is absent from the JSON.

What this path reads from them: `uuid`, `clientId`, `id`, `category`, `entityType`, `goldDecision`,
`originalTransaction` of the alert, and `id`, `category`, `entityType`, `goldDecision` of each WLE
(`J:service/AnalyticsService.java:34` “screenedData.getId(), screenedData.getCategory(), screenedData.getClientId()”).
The CSV mapping fills the rest so that later steps (enrichment, the model) can use it.

## 10. Record fields between steps → Flow and Function fields

| Field | Evelyn: written by → read by | UiPath carrier |
|---|---|---|
| `data_file_location`, `format_file_location` | monitor row → `csv-task` | monitor output `rows[i]`, loop item, `csv-task` inputs |
| `screened_data`, `wle_list` | `csv-task` (Gson text) → BP call → `csv-schema-producer` | `csv-task` output `rows[i]` (objects), main-flow inputs `screened_data` (object) and `wle_list` (array of objects), producer inputs |
| `request_id` | `csv-task` → BP call → producer (`ext_record_id`) | same path, string |
| `stop` | `csv-task` → rule "Should proceed?" | `rows[i].stop`, read by the Decision |
| `provider_id` | `input-task.afterRunning` → rule "Screening System" | main-flow input `provider_id`, set to `"CSV"` by the CSV flow (D-2) |
| BP run id, run start time | Control Tower task context → `startNewTransaction` | main-flow inputs `bp_run_id` (`=js:$metadata.InstanceId` of the CSV flow) and `bp_start_time` (D-2) |
| `transaction_id`, `wle_count`, `is_internal_request` | producer → later steps | producer output; nothing reads it in the slice |
| `_sys_*` fields (`_sys_ext_record_id`, `_sys_bp_transaction_id`) | Control Tower system fields; the BP call removes or renames them | not ported: unused on this path |
| `rest_request` | REST input only; its absence makes `is_internal_request` true | optional producer input, never set by the CSV flow. A Flow node sends every input, so "absent" means null, "" or {} (DEC-3) |
