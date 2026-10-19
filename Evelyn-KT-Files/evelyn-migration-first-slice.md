# Evelyn → UiPath: the first slice (CSV ingestion → main flow skeleton)

You are starting the UiPath port of **Evelyn**, WorkFusion's Names Sanctions Screening digital
worker. The owner, Kowshik, is on the Evelyn team: a Java and WorkFusion background, new to Python.
They will review everything you produce with another AI, so make every claim checkable. Cite
`path:line`, label guesses **Inference**, and say "unknown" when the evidence is thin.

This is not a full migration. Port one path, faithfully and small: the **CSV File Ingestion BP**
calling the **main Names Screening BP**. The main flow ends after its first CSV step.

## 1. Hard rules

1. **A new repo:** work only in `/Users/knarayanam/UiPathRepos/experiment-evelyn-migration`
   (`git init`, no remote). It will hold Evelyn's logic, so it stays private. Don't add a remote,
   push or commit unless the owner asks.
2. **Read-only, never edit or commit:**
   - the Evelyn repos under `/Users/knarayanam/WorkfusionRepos/NSS/` (leave their uncommitted and
     untracked files alone);
   - `/Users/knarayanam/UiPathRepos/UiPath-WorkFusion/` (another team's port);
   - `/Users/knarayanam/UiPathRepos/Evelyn Simulation/` and `/Users/knarayanam/UiPathRepos/learning/`.
3. **Nothing on a tenant without the owner's go-ahead.**
   - Not allowed: `uip maestro flow debug`, `uip solution upload/publish/deploy`,
     `uip df entities create` or `records insert`, bucket create or upload, starting a job.
   - Fine, because they only read: `uip login status`, `validate`, `registry`,
     `resources list/refresh`, `pack --dry-run`, `uip df entities list`.
   - Write the tenant steps into HOW_TO_RUN.md for the owner to run.
4. **No secrets.**
   - Never run `uipath auth` in a project folder: it writes a token into `.env`, and `pack`
     ships `.env`. Use `uip login`.
   - Never copy credentials from any repo. `UiPath-WorkFusion/Isaac/scripts/call_workfusion_isaac.py:20-23`
     and some Evelyn helper repos contain committed ones.
5. **Mock data only.** Read Evelyn's synthetic test files for the format, but write your own rows
   with placeholder names (Alice Wonderland, John Doe, Gill Bates). Design the rows so a wrong port
   fails a test.
6. **Translate, don't redesign.** Keep Evelyn's step names, field names and behaviour. Where UiPath
   forces a change, record it as a numbered difference (D-1, D-2…) in `docs/differences.md`.
7. **Unique tenant names.** Prefix every Solution, Flow, function, bucket and entity with `EvMig`.

## 2. Read first

In this order. The Evelyn snapshot: `names-screening` `master` @ `fa168ccb2` (2026-10-16) and
`names-screening-contract` @ `ffc12d6`. Record the commits you read in the README.

**Evelyn.** The code is the source of truth; the notes can be stale, so check them against it.
Paths are relative to `/Users/knarayanam/WorkfusionRepos/NSS/names-screening/`:
- `CLAUDE.md` and `AGENTS.md`: the repo's own rules.
- `notes_files/MAIN_BP_FLOW.md`: the main BP's step order, the CSV BP, and how results reach a
  caller.
- The BPs: `names-screening-package/src/main/resources/business-process/CSV+File+Ingestion+_v_4.5.0-dev.zip`
  and `Names+Screening+_v_4.5.0-dev.zip`. Unzip them into a scratch folder. `project.xml` is
  XML-escaped mxGraph, and node order in the file is not execution order.
- The CSV processors in `names-screening-jnw/src/main/java/com/workfusion/dw/nss/task/csv/`:
  - `CsvMonitorTaskProcessor`, `CsvTaskProcessor` and `CsvSchemaProducerProcessor`;
  - `service/CsvDataService`;
  - their tests, under `src/test/.../task/csv/`.
- `task/input/InputTaskProcessor.java`: the REST and other inputs. Its `shouldRun` is false for CSV.
- The services and their tests:
  - `service/TransactionService.java`: `startNewTransaction`;
  - `service/AnalyticsService.java`: `initFullAnalytics`.
- In `names-screening-core`: `core/domain/Transaction.java` and `core/service/S3DownloadService.java`.
- The configuration keys:
  - in code, `constants/CSVConfiguration.java` and `constants/NssConfiguration.java`;
  - the form, `names-screening-package/src/main/resources/configuration.json`;
  - the saved values, `configuration_payload.json` beside it.
- The tables, in `names-screening-package/src/main/resources/datastore/migrations/` (Liquibase).
  Apply the changesets in `install.changelog.xml` order and take the final state of three tables:
  the transaction table, `alert_analytics` and `hit_analytics`.
- The data contract, `ScreenedData` and `WleData`:
  `/Users/knarayanam/WorkfusionRepos/NSS/names-screening-contract/src/main/resources/nss_schema.yaml`.
- Other notes in `notes_files/` as you need them: `JNW_DEEP_DIVE.md`, `FIRCO_SCREENING.md` and
  `INTEGRATION_TESTS_WALKTHROUGH.md`.

**UiPath, and how we build here:**
- In `/Users/knarayanam/UiPathRepos/learning/KT/`:
  - `evelyn-migration-headstart.md`;
  - `equivalent.md`, the WorkFusion ↔ UiPath dictionary;
  - `flow-read-write-contracts.md`;
  - `coded-functions.md`.
- `/Users/knarayanam/UiPathRepos/learning/playground/building-examples.md`, Part 2: Solutions,
  function projects, Flows built by `uip maestro flow node/variable/edge add`, and the traps.
- `/Users/knarayanam/UiPathRepos/Evelyn Simulation/`: toy versions of this very path. Their levels 0–3 were run
  on the owner's tenant on 2026-10-16.
  - **CsvProcessor Simulation:** a CSV Flow calling a child Flow, and a bucket.
  - **Datastore Simulation:** Data Fabric entities created from JSON files, a lookup before
    insert, and a fake entities service for the tests.
  - **Dependency Simulation:** a library shipped inside a function as a wheel.
  - **Configuration Simulation:** settings loaded from a bucket file. Don't copy its Credential
    asset: it blocks debug runs.
- The other team's port, as a precedent (read-only). Their `AGENTS.md` files are partly stale, so
  check them against the code.
  - `/Users/knarayanam/UiPathRepos/UiPath-WorkFusion/Evan/`: `AGENTS.md`, `docs/` and
    `EvanUiPath/`.
  - `shared/docs/uipath-deployment-pitfalls.md`.
- The UiPath docs: start at https://docs.uipath.com/llms.txt, and add `.md` to a page URL for
  Markdown.
- If the UiPath plugin skills are available (`uipath-maestro-flow`, `uipath-solution`,
  `uipath-platform`), load the matching one before its commands. Read its Data Fabric reference
  before any `uip df` command.

## 3. What Evelyn does on this path (verify each line)

WorkFusion BPs pass **records**. A step that outputs N rows sends N records on, and each one goes
through the rest of the BP on its own.

**CSV File Ingestion BP:**
`Start → csv-monitor-task → csv-task → Should proceed? → Yes: ProcessCall "NSS-main-BP" → Final Results`.
No goes straight to Final Results.
- **`csv-monitor-task`:**
  - reads `provider.FORMAT_FILE_LOCATION` and `provider.CSV_DATA_FILE_LOCATION`;
  - checks that the format file exists;
  - lists the CSV data files in S3, and outputs one row per data file.
- **`csv-task`, once per file:**
  - maps the format file and the data file into screened records, each with its WLE list;
  - sets `request_id`: the data file's name if `configuration.keep_input_file_name_for_qc_report`
    is true, otherwise a random UUID;
  - outputs one row per screened record, with `screened_data`, `wle_list` and `request_id`, or a
    single `stop=true` row when the file has no data.
- **The ProcessCall is asynchronous** (`nss-signal-id`, `synchronous=false`). There is one main-BP
  run per row, and the parent gets nothing back.

**Main BP:**
`Start → input-task (skipped for CSV) → Screening System? (by provider id) → CSV: csv-schema-producer → …`.
After `csv-schema-producer` come enrichment, the model, reports, master selection, QC, send results
and purge.
- **`csv-schema-producer`:**
  - parses `screened_data` and `wle_list`;
  - calls `TransactionService.startNewTransaction(clientId, uuid, requestId)`. It writes status
    NEW, the BP run id, the times and versions, and `ext_record_id` = `request_id`;
  - calls `AnalyticsService.initFullAnalytics`: one `alert_analytics` row, and one `hit_analytics`
    row per WLE;
  - outputs `transaction_id`, `screened_data`, `wle_list`, `request_id`, `wle_count` and
    `is_internal_request`, which is true for CSV.

## 4. Scope

**In:**
1. **The CSV flow, `EvMigCsvFileIngestionFlow`:** csv-monitor-task → csv-task → Should proceed? →
   call the main flow.
2. **The main flow, `EvMigNamesScreeningFlow`:** Start → the CSV branch → `csv-schema-producer` →
   End. That is one processor: a skeleton to build on later, not Evelyn's full behaviour.
3. **`csv-schema-producer` writes to Data Fabric:** the transaction, its `alert_analytics` row, and
   one `hit_analytics` row per WLE.
4. **S3 is mocked by an Orchestrator storage bucket, `EvMigFiles`.** Its object keys mirror
   Evelyn's S3 paths. For local runs, use a folder with the same layout.

**Out.** Don't build any of this. List each item in `docs/out-of-scope.md`, with what it will need
later.
- **The REST input** (`input-task`, Postman or curl). Keep the main flow's input contract to what
  both inputs produce, so a REST flow can be added later.
- **The other screening providers:** Firco Trust, Dow Jones, World-Check One and Thomson Reuters.
  - Firco and location enrichment depend on Evelyn's Java libraries `fircosoft-trust` and
    `address-lookup-jnw`, which can't be replaced yet. Don't port, wrap or call them.
  - When they come, each gets its own library project, the shape of the Dependency Simulation.
  - Open question: a Python function can't load a jar directly.
- **Everything after `csv-schema-producer`:** enrichment, the names classification model, reports,
  manual review, master selection, wait-for-completion, the QC report, send results and purge.
  Skip the QC report in particular: how to migrate its model is unsolved.
- **The Ticker Lookup, Orchestrate and Aggregated Analytics BPs.**
- **A scheduled trigger for the CSV monitor.** Start the CSV flow by hand for now.

## 5. Target design

Decide these in Phase 0 and write them in `docs/decisions.md`. Take the first option unless the
evidence says otherwise.

**Layout.** It mirrors Evelyn's modules:
```
experiment-evelyn-migration/
├── README.md, HOW_TO_RUN.md, AGENTS.md, CLAUDE.md (holds "@AGENTS.md"), .gitignore
├── docs/              mapping.md, decisions.md, differences.md, out-of-scope.md
├── data/              mock format file, mock data CSVs, mock configuration_payload.json
├── evmig-nss/         the shared library, with its own tests, built into a wheel
├── EvMigEvelyn/       the Solution
│   ├── EvMigCsvMonitorTask/, EvMigCsvTask/, EvMigCsvSchemaProducer/
│   │                  one function project per task processor, each vendoring the wheel in wheels/
│   ├── EvMigCsvFileIngestionFlow/, EvMigNamesScreeningFlow/
│   └── entities/      one *.create.json per table, and migrations/ for later changes
└── scripts/build_flows.sh   every `uip maestro flow` command that builds the two Flows
```

**Library contents.** `evmig-nss` holds:
- `schema`: `ScreenedData` and `WleData`, from `nss_schema.yaml`;
- `core`: `Transaction`, the configuration keys and the bucket store;
- `service`: `TransactionService` and `AnalyticsService`, over Data Fabric.

**Functions.** Write one function per processor, named after it.
- The processor's Java class becomes `main.py`, and its service classes become modules.
- Shared code goes in the library: what Evelyn keeps in `names-screening-schema` and
  `names-screening-core`, plus the services both inputs use.
- Ship the library inside each function as a vendored wheel. That was proved on a tenant on
  2026-10-16, in the Dependency Simulation.
- Evan copies its shared modules into each function instead (`Evan/tools/sync_shared_code.py`).
  Record which approach you chose, and why.

**Fan-out.** Keep Evelyn's semantics: one csv-task per data file, and one main-flow run per screened
record, fire and forget.
- Find out what Maestro Flow supports, from `uip maestro flow registry` and the docs: a loop node,
  and the Flow-call node's `fireAndForget`.
- If a Flow can't start one child run per item, fall back: pass the list to the main flow, and have
  `csv-schema-producer` make one transaction per record. Record that as a difference.

**BP run id.** Evelyn stores the BP run id on each transaction, and later steps group by it (master
selection, wait-for-completion).
- Pass the CSV flow's run id into every main-flow run.
- If a Flow can't read its own instance id, generate a UUID in the CSV flow's first node instead,
  and record it.

**Data Fabric:**
- **One `.create.json` per table,** with the columns of the final Liquibase state. Keep Evelyn's
  names, and map each snake_case column to its Data Fabric field name in `docs/mapping.md`.
- **Keep Evelyn's links and keys.** Evelyn links the analytics rows to the transaction by a text
  `transaction_uuid`, with no foreign key; keep that. Keep Evelyn's `uuid` as a unique field (Data
  Fabric adds its own `Id`).
- **There are no transactions across entities.** Evelyn wraps `initFullAnalytics` in
  `@Transactional`; Data Fabric can't. Write in Evelyn's order, check before each insert so a rerun
  doesn't duplicate rows, and record the difference.
- **Entities are tenant-level.**
- **Keep test runs small:** the Community tenant allows about 1,000 Data Fabric calls a day.

**Configuration:**
- Use the same keys and value shapes as Evelyn's `configuration_payload.json`, but only the ones
  this path reads.
- Store it in the bucket at `config/configuration_payload.json`; the library loads it once per job.
- No Credential assets.

**Code:**
- Python 3.11, `uv`, `uipath>=2.14.0,<2.15.0` as in the simulations, and pydantic models.
- The owner is new to Python, so keep the code plain. Add short comments where Python differs from
  the Java: Gson ↔ pydantic, a Spring repository ↔ the store class.

## 6. Platform facts already confirmed on the owner's tenant (2026-10-16)

- **Debug-run buckets:** the first `flow debug` creates the Solution's bucket in
  `<email>'s workspace/Debug_<FlowName>`, not in the workspace itself. Uploads must go there.
- **Changed tracked files:** `flow debug` rewrites the committed `.uipx` (its `SolutionId`), and
  `resources refresh` can add fields to files under `resources/`. Don't commit those changes.
- **Credential assets:** a Credential asset with no username and password in a Solution makes every
  `flow debug` fail at provisioning.
- **List commands:** `--output-filter` needs an explicit `--limit`.
- **Data Fabric:**
  - a RELATIONSHIP field pointing at a missing row is refused, with "Relationship violation";
  - a duplicate unique value is refused, with "Value uniqueness violation … Error Number: 2627";
  - a batch insert reports each failed row separately; a mixed batch is untested;
  - debug-run jobs reach Data Fabric as the user.
- **Null list inputs:** a Flow node sends `null` for a list input it doesn't set. Give such inputs a
  `field_validator(mode="before")` that maps `None` to `[]`.
- **Run time:** debug runs took 30–70 seconds.

## 7. Work in phases

**Phase 0: read and plan, then stop.** Write:
- `docs/mapping.md`: each Evelyn step, class and table, and its UiPath piece, with `path:line`;
- `docs/decisions.md`: the choices in section 5, with the evidence;
- a short plan, with the open questions.

Show these to the owner and wait for a go-ahead before you write code.

**Phase 1: the library and its tests.**

**Phase 2: the three functions and their tests.**
- Port the test cases of `CsvMonitorTaskProcessorTest`, `CsvDataServiceTest` and
  `CsvSchemaProducerProcessorTest`.
- Port the parts of `TransactionServiceTest` and `AnalyticsServiceTest` that this path uses.
- Test Data Fabric and the bucket with fakes, in the shape of the Datastore Simulation's
  `FakeEntities`.

**Phase 3: the entity JSON files.** Check them with `jq` against the Liquibase columns.

**Phase 4: the Flows.**
- Build them only with `scripts/build_flows.sh`.
- `uip maestro flow validate` reports no warnings for either Flow.
- `uip solution pack . --dry-run` is Valid.

**Phase 5: the docs.**
- **README:** what this is, a WorkFusion → UiPath table, the status, and how to rebuild.
- **HOW_TO_RUN:** in levels, each step with a check.
  - Tests.
  - A local run that calls the three functions in order on the mock data.
  - The tenant run, written as steps for the owner.
- **AGENTS.md:** rules for the next AI, which files are source and which are generated, and how to
  verify.

**Phase 6: verify.**
- Run every command in HOW_TO_RUN levels 1–2 as written, in a fresh copy.
- Run `scripts/build_flows.sh` in an empty folder, and diff the `.flow` files with yours, ignoring
  generated ids.

## 8. Done when

- `uv run pytest -q` passes in the library and in each function. Put the counts in the README.
- Both Flows validate with no warnings, `pack --dry-run` is Valid, and the build script reproduces
  the Flows.
- Levels 1–2 of HOW_TO_RUN pass as written on a fresh copy.
- `docs/mapping.md`, `decisions.md`, `differences.md` and `out-of-scope.md` are filled in.
- Nothing ran on a tenant.

## 9. Final report (your last message)

Under 600 words:
- what you built, as a tree;
- the verification results, with the counts;
- the D-numbers;
- the decisions you made, and why;
- what is still **Inference**;
- the tenant steps waiting for the owner;
- your questions for the owner.
