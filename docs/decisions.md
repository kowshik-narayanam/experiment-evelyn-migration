# Decisions (Phase 0)

Status: proposed 2026-10-16; **approved by you on 2026-10-19**, with your answers recorded under "Open questions"
(defaults for all, plus your notes on Q11 and Q15). Citations use the aliases of
[mapping.md §0](mapping.md#0-sources-and-how-to-check-a-citation); a few platform facts cite a CLI command or a
docs page instead, and say so. Each decision says what it chose, why, what else was possible, and which numbered
difference (D-n, listed at the end) it creates. The questions (Q1-Q16) and your answers are at the end. Two
independent reviews of these two files were run, and their findings are folded in. Facts cited as "owner's tenant run,
2026-10-16" are what you observed on your tenant that day (CLI, by verification agents); no file records them.

## DEC-1 Layout and naming

- The layout of the prompt's §5: `README.md`, `HOW_TO_RUN.md`, `AGENTS.md`, `CLAUDE.md` (holding `@AGENTS.md`),
  `.gitignore`, `docs/`, `data/`, `evmig-nss/`, `EvMigEvelyn/` (three function projects, two Flows, `entities/` with an
  empty `migrations/` for later changes), `scripts/build_flows.sh`.
- One addition: `scripts/vendor_wheel.sh`, about ten lines (build the wheel, copy it into the three functions, `uv add`
  it, print the three sha256 sums). By hand that is 3 × 4 commands after every library change.
- Python modules follow Evelyn's classes, as planned in mapping §6.
- Names: every tenant-visible name starts with `EvMig` (Solution `EvMigEvelyn`, functions, Flows, bucket
  `EvMigFiles`, entities). Flow node labels keep Evelyn's step names ("csv-task", "Should proceed?", "NSS-main-BP").

## DEC-2 The library `evmig-nss`, shipped as a vendored wheel

**What it holds** (mapping §6): `evmig_nss.schema` (the `ScreenedData`/`WleData` models and Evelyn's schema utils),
`evmig_nss.core` (`Transaction`, analytics rows, configuration keys and loader, the bucket store, the Data Fabric
store, constants, the error text), `evmig_nss.service` (`TransactionService`, `AnalyticsService`).

**How it ships:** a wheel, copied into each function's `wheels/` folder and pinned in its `uv.lock`, as the Dependency
Simulation does: `SIM:Dependency Simulation/DependencySim/DependencySimFunction/pyproject.toml:19` “evsim-calc = { path = "wheels/evsim_calc-1.0.0-py3-none-any.whl" }”,
`SIM:Dependency Simulation/DependencySim/DependencySimFunction/uv.lock:602` “source = { path = "wheels/evsim_calc-1.0.0-py3-none-any.whl" }”.

| | Evidence |
|---|---|
| For | Your level-3 run installed the vendored wheel from the lock on the tenant: `SIM:Dependency Simulation/HOW_TO_RUN.md:14` “Level 3 was run on a tenant the same day”, `SIM:Dependency Simulation/HOW_TO_RUN.md:410` “Does `library_version` come back as `1.0.0`?” (answer "Yes"). This text is an **uncommitted** edit in that repo |
| Proved with dependencies | That wheel had none. `evmig-nss` declares `pydantic` and `uipath`, and it installed from the lock in a debug job: the job log had “+ evmig-nss==0.1.2 (from file:///tmp/home/.job-data/<id>/wheels/...)” (owner's tenant run, 2026-10-19) |
| Precedent against | No project in `W` ships its own code as a wheel. Evan copies 11 shared files with a script and a test: `W:Evan/tools/sync_shared_code.py:38` “SHARED = (”, `W:Evan/tests/project/test_shared_code_is_identical.py:32` “assert len(sync_shared_code.SHARED) == 11”. Isaac copies too |
| Traps | A changed wheel under the same version is refused by `uv` (`SIM:Dependency Simulation/README.md:574` “Hash mismatch for evsim-calc”), so every change bumps the version. The tenant installs from `uv.lock`, so the lock is refreshed before every pack: `W:shared/docs/uipath-deployment-pitfalls.md:346` “Refresh the lockfile before you pack.” |

Why the wheel over Evan's copy: one artifact with a real package boundary, and the mechanism already ran on your
tenant. The three copies are made by `scripts/vendor_wheel.sh` and checked by a test in each function (its wheel's
sha256 equals the one in `evmig-nss/dist/`). Fallback if the wheel fails on a tenant: Evan's copy-and-test. (Q13)

## DEC-3 Function conventions

| Rule | Why (evidence) |
|---|---|
| One function project per processor, one entry point `main` in `main.py` | the prompt; a Flow node cannot choose a second entry point: `L:playground/building-examples.md:107` “Runs locally, but a Flow node can't choose it” |
| Pydantic models. Field names are Evelyn's names in that layer: record keys stay snake_case (`screened_data`, `request_id`), `ScreenedData` keys stay camelCase (`clientId`, `entityType`). **No aliases** | the runtime ignores aliases on output: `L:KT/coded-functions.md:130` “the runtime dumps output without `by_alias`”; mapping §9 for the camelCase keys |
| Input models ignore unknown fields (`extra="ignore"`) | Maestro adds fields to a function's job arguments, for example the loop context: `W:IDP/specs/006-maestro-call-contract/spec.md:45` “`iterator`, `iterator[0]`”, and `L:KT/coded-functions.md:132` “Armed error ports inject `errorHandlingEnabled`”; Evan does it: `W:Evan/EvanUiPath/EvanAmmFunction/evan_amm/function/contract.py:71` “extra="ignore"” |
| An input a node may leave unset (`rest_request`) is optional; "absent" means null, "" or {}, because a node sends every input. A required input that arrives null or empty fails, as Evelyn fails on a missing field. A `mode="before"` validator maps null to `[]` only where a list may legitimately be unset | a node sends every input, unset ones as null or "": `L:playground/building-examples.md:99` “never the function's own default”; your fix for lists: `SIM:CsvProcessor Simulation/StudentSections/StudentSectionsFunction/main.py:35` “mode="before"” |
| **Errors are raised**, with Evelyn's text “Exception was thrown by Evelyn NSS step <id>: <message>” | translate, don't redesign: Evelyn always rethrows (`J:exceptions/CustomErrorHandling.java:81` “throw new NSSProcessingException(errorMessage, e);”), so the step fails. The other ports return errors as fields instead (`L:KT/coded-functions.md:102` “Never raise.”). Raising is safe while the parent does not wait for the child (DEC-4); it hangs a waiting parent, so the choice is Q14 |
| The configuration is loaded once per job (cached in the process) | each Function node run is its own Orchestrator job; this is what the prompt asks (DEC-8) |
| The SDK client is created on first use by a small factory, which tests replace | `uipath init` imports `main.py` and `UiPath()` needs a login; your simulations do the same |
| Log texts stay verbatim (for example "Parsing completed. %s out of %s alerts will proceed to NSS main Business Process.") | Evelyn's e2e tests assert them on the run's error events: `IT:e2e/CsvProviderTest.java:435` “Parsing completed. 0 out of 1 alerts will proceed to NSS main Business Process.”. Here they go to the job log (D-9) |

## DEC-4 Fan-out: two loops and a fire-and-forget Flow call

What Maestro offers, checked with `uip` 1.203.0 (nothing was run; no public doc mentions `fireAndForget` for Flow):

| Fact | Evidence |
|---|---|
| A loop node exists: `core.logic.loop`, inputs `collection`, `parallel`, nestable; the item is `$vars.<loop>.currentItem` | `uip maestro flow registry get core.logic.loop --output json` (command; read-only). A research agent built and validated a two-level nest with a Flow call inside, in a throwaway Solution that was not kept |
| The Flow-call node `uipath.core.flow.<key>` has a `fireAndForget` input; `true` compiles to the async service type and drops the node's output | `CLI:serialization-BXU6AKAN-xsgqvge2.js:19464` “const fireAndForget = inputs?.[FIRE_AND_FORGET_INPUT] === true;”; `CLI:headless-5kfya4w8.js:163108` “asyncServiceType: "Orchestrator.StartFlowProcessAsync",”; for Flow nodes the CLI also sets `CLI:headless-5kfya4w8.js:163110` “fireAndForgetFlagGated: true,” (meaning unknown; maybe a feature flag) |
| A Flow call inside loops runs in production elsewhere, **always waiting** | Isaac: `W:Isaac/IsaacUiPath/IsaacCoreFlow/IsaacCoreFlow.flow:837` “"fireAndForget": false,”; Edward: `W:Edward/EdwardUiPath/EdwardOrchestration/EdwardOrchestration.flow:703` “"id": "callOws",”. Across `W`, 44 `false` and 0 `true` |
| A Decision branch can go straight back to a loop's `continue` port | Evan's live flow does it: `W:Evan/EvanUiPath/EvanAmmFlow/EvanAmmFlow.flow:2712` “shouldTranslate1-false-forEachProvider1-continue” (working tree; that file has an uncommitted diff of `uniqueId` fields). Your simulations have not run it |
| Your own run of a Flow calling a Flow waited (`false`) and the child ran as its own instance | `SIM:CsvProcessor Simulation/README.md:649` “The whole list goes to the child as one value.”; `SIM:CsvProcessor Simulation/HOW_TO_RUN.md:426` “Does a debug run of the parent also run the in-solution child?” (answer Yes, uncommitted text) |

**Decision:** a loop over the data files around `csv-task`, a loop over its rows around the gate and the call, and
the call with `fireAndForget: true`: one main-flow instance per record, and the CSV flow does not wait (D-1). Both
loops are sequential: a parallel loop gains nothing when the call does not wait, and it can show another pass's
value (`L:KT/flow-read-write-contracts.md:145` “in a **parallel** Loop, a body node that produced”).

Per record, not per file: the prompt's §5 asks for one main-flow run per record, and that keeps the main flow's input
one record, the same contract a REST input would produce. Evelyn's records actually join one running main-BP
instance (mapping claim 11), so one main-flow run per file would be closer to Evelyn's runtime; that choice is Q15.

**`fireAndForget: true` is untested anywhere, so your first tenant run is the test** (Q1). Fallbacks, in order:
1. `fireAndForget: false`: still one child per record, but the CSV flow waits for each (D-1 then says "synchronous").
   Risk: a waiting Flow-call node did not release its parent when the child faulted, and has no timeout
   (`W:Isaac/docs/workfusion-parity-differences.md:182` “Running for 3 h with no incident”;
   `L:KT/coded-functions.md:113` “the built-in flow-call node hung for hours when a child job faulted”). That was a
   cross-Solution call; in-Solution is unmeasured. With sequential loops, one hung child would block every later record.
2. The prompt's fallback: pass the file's records to one main-flow run; `csv-schema-producer` makes one transaction per
   record.

Known risks of the decision itself:
- **Concurrency.** The children start seconds apart, each runs one job, and Community runs 3 serverless jobs at once
  (`L:KT/equivalent.md:408` “(Community 3)”). What happens past the cap is undocumented
  (`L:KT/uipath-platform-architecture.md:316` “Past the cap: undocumented.”), and Isaac once found no child job at all
  after a burst (`W:Isaac/docs/workfusion-parity-differences.md:182` “no Evan child job exists”). A lost child is a
  lost record while the CSV flow ends well. So the first CSV run uses at most 3 records, and HOW_TO_RUN counts the
  `EvMigTransaction` rows after it.
- **Error isolation.** In Evelyn one file's failure fails only that file's record. Here a failing `csv-task` stops the
  CSV flow, because a Maestro incident suspends the run
  (`W:OrganisationClassification/docs/uipath-platform-limits.md:25` “A Maestro **incident suspends** rather than fails”). Default: arm `csv-task`'s error port and route it to the file
  loop's `continue`, so the other files go on, and the error stays visible on the node (Q16, D-12).
- **Loop state.** The loop keeps every pass's output in the instance; Isaac once hung on about 12 MB of it
  (`W:Isaac/docs/uipath-loop-parity-and-payload-contract.md:25` “approximately 12 MB of duplicated state”). The mock
  data stays small (DEC-10).
- A faulted child is visible only in its own instance.

## DEC-5 The run context written on each transaction

Evelyn takes these from the WorkFusion task context; a Python function has none of it (D-2).

| Column | Evelyn source | Port source |
|---|---|---|
| `start_bp_uuid` | the **main** BP run's id: `J:utils/ExecutionUtils.java:45` “taskExecutionContext.getBpExecutionUuid()” | the CSV flow's own instance id, `=js:$metadata.InstanceId`, passed to every main-flow run as `bp_run_id`. The producer refuses an empty value. If the id turns out empty at runtime, the prompt's fallback applies: the monitor generates a UUID |
| `bp_start_time` | that run's start time, fetched from Control Tower: `J:utils/ExecutionUtils.java:50` “controlTowerBpService.getBpDetails(bpRunUuid)” | the UTC time `csv-monitor-task` starts, returned in its output as `bp_start_time` (Q3) |
| `dw_variation` | the variation (a configured copy of the worker): `J:utils/ExecutionUtils.java:62` “.map(InstanceConfiguration::getConfigurationId)”, else "" | the job's folder key, from the environment variable the SDK reads (`SDK:constants/__init__.py:18` “ENV_FOLDER_KEY = "UIPATH_FOLDER_KEY"”); "" when absent, Evelyn's own fallback. A Flow could pass `$metadata.FolderKey` instead (`CLI:headless-5kfya4w8.js:205382` “FolderKey: string;”). A deployment folder holds its own configuration file, so it is the closest thing to a variation (**Inference**). In a debug run it is your personal workspace, where the function jobs run, not the `Debug_<Flow>` folder (owner's tenant run, 2026-10-19; Q4) |
| `dw_version`, `model_version` | build properties: `JR:usecase.properties:3` “version=${usecase.version}” (4.5.0-dev), `JR:usecase.properties:5` “ml-model=${usecase.ml-model}” | `evmig-nss`'s version, and the constant `nss-classification-model-v5.3.0` from `E:pom.xml:21` “nss-classification-model-v5.3.0” (Q5) |
| (`provider_id`, not a column) | `input-task.afterRunning`, from `configuration.INPUT_TYPE` (mapping claim 12a) | main-flow input, set to `"CSV"` by the CSV flow (Q2) |

Why the CSV flow's instance id: `$metadata.InstanceId` is the current instance's id
(`CLI:headless-5kfya4w8.js:205384` “InstanceId: string;”, used at runtime by another team:
`W:OWS/workfusion-vs-uipath/2026-09-23-sharepoint-batch/REPORT.md:148` “`$metadata.InstanceId` (capital I)”). The
Flow skill spells it differently (`SKILL:shared/variables-and-expressions.md:441` “`$metadata.instanceId`”), which per
that report is "silently undefined"; AGENTS.md will warn the next AI. In Evelyn the records of a file share one run
id (mapping claim 11), and master selection and wait-for-completion group by (run id, `request_id`). Each child's own
id would put every record in its own group. With the CSV flow's id the group is "this CSV run, this file", which is
what Evelyn's grouping amounts to on this path (**Inference**: in Evelyn one main-BP run can also mix files and REST
requests; nothing on this path depends on that).

## DEC-6 Data Fabric

- **Entities:** `EvMigTransaction`, `EvMigAlertAnalytics`, `EvMigHitAnalytics`, tenant-level, every column of the
  final Liquibase state (mapping §8). You create them with `uip df entities create EvMigTransaction --file
  EvMigEvelyn/entities/EvMigTransaction.create.json` and the like (the Datastore Simulation's format). They are not
  shipped as Solution resources, which have deploy rules of their own (Evan's way; a later step). Tenant scope is the
  shared rule: `W:shared/AGENTS.md:177` “Ship Data Fabric entities tenant-scoped, not folder-scoped.” Your tenant holds
  no `EvMig*` entity today (`uip df entities list`, read-only, run 2026-10-16: `PgStudent`, `PgStudentMark`,
  `SystemUser`).
- **Names:** snake_case columns become PascalCase fields, because field names allow letters and digits only (mapping §8;
  Evan's rule: `W:Evan/docs/data-fabric.md:114` “`amm_articles` became `AmmArticles`”). All names fit the UI's
  30-character limit.
- **Types:** `NVARCHAR(n)` → `STRING(n)`; `NVARCHAR(MAX)` → `MULTILINE_TEXT` with 10,000 characters, because
  `MULTILINE_MAX` must be enabled per tenant (`W:Evan/docs/data-fabric.md:126` “**`MULTILINE_MAX` is a tenant feature.**”);
  `DATETIME2` → `DATETIME_WITH_TZ`, written in UTC (`W:Evan/docs/data-fabric.md:121` “`datetime2` is `DATETIME_WITH_TZ`”);
  `autoQC` and `ticker` → `BOOLEAN`, because Evelyn writes Java booleans into those `NVARCHAR(5)` columns (Q7).
- **Keys:** each table's own uuid is required and unique (Evelyn's only constraint per table). It was `Uuid`; since
  the tenant run of 2026-10-19 it is `TransactionUuid`, `AlertUuid`, `HitUuid`, because Data Fabric refuses `Uuid`
  (D-5). `ClientId` is required with default "1". Evelyn's ten other indexes are not carried (mapping §8.4, D-5).
- **Links:** `TransactionUuid` stays a text field, as in Evelyn; no `RELATIONSHIP` field.
- **Writes, in Evelyn's order** (D-6):
  1. Transaction: find by `TransactionUuid`; if found, update every field, sending absent values as explicit nulls (Evelyn's
     `save` overwrites, mapping claim 15a); else insert. If the insert fails and a second find now returns the row
     (two producers racing), log Evelyn's warning "transaction '<uuid>' already exist" and go on, as
     `J:service/TransactionService.java:75` “} catch (DataIntegrityViolationException ex) {” does.
  2. Alert: find by `TransactionUuid`; insert only if none (as Evelyn).
  3. Hits: find by `TransactionUuid`; insert, in one batch call, the WLEs not stored yet, counting repeated `WleId`s,
     because identical hit ids are legal (mapping §8.3). Evelyn would duplicate them on a retried step (D-7, Q6).

  In Evelyn the alert and hit writes are one database transaction and the transaction row is committed before them;
  here the three writes are separate calls. A failure after step 1 leaves a NEW transaction, as in Evelyn; a rerun
  completes the rows.
- **SDK** (2.14.27): `retrieve_by_name`, `retrieve_records` with a filter group, `insert_record`, `insert_records`,
  `update_record`. The non-`_v3` names, although the source marks them deprecated: the `_v3` twins call a different
  REST root (`SDK:entities/_entity_data_service.py:49` “_V3_RECORD_ROOT”) and call themselves experimental
  (`SDK:entities/_entities_service.py:173` “Experimental v3 surface”), and no code in `W` uses them. Details that
  matter: `update_record` given a model sends only the fields that were set
  (`SDK:entities/_entity_data_service.py:1116` “exclude_unset=True”), so updates send a dict; `retrieve_records`
  returns one page (at most 1,000 rows), so finds pass a limit and page; `insert_records` reports failed rows instead
  of raising (`SDK:entities/_entities_service.py:1448` “fail_on_first”), so the store raises on any failed row. Tests
  use an in-memory fake in the shape of the Datastore Simulation's `FakeEntities`.
- **Budget:** about 9 Data Fabric calls per record (3 entity lookups by name, 3 finds, up to 3 writes), so the first
  3-record run is about 30 calls. The Community plan allows 1,000 a day:
  `L:playground/examples-data-fabric/README.md:102` “1,000 Data Fabric API calls a day”. Whether your tenant is
  Community is not visible to read-only commands.

## DEC-7 The bucket `EvMigFiles` (the S3 stand-in)

- One Orchestrator bucket, declared by a hand-written entry in `bindings.json` of the two functions that use it (the
  monitor and `csv-task`), with `key` equal to the name (`W:shared/docs/uipath-deployment-pitfalls.md:112` “Write the
  key as the bare logical name”). A debug run creates it empty in a `Debug_<Flow>` folder:
  `SIM:CsvProcessor Simulation/HOW_TO_RUN.md:134` “`Debug_StudentIntakeFlow`, not in the workspace itself”.
- **Object keys are Evelyn's whole S3 path**, bucket segment included: `doc-upload/name_sanctions_screening/csv/...`.
  Configuration values keep Evelyn's `bucket/key` shape, so the first segment becomes a top-level folder (D-4).
- **`S3DownloadService`'s behaviour is kept** (mapping claims 4-5): the path must contain `/`, the key must not be
  blank; for the format file and for a data path ending `.csv`, the "bucket" must exist (here: at least one key under
  `<bucket>/`) and then the object; a data path not ending `.csv` lists every key under the prefix at any depth that
  ends in lower-case `.csv`, in lexicographic order, with no bucket check (Evelyn swallows listing errors into "There
  are no csv files in …"); the format file is not excluded; a UTF-8 BOM is stripped; a zero-byte file fails with
  "File <path> is empty". Messages keep Evelyn's `<reason>: <input>` text inside “Exception was thrown by Evelyn NSS
  step <id>: …”; Java's class name in front of it is not reproduced (D-8).
- **Listing, safely.** Orchestrator has answered HTTP 400 to a list prefix that ends in `/`:
  `W:TrClear/TrClearUiPath/TrClearFunction/trclear/platform.py:167` “Orchestrator answers 400 to a ListFiles prefix that
  ends in "/"”, also `W:Edward/EdwardUiPath/PrepareIdpInput/edward_idp_input/bucket_source.py:80` “The folder without a
  trailing slash”. And `list_files` returns one page (`SDK:orchestrator/_buckets_service.py:875` “Returns a single page
  of results”). So the store sends prefixes without a trailing `/`, filters the keys itself, follows the continuation
  token, removes a leading `/` from returned paths, and sorts. The fake refuses a prefix ending in `/`, so tests catch
  a regression. Existence is checked the same way, never with `buckets.exists_file`, which reports present files as
  missing: `W:OrganisationClassification/docs/uipath-platform-limits.md:34` “**Never call `buckets.exists_file`**”.
  Downloads go through a temp file (the SDK has no in-memory download). Before a download the store looks the key up in
  a listing, and a missing key raises `FileNotFoundError` "Please provide correct path to file: <key>": the SDK writes
  whatever the storage answers without checking its status
  (`SDK:orchestrator/_buckets_service.py:455` “file_content = self.custom_client.get(read_uri, headers=headers).content”),
  so a missing file would come back as the storage's error text (added after the review of 2026-10-19).
- **Not reproduced:** three string-handling defects of `S3DownloadService` that only show with odd names: a doubled
  path when the prefix text also appears in the bucket name, a wrong key when the key contains `<bucket>/` again, and
  a failure on very long keys (temp file name) (D-4, Q9).
- **Local runs** use a folder with the same layout (`data/`) behind the same store interface.

## DEC-8 Configuration

- One JSON file, `config/configuration_payload.json` in `EvMigFiles`, nested like Evelyn's payload. The mock holds the
  five keys the three processors read (mapping §7), four of which Evelyn's own payload file lacks. No Credential asset.
- The loader mirrors Evelyn's reader: a required key that is missing fails with “Configuration does not contain
  property '<key>'” (`JsonStringConfiguration.java:31` in the jnw-toolkit 3.0.0.87 sources jar in `~/.m2`); `a.b` is
  read as a nested path, then as a flat key (same file, lines 143-145); booleans accept what the toolkit accepts: JSON
  `true`/`false`, the strings `true`/`True`/`TRUE`/`false`/`False`/`FALSE` (trimmed), and integers (0 is false, any
  other is true). Not "any case": `tRuE`, `yes` and `"1"` are refused. Corrected 2026-10-19: the Phase 0 text said
  "in any case"; the Phase 1 agent ran about 50 documents through the toolkit jar, and the conversion is Jackson's
  (`getRequiredProperty` at `JsonStringConfiguration.java:105` reads through JsonPath with `new JacksonMappingProvider(...)` at line 66).
- Read by the monitor and `csv-task` only; a missing file fails the job (Evelyn has no defaults for these keys either).
- In Evelyn the configuration arrives with every task message; here each job reads the file once (D-3).

## DEC-9 Versions

Python 3.11 (`uv python pin 3.11`), `uv` 0.13.0, `uipath>=2.14.0,<2.15.0` (locks resolve 2.14.27),
`pydantic>=2.10,<3`, pytest as a dev dependency, `uip` 1.203.0. The `.flow` format changes between CLI versions (Evan
pins its CLI: `W:pipelines/evan-deploy.yml:151` “default: 1.200.1”), so the README records the CLI version the Flows
were built with.

## DEC-10 Mock data and tests

- `data/` mirrors the bucket: `config/configuration_payload.json`,
  `doc-upload/name_sanctions_screening/csv/nss_input_format.csv`, and under `.../csv/data/`: two data files at
  different depths, one header-only file (gives `stop`), one `.txt` file (ignored).
- Placeholder names only (Alice Wonderland, John Doe, Gill Bates and spelling variants for aliases and hits). Rows are
  built to make a wrong port fail: an alert whose rows are not adjacent; a blank `input_id`; an alert whose first row
  is invalid (all its rows dropped); a later invalid WLE row (alert kept); a LOCATION hit with `location_wle_enable`
  false; a month-first date that a day-first parser reads differently; two WLEs with the same hit id; a blank line; a
  BOM; headers with odd case and spaces; a `client_id` column. At most 2 alerts per file, and 3 records in the first
  tenant run.
- Every `csv-task` output on the mock data stays under 8,000 characters, checked by a test, because larger job
  outputs may be dropped without an error: `L:KT/equivalent.md:411` “oversized output is silently dropped” (Q8). One
  alert with 4 WLEs is about 3.6 KB (a reviewer's estimate), hence 2 alerts per file.
- Tests port Evelyn's cases one by one, with the fixtures re-created with placeholder names and the same shapes and
  asserted values: `CsvMonitorTaskProcessorTest` (1), `CsvDataServiceTest` (18 methods, 60 assertions),
  `CsvSchemaProducerProcessorTest` (1), and the relevant parts of `TransactionServiceTest` and `AnalyticsServiceTest`.
  As you agreed (Q10, which widens the prompt's list), also the ITs `CsvMonitorTaskProcessorIT` (11),
  `CsvTaskProcessorIT` (9), `CsvSchemaProducerProcessorIT` (1) and `S3DownloadServiceTest` (9), which pin the error
  texts. Plus checks on the `.flow` files, because `validate` checks structure only. Comparisons ignore list order
  where Java uses a `HashMap` (D-8).

## DEC-11 Flows, built only by `scripts/build_flows.sh`

- Child Flow first (its input variables define the call node's fields), then the parent. Commands: `uip maestro flow
  init`, `registry search --local` (node types looked up by name, filtered on `Category`), `node add` (with `--parent`
  for loop bodies), `variable add`, `edge add` (with ports), `validate`, `format`, `validate`. Any edit no command
  can make is a `jq` line inside the script.
- The call node's object and array inputs (`screened_data`, `wle_list`) are written in the object form
  `{"type": "jsExpression", "expression": "...", "fieldType": "object"}`, because `format` once emptied `=js:` object
  inputs of an in-Solution Flow node:
  `W:OWS/workfusion-vs-uipath/2026-09-23-sharepoint-batch/REPORT.md:143` “replaced the object-typed `=js:` inputs”. The script checks them with `jq` after `format`; `validate` would not
  notice.
- The script is checked by rebuilding in an empty folder and diffing the `.flow` files with generated ids ignored.

## Differences these decisions create

As approved. The maintained list, with the differences found while porting (D-13 onwards), is
[differences.md](differences.md).

| # | Difference | Forced by |
|---|---|---|
| D-1 | Records fan out through explicit loops, and each record starts its own main-flow instance; in Evelyn records join the running main-BP instance | Maestro has no record streaming (DEC-4) |
| D-2 | `start_bp_uuid` is the CSV flow's run, not the main flow's; it and `bp_start_time`, `dw_variation`, `dw_version`, `model_version` and `provider_id` come from the CSV flow, the job and the library | no WorkFusion task context (DEC-5) |
| D-3 | The configuration is a bucket file read once per job, holding keys Evelyn's payload file lacks | no Digital Worker configuration service (DEC-8) |
| D-4 | S3 paths become keys of one bucket; "bucket exists" means "a key under that folder exists"; three path defects are not reproduced | buckets are not S3 (DEC-7) |
| D-5 | Data Fabric schema: PascalCase names, `MULTILINE_TEXT` capped at 10,000, UTC times, booleans for `autoQC`/`ticker`, none of Evelyn's ten non-unique indexes | Data Fabric's types and rules (DEC-6) |
| D-6 | The three writes are separate calls; in Evelyn the alert and hit writes were one database transaction | Data Fabric has no transaction across calls |
| D-7 | A rerun does not duplicate hit rows | the prompt asks for it |
| D-8 | Records travel as objects; JSON text details (nulls, HTML escaping, key order), Java's `HashMap` order of aliases, dates, locations and maps, and Java exception class names are not reproduced | no Gson, Jackson or Java in the path |
| D-9 | Logs go to the job log, not Control Tower's event log (texts verbatim) | platform |
| D-10 | The CSV BP's "Final Results" step exports the run's records; the Flow's End node does nothing | no equivalent; nothing in the slice reads it |
| D-11 | `csv-task` runs on the default robot (1 GB, 15-minute cap: `L:KT/coded-functions.md:122` “15-minute hard cap per job; 1 GB memory by default.”), not Evelyn's 4 GB high-memory worker | robot size is set after deploy; the mock files are small |
| D-12 | A failing file is caught by `csv-task`'s error port and the CSV flow goes on to the next file; the failure shows on the node, not as a failed record (Q16: yes) | a Maestro incident would suspend the whole run |

## The prompt's platform facts (§2, §5, §6), checked against files

| Claim | What the files show |
|---|---|
| "Their levels 0-3 were run on the owner's tenant on 2026-10-16" | CsvProcessor and Dependency level 3 are recorded, only in uncommitted edits: `SIM:CsvProcessor Simulation/HOW_TO_RUN.md:14` “Level 3 was run on a tenant on 2026-10-16”. The files still say Datastore and Configuration were not run (`SIM:Datastore Simulation/HOW_TO_RUN.md:14` “haven't been run on a tenant yet.”, `SIM:Configuration Simulation/HOW_TO_RUN.md:14` “Levels 3 and 4 haven't been run on a tenant yet.”). Owner's tenant run, 2026-10-16: Datastore level 3 passed; Configuration level 3 was blocked (next rows) |
| Vendored wheel proved on a tenant | yes, for a wheel without dependencies (DEC-2); and with dependencies, `evmig-nss` 0.1.2 (owner's tenant run, 2026-10-19) |
| Debug-run buckets in `Debug_<FlowName>` | recorded (DEC-7) |
| `flow debug` rewrites the `.uipx` `SolutionId` | recorded: `SIM:CsvProcessor Simulation/HOW_TO_RUN.md:213` “your Studio Web `SolutionId` into `StudentSections.uipx`” |
| A Credential asset with no value blocks every `flow debug` | owner's tenant run, 2026-10-16: every `flow debug` of the Configuration Simulation failed at provisioning with "Username is mandatory for asset type Credential" / "Password is mandatory for asset type Credential". No file records it (Q11). This port declares no Credential asset (DEC-8) |
| `--output-filter` needs an explicit `--limit` | recorded in the CLI's own notes: `SIM:Dependency Simulation/DependencySim/AGENTS.md:483` “explicit `--limit` is required” |
| Data Fabric refuses a dangling RELATIONSHIP ("Relationship violation") and a duplicate unique value ("Value uniqueness violation … 2627") | owner's tenant run, 2026-10-16: "Insert data failed. Relationship violation." and "Insert data failed. Value uniqueness violation. ... Error Number: 2627". No file records them (Q11). The second is the error DEC-6's insert race meets on `TransactionUuid` |
| Debug-run jobs reach Data Fabric as the user | owner's tenant run, 2026-10-16: debug-run jobs wrote to and read from Data Fabric with no role added, and a batch insert returned each new row's Id. Your runbook still shows the question open: `SIM:Datastore Simulation/HOW_TO_RUN.md:414` “Do a debug run's jobs reach Data Fabric as you, with no role to add?” (Q11) |
| A Flow node sends `null` for an unset list input | recorded (DEC-3) |
| Where a debug run's function jobs run | owner's tenant run, 2026-10-19: in your personal workspace (`FolderKey` = the workspace), not in `Debug_<Flow>`. `jobs list` shows their `ProcessName` as ""; `jobs get` shows `ProcessType` "Function", `ServerlessJobType` "PythonCodedFunction" and `ParentJobKey` = the debug output's `.Data.instanceId`. So `UIPATH_FOLDER_KEY`, and `DwVariation`, is the workspace's key (DEC-5) |
| Data Fabric on a debug run's job (Stage A) | owner's tenant run, 2026-10-19: the three entities were created; the producer's job wrote 1 / 1 / 2 rows; the rerun overwrote the transaction in place (`update_record`) and added nothing; `DATETIME_WITH_TZ` took UTC text ending in `Z` and gave it back as `+00:00` (“2026-10-19T06:15:07+00:00” for “…07.000Z”; `StartTime` kept its milliseconds, “…06:15:54.886+00:00”); `records delete` took several ids in one call. It refused the field name `Uuid` first (D-5) |
| Debug runs take 30-70 seconds | one figure recorded: `SIM:CsvProcessor Simulation/HOW_TO_RUN.md:141` “33 seconds on 2026-10-16” |

## Plan

| Phase | Work | Owner (one per project) | Done when |
|---|---|---|---|
| 1 | `evmig-nss`: models, schema utils, configuration loader, bucket store, Data Fabric store, services; their tests; the wheel | one agent | `uv run pytest -q` passes; `uv build --wheel` works |
| 2 | `EvMigCsvMonitorTask`, `EvMigCsvTask`, `EvMigCsvSchemaProducer`: scaffold (`uv`, `uipath new`), code, ported tests, vendored wheel, `bindings.json` | one agent per function, in parallel, after Phase 1 | each `uv run pytest -q` passes; `uv run uipath init` writes `entry-points.json` |
| 3 | `EvMigEvelyn/entities/*.create.json` | me | a `jq` check matches every Liquibase column of mapping §8 |
| 4 | `uip solution init`, `projects add`, both Flows by `scripts/build_flows.sh` | one agent | `validate` with no warnings; `uip solution pack . --dry-run` is Valid |
| 5 | README, HOW_TO_RUN (tests, local run, tenant steps for you), AGENTS.md, `differences.md`, `out-of-scope.md` | me | |
| 6 | Verification in a fresh copy: HOW_TO_RUN levels 1-2 as written; the build script in an empty folder, diffed | a fresh agent | as the prompt's §8 |

Nothing touches a tenant. Read-only `uip` commands only (`validate`, `registry`, `resources list/refresh`,
`pack --dry-run`). The tenant steps in HOW_TO_RUN come in stages, so that one failure points at one cause: first the
main flow alone with one record (Data Fabric from a job, the wheel, `UIPATH_FOLDER_KEY`), then the CSV flow with at
most 3 records (the bucket, the loops, `fireAndForget`, `$metadata.InstanceId`, the object-typed call inputs).

## Open questions (answered 2026-10-19)

You took every default, with two notes: Q11 is cited as "owner's tenant run, 2026-10-16" (the §6 facts table above),
and Q15 is per record while keeping DEC-5's shared `bp_run_id`.

| # | Question | Default (= your answer) |
|---|---|---|
| Q1 | Build the per-record call with `fireAndForget: true`, though no run anywhere has used it, and treat your first tenant run as the test? | yes, with the fallbacks of DEC-4 |
| Q2 | Where does `provider_id` come from? The CSV flow passes `"CSV"` (D-2), or something reads `configuration.INPUT_TYPE` as `input-task` does (a function per record, or the monitor's output) | the CSV flow passes `"CSV"` |
| Q3 | `bp_start_time` = the time `csv-monitor-task` starts (its output gains one field)? | yes |
| Q4 | `dw_variation` = the job's folder key, "" when absent? (Alternatives: always "", or the CSV flow's `$metadata.FolderKey`) | yes. In a debug run that key is your personal workspace's (owner's tenant run, 2026-10-19) |
| Q5 | `dw_version` = `evmig-nss`'s version; `model_version` = Evelyn's `nss-classification-model-v5.3.0`, though no model runs yet? | yes |
| Q6 | Rerun rules: transaction overwritten (as Evelyn), alert written once (as Evelyn), hits completed without duplicates (Evelyn duplicates)? | yes |
| Q7 | `NVARCHAR(MAX)` → `MULTILINE_TEXT` 10,000 (not the tenant-gated `MULTILINE_MAX`), and `autoQC`/`ticker` → `BOOLEAN` (not `STRING(5)` holding "0"/"1")? | yes |
| Q8 | Records travel inside Flow variables; job outputs above 10,240 characters may be dropped silently. Keep the mock files small (checked by a test) and move real-size files to a bucket-path ("claim-check") design later, listed in `out-of-scope.md`? | yes |
| Q9 | Reproduce Evelyn's observable quirks (format file listed as data, blank lines as empty records, case-sensitive `.csv`, an error on a duplicate client column in the format file), but not the three path-string defects of DEC-7? | yes |
| Q10 | Port the ITs as well (`CsvMonitorTaskProcessorIT`, `CsvTaskProcessorIT`, `CsvSchemaProducerProcessorIT`, `S3DownloadServiceTest`)? They pin the error texts; the prompt names only the unit tests | yes |
| Q11 | Three facts in your §6 are in no file: the Credential asset blocking debug runs, the two Data Fabric error texts, and debug-run jobs reaching Data Fabric as you (your runbook still lists that one as open). Were they seen in a session that left no notes? May I cite them as "owner's observation, 2026-10-16"? | cite them as "owner's tenant run, 2026-10-16" (your answer, with the facts now in the §6 table) |
| Q12 | Evelyn pins contract `4.4.0`, which is not on this machine; you chose `ffc12d6` (a feature branch, content not in the clone's `origin/master`). Treat them as equal for `ScreenedData`/`WleData`? You can check with `git fetch --tags` in the contract repo, then diff `nss-schema-contracts-4.4.0` against `ffc12d6` | treat as equal |
| Q13 | Vendored wheel (DEC-2) rather than Evan's copy-and-test? | wheel |
| Q14 | Functions raise on errors, as Evelyn's steps do (DEC-3), rather than return the error in their output as the other ports do? Raising is safe with fire-and-forget; it would hang a waiting parent (DEC-4 fallback 1) | raise |
| Q15 | One main-flow run per record (the prompt's §5; the main flow takes one record, like a future REST input), or one per file (closer to Evelyn's shared main-BP run; the main flow would loop)? | per record, keeping DEC-5's shared `bp_run_id` (your answer) |
| Q16 | Arm `csv-task`'s error port so a failing file does not stop the other files (D-12)? | yes |

## Since approval (2026-10-19, Phases 1-5)

What the build added or changed against the approved text above. Nothing here changes a decision; Q17 was asked and
answered after the build.

| What | Where |
|---|---|
| DEC-8's boolean rule corrected (Jackson's, not "any case") | DEC-8 above |
| A listing failure of the SDK is swallowed as Evelyn swallows AWS errors; mapping claim 5 narrowed to "raised by the AWS SDK" | D-4 in [differences.md](differences.md) |
| D-13 to D-17 found while porting (date parser, configuration reader, integrity errors, two Java failure paths, input checks) | [differences.md](differences.md) |
| Local runs: one switch in the library, `evmig_nss.core.sdk.get_sdk()`. With env `EVMIG_LOCAL_BUCKET_DIR` it serves the bucket from a folder (`data/`) and keeps Data Fabric rows in memory or in the JSON file named by `EVMIG_LOCAL_DATAFABRIC_FILE`; otherwise it creates `UiPath()` on first use. The test fakes (`evmig_nss/testing.py`) ship in the wheel so the three functions reuse them | HOW_TO_RUN level 2 |
| `uipath` locked at 2.14.27 in all four locks (DEC-9) | each `uv.lock` |
| Layout additions to DEC-1: `scripts/entities.py` (generates and checks the entity files from mapping §8, used instead of a `jq` check), `scripts/normalize_flow.sh` (blanks generated ids to diff two Flow builds), `data/README.md` | README "Layout" |
| Order: `uip solution init` was run before Phase 2, because function projects are created inside the Solution folder; Phase 3 ran while Phase 1 was in progress | |
| After the owner's first A1 (2026-10-19): each entity's own uuid field renamed from `Uuid` to `TransactionUuid`, `AlertUuid`, `HitUuid`, because Data Fabric refuses `Uuid`; `evmig-nss` 0.1.2 | D-5, DEC-6 "Keys", mapping §8 |
| After Stage A passed (2026-10-19): HOW_TO_RUN finds function jobs in the workspace by their parent run, B4 waits on the transaction count, `DwVariation` is the workspace's key | DEC-5, Q4, the facts table above |
| The Flows: no `jq` edit was needed. `rest_request` stays on the producer node with the CLI's default; the compiled job arguments leave it out, and the producer accepts "" anyway. The call node compiles to `Orchestrator.StartFlowProcessAsync` (seen in `uip maestro flow pack` output, not only in the CLI source) | `scripts/build_flows.sh` |

**Q17 (new).** The "NSS-main-BP" call node's error port is not armed, as approved. If a child run fails to start, the
call raises a Maestro incident, and that suspends the whole CSV flow run, so the remaining records wait. In Evelyn an
error answer to the BP call fails only that record's step (mapping claim 11). Arming the port to the record loop's
`continue`, as Q16 did for `csv-task`, is one more `edge add` line in `scripts/build_flows.sh`; the research build
validated it. Arm it? Default: **yes**.

**Answered 2026-10-19: yes.** Applied in `scripts/build_flows.sh`, both Flows rebuilt (the child is unchanged; the
parent gained only the error edge and `errorHandlingEnabled` on `nssMainBp1`), re-verified: both `Valid` with no
warnings, `pack --dry-run` `Valid`, the rebuild in an empty copy identical, and the packed BPMN has
`BoundaryEvent_nssMainBp1_Error` next to `BoundaryEvent_csvTask1_Error`. Recorded as D-18.

## Seen while reading (for you, not for this port)

- A committed Evelyn test fixture holds an `Authorization` header with a bearer token:
  `E:names-screening-jnw/src/test/resources/input/streaming-api-input.json` (not opened by me, not copied anywhere).
  Worth telling the Evelyn team.
- Your untracked notes in `E/notes_files/` disagree with the code in about 40 places (wrong config key paths, Java 17
  instead of 21, processor base classes, the OBP signal id). The code was used throughout. The fix list, with
  `path:line` on both sides, is [notes-files-review.md](notes-files-review.md).
