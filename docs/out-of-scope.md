# Out of scope for the first slice

What this slice does not build, and what each piece will need later. The slice ends after `csv-schema-producer`
(mapping §1). Sections and D-numbers refer to [mapping.md](mapping.md), [decisions.md](decisions.md) and
[differences.md](differences.md).

| # | Not built | What it will need later |
|---|---|---|
| 1 | **The REST input** (`input-task`, Postman or curl) | A REST entry (an HTTP-triggered Flow or an API workflow) that produces the same main-flow inputs as the CSV flow: `screened_data`, `wle_list`, `request_id`, `provider_id`, `bp_run_id`, `bp_start_time`, plus `rest_request`, which `EvMigCsvSchemaProducer` already accepts (an absent value makes `is_internal_request` true). A port of `input-task`: it sets `provider_id` from `configuration.INPUT_TYPE` (mapping claim 12a) and reads `configuration.ongoing_monitoring` and `enrichment.location.provider` (mapping §7) |
| 2 | **The other screening providers:** Firco Trust, Dow Jones (Factiva), World-Check One, Thomson Reuters and TR monitoring | Each is one more outcome of the main flow's "Screening System" Decision, whose false branch ends at "Other providers (not ported)" today (mapping §4). Firco depends on Evelyn's Java library `fircosoft-trust`, which a Python function cannot load; when a provider comes, it gets its own library project in the shape of the Dependency Simulation. How to run Java code from a Python function is an open question |
| 3 | **Location enrichment** (`address-lookup-jnw`) | The same Java-library question as Firco. `input-task` sets `location_enrichment_enabled`, which nothing in this slice reads (mapping §4) |
| 4 | **Everything after `csv-schema-producer`:** Validate WLE, enrichment, the names classification model (`nss-classification-model-v5.3.0`), reports, manual review, master selection, wait-for-completion, the QC report, send results, purge | Master selection and wait-for-completion group transactions by (run id, `request_id`); this slice already writes the CSV flow's run id as `StartBpUuid` on every transaction for that reason (DEC-5). The QC report needs its model migrated, which is unsolved. Steps that mark a transaction ERROR need `finishTransactionWithError`, which this slice does not port: its producer has no `transaction_id` on input, so Evelyn marks nothing either (mapping §5.3) |
| 5 | **The Ticker Lookup, Orchestrate and Aggregated Analytics BPs** | Separate Flows. `AutoQC` and `Ticker` are already fields of `EvMigAlertAnalytics`, written false at init |
| 6 | **A scheduled trigger for the CSV monitor** | A time trigger on `EvMigCsvFileIngestionFlow`. Today the flow is started by hand |
| 7 | **Real-size CSV files** | Records travel inside Flow variables, and a job output above 10,240 characters may be dropped without an error (DEC-10, Q8), so the mock files are kept small. Real files need a "claim-check" design: `csv-task` writes its rows to the bucket and passes paths. Also a larger robot for `csv-task` (Evelyn runs it with a 4 GB heap; D-11) |
| 8 | **Evelyn's ten non-unique indexes** | Data Fabric offers only a single-field unique flag (mapping §8.4, D-5). If later queries (by run id, status, times) get slow, this needs a look then |
| 9 | **The CSV BP's "Final Results" export** | Evelyn's End step exports the run's records; nothing in the slice reads that export (D-10). Whether anything outside the slice does is unknown |
| 10 | **Entities shipped as Solution resources** | The owner creates the three entities with `uip df entities create` (DEC-6). Shipping them inside the Solution has its own deploy rules (Evan's way) |
| 11 | **The `bp_name` column** | Evelyn's untracked `048_add_bp_name_to_transaction_table.yaml` is not in the changelog, so it is left out (mapping §8). Add a field when it lands |
| 12 | **Fallback run id** | If `$metadata.InstanceId` turns out empty on the tenant, `csv-monitor-task` generates a UUID and the CSV flow passes that instead (DEC-5). Not built until the tenant run shows it is needed |
| 13 | **The `fireAndForget` fallbacks** | If `fireAndForget: true` fails on the tenant: first `false` (the CSV flow waits for each record), then one main-flow run per file with a list input (DEC-4). Neither is built |
| 14 | **A deploy pipeline** | Everything here is local; tenant steps are run by hand by the owner (HOW_TO_RUN) |
