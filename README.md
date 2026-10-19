# Evelyn → UiPath: the first slice

A port of one path of Evelyn, WorkFusion's Names Sanctions Screening digital worker, to UiPath. The path is the BP
"CSV File Ingestion" calling the main "Names Screening" BP, up to and including its `csv-schema-producer` step: read
the CSV files from storage, turn each alert into a screened record, and start one main run per record, which writes
the transaction and its analytics rows. It is a translation, not a redesign. Each forced change has a D-number in
[docs/differences.md](docs/differences.md).

Built 2026-10-19 against Evelyn `master` @ `fa168ccb2` (2026-10-16) and the contract `nss_schema.yaml` @ `ffc12d6`.
Private: nothing here is pushed. How to run it is in [HOW_TO_RUN.md](HOW_TO_RUN.md). Rules for AI agents are in
[AGENTS.md](AGENTS.md).

## WorkFusion → UiPath

| Evelyn (WorkFusion) | Here (UiPath) |
|---|---|
| BP "CSV File Ingestion" | Maestro Flow `EvMigCsvFileIngestionFlow` (manual trigger, no inputs) |
| Task `csv-monitor-task` (`CsvMonitorTaskProcessor`) | Python coded function `EvMigCsvMonitorTask`, called by the node "csv-monitor-task" |
| One record per output row (Control Tower splits the rows) | Loop "For each data file" over the monitor's `rows` |
| Task `csv-task` (`CsvTaskProcessor`, `CsvDataService`) | Function `EvMigCsvTask`. Its error port is armed, so a bad file skips to the next one (D-12) |
| One record per alert | Loop "For each record" over `csv-task`'s `rows` |
| Rule "Should proceed?" (`stop EQ 'true'`) | Decision "Should proceed?" (`currentItem.stop !== "true"`) |
| ProcessCall "NSS-main-BP" (`nss-signal-id`, asynchronous) | Flow-call node "NSS-main-BP" to `EvMigNamesScreeningFlow`, `fireAndForget: true` (D-1). Its error port is armed, so a child that fails to start skips to the next record (D-18) |
| BP "Names Screening": `input-task`, then rule "Screening System" | Maestro Flow `EvMigNamesScreeningFlow`, Decision "Screening System" on `provider_id === "CSV"`; `input-task` is not ported, and the CSV flow passes `provider_id` "CSV" (D-2) |
| Task `csv-schema-producer` (`CsvSchemaProducerProcessor`) | Function `EvMigCsvSchemaProducer`, then End "Final Results" |
| `names-screening-schema` and `names-screening-core` and the shared services (`TransactionService`, `AnalyticsService`) | Library `evmig-nss`, built as a wheel and copied into each function's `wheels/` (DEC-2) |
| S3 (`S3DownloadService`) | Orchestrator storage bucket `EvMigFiles`. Keys are Evelyn's S3 paths (D-4); `data/` is its local mirror |
| Configuration (`configuration_payload.json` plus the form) | `config/configuration_payload.json` in the bucket, read once per job (D-3) |
| Tables `transaction`, `alert_analytics`, `hit_analytics` (Liquibase) | Data Fabric entities `EvMigTransaction`, `EvMigAlertAnalytics`, `EvMigHitAnalytics` (tenant level, PascalCase fields; D-5) |
| BP run id, start time, variation, versions (Control Tower task context) | Flow inputs `bp_run_id` (`$metadata.InstanceId` of the CSV flow) and `bp_start_time` (from the monitor), the job's folder key, the library version (D-2) |
| Spring `@Transactional` over the alert and hit writes | Three separate Data Fabric writes in Evelyn's order; a rerun completes the rows without duplicating (D-6, D-7) |

## Status

| | Result (2026-10-19) |
|---|---|
| Library `evmig-nss` | `uv run pytest -q`: 457 passed |
| `EvMigCsvMonitorTask` | 33 passed (all 12 Java tests ported: 1 unit test and 11 ITs) |
| `EvMigCsvTask` | 148 passed (all 18 methods of `CsvDataServiceTest` and all 9 of `CsvTaskProcessorIT`; its CSV reader was compared with commons-csv 1.14.1 on 56 inputs: 55 pinned in `tests/csv_parser_cases.py`, plus one 200,000-character field) |
| `EvMigCsvSchemaProducer` | 35 passed (`CsvSchemaProducerProcessorTest` and `CsvSchemaProducerProcessorIT`) |
| Flows | Both `Valid` with no warnings; `uip solution pack --dry-run` `Valid`; `scripts/build_flows.sh` rebuilt in an empty copy gives the same `.flow` files apart from generated ids and what the designer adds (`scripts/normalize_flow.sh`) |
| Local run | The three functions in order on `data/`: 3 transactions, 3 alert rows and 5 hit rows (HOW_TO_RUN level 2) |
| Tenant | **Not run.** Nothing here touched a tenant. The staged tenant steps are in HOW_TO_RUN level 4, for the owner |

Still **Inference** until the first tenant run: that `fireAndForget: true` starts the child Flow (never run anywhere
before, Q1); that `$metadata.InstanceId` holds the CSV flow's id; that Data Fabric accepts the UTC text
`2026-10-19T07:15:00.123Z` for `DATETIME_WITH_TZ` fields; that `ListFiles` with a prefix without a trailing `/` returns
nested keys; what happens past Community's 3 concurrent jobs. HOW_TO_RUN lists the checks.

## Layout

```
README.md, HOW_TO_RUN.md, AGENTS.md, CLAUDE.md, .gitignore
docs/          mapping.md, decisions.md, differences.md, out-of-scope.md, notes-files-review.md (your notes vs the code)
data/          the bucket's content: configuration, format file, data files (README inside)
evmig-nss/     the library (src/evmig_nss: schema, core, service, testing), its tests, dist/ (the wheel)
EvMigEvelyn/   the Solution (EvMigEvelyn.uipx and resources/ are tool-managed)
  EvMigCsvMonitorTask/, EvMigCsvTask/, EvMigCsvSchemaProducer/   function projects, each vendoring the wheel in wheels/
  EvMigNamesScreeningFlow/, EvMigCsvFileIngestionFlow/           the Flows (built by scripts/build_flows.sh)
  entities/      one *.create.json per table (generated from mapping §8), migrations/ for later changes
scripts/       build_flows.sh, normalize_flow.sh, vendor_wheel.sh, entities.py, check_citations.py
```

## Rebuild

What is generated, and the command that regenerates it. Run from the repo root unless a step says otherwise.

| Piece | Command | When |
|---|---|---|
| The wheel, and its copy in each function | `scripts/vendor_wheel.sh` | after any library change; bump `version` in `evmig-nss/pyproject.toml` first |
| A function's `entry-points.json` | `cd EvMigEvelyn/<function> && uv run uipath init`, then delete the empty `.env` it creates | after changing its input or output model; then rebuild the Flows |
| The Flows | remove both Flow projects (`cd EvMigEvelyn && uip solution projects remove ./EvMigCsvFileIngestionFlow`, the same for `EvMigNamesScreeningFlow`, then `rm -rf` both folders), then `scripts/build_flows.sh` | after changing a Flow or a function's schema |

Tidying a Flow in the Studio Web designer is fine: the rebuild check (HOW_TO_RUN level 3) ignores layout and
designer metadata, so only a real change (an input, expression, edge, variable or node) fails it, and such a change
belongs in `scripts/build_flows.sh`. The designer also writes `evals/` and `simulations.json`, and a logged-in
`uip solution` command writes `userProfile/`; all three are unused here and gitignored.
| The entity files | `python3 -I scripts/entities.py --write` | after changing mapping §8 |

The Solution was assembled once with `uip solution init EvMigEvelyn`, the three function projects (each scaffolded
with `uv init --bare --python 3.11`, `uv python pin 3.11`, `uv add "uipath>=2.14.0,<2.15.0"`, `uv run uipath new
<name> --type function`, `uv add --dev pytest`, `uv add "pydantic>=2.10,<3"`, the wheel added from `wheels/`, and
`uv lock --upgrade-package uipath==2.14.27`), `uip solution projects add ./<function>` for each, then
`scripts/build_flows.sh`. Built with `uv` 0.13.0, Python 3.11, `uipath` 2.14.27 and `uip` 1.203.0 (the `.flow`
format changes between CLI versions).
