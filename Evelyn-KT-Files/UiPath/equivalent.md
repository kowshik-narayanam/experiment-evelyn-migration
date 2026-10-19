# WorkFusion → UiPath equivalents, through the Evelyn lens

**Purpose:** any AI agent or person can use this file to rebuild the mapping without the original chat. It has two parts:

- **Term by term:** a WorkFusion ↔ UiPath dictionary covering tools, building blocks, runtime, data, packaging and code. It also separates UiPath look-alikes, such as App vs Coded App.
- **Platform mechanics (§1–§12):** how each WorkFusion concept Evelyn relies on works on UiPath, and how the other ports handled it.

**How it was built:** a read-only review of the Evelyn product, the UiPath ports, and public UiPath docs. Nothing was run against a tenant or WorkFusion. Labels: **Inference** = a reasoned guess; **Unconfirmed** = the docs are unclear or the evidence is an absence; **unknown** = no evidence.

`BP[Name]` means that business process's `project.xml`. Zip names use `+` for spaces, for example `Names+Screening`, `Names+Screening+QC+Report`, `CSV+File+Ingestion`.

---

### Tools and consoles

| WorkFusion | UiPath | Note |
|---|---|---|
| Control Tower | **No single equivalent**, split across the rows below | The biggest mental shift |
| Control Tower BP designer | Studio Web (Flow designer) | Coded functions are written locally, not in Studio Web |
| Control Tower run monitoring | Maestro (Flow instances) and Orchestrator → Jobs | |
| Control Tower deploy, secrets, files, schedules | Orchestrator: processes, assets, storage buckets, triggers | |
| Control Tower users and roles | Automation Cloud admin (users, groups), plus Orchestrator folder roles | |
| Manual-task inbox | Action Center | |
| WorkFusion environment (e.g. `dw-isaac-23`) | Automation Cloud **organization → tenant → folder** | Practice org `uipatqejfxxi` / `DefaultTenant`; staging `uipathstgSS_updated` |
| IntelliJ plus a Maven worker project | Any editor plus the `uipath` CLI (coded functions); Studio Web (Flows) | |
| WorkFusion SDK services (`SecretService`, `S3Service`, `TaskConfigurationProvider`) | The `uipath` Python SDK: `sdk.assets`, `.buckets`, `.processes`, `.jobs`, `.entities` | |

### Building blocks

| WorkFusion | UiPath | Note |
|---|---|---|
| Digital worker (Isaac, Evelyn…) | Solution (`.uipx`) | One worker can be several Solutions; Isaac's providers each have their own |
| Skill (e.g. Isaac's TMI) | A Flow or a group of Flows in the Solution | **Inference** |
| Business process (BP) | Maestro Flow (`.flow`) | Isaac: 10 BPs became 15 Flows |
| Bot task / machine task (a BP step) | Flow node running a coded function (`uipath.core.function.<key>`) | Each node run is an Orchestrator job |
| Task processor (`@TaskProcessor` class) | Coded function, or one `operation` inside one | Isaac packs about 70 operations into one function |
| Human task step | Human-in-the-loop (HITL) node, which creates an Action Center task | |
| Manual-task UI (React, e.g. `nss-dw-mt`) | Coded action app | Isaac `ActionTaskApp` |
| Rule node / gateway (Drools, MVEL) | Decision or Switch node | |
| Embedded sub-BP | Subflow node (`core.subflow`) | Isaac used separate Flows instead |
| Call activity / `BP_CALL` | Flow-calls-Flow node (`uipath.core.flow.<key>`) | Across Solutions: start a job and poll (§2) |
| Records fanning out (a step emits many rows) | Loop node, or a batch inside one function | WorkFusion steps process many records at once; a Flow instance carries variables, so you loop explicitly (**Inference**) |
| Signal id | Process name, release key or API trigger URL | §1 |
| REST input connector | API trigger | §4 |
| Form.io configuration page | Coded app (Evan's `EvanConfigurationApp`) or assets | |

### Runtime

| WorkFusion | UiPath | Note |
|---|---|---|
| Java Native Worker (long-running Spring Boot app) | Serverless robot. Each run is a fresh job | About 50 s cold start; no warm server to rely on |
| `@WorkerProfile("high-memory")` | Robot size (memory tier), set on the process in Orchestrator | Can't be set from the package |
| BP run / instance (`bpUuid`) | Flow instance (Maestro), with a job key per job | |
| One task execution | One Orchestrator job | |
| `reprocessAfter(n)` | A wait or poll loop inside the function | 15-minute cap per job; never a Flow Delay node (§8) |
| Step retry with attempt limit | A node's error port plus retry logic in the function; queue auto-retry | |

### Data, files, config, secrets

| WorkFusion | UiPath | Note |
|---|---|---|
| Datastore (MSSQL `ds_uc_…` tables) | Data Fabric entities (formerly Data Service) | Decision still open (§7) |
| Liquibase | Entity JSON committed in the Solution, plus scripts | No migration runner (§7) |
| S3 | Storage bucket | Can be backed by Amazon S3 (§5) |
| Vault | Secret or Credential asset | |
| Zookeeper, `configuration.json` | Text asset, or a JSON file in a config bucket | Isaac: `isaacConfig.json` in a bucket |
| Python Bridge / AutoML model | Model files in a bucket, run in a child Python process | Evan, OrgClas |
| Variation (a configured instance per customer) | A Solution deployment in its own folder, with its own assets and config | **Inference** |

### Packaging, deploy, tests

| WorkFusion | UiPath | Note |
|---|---|---|
| `pom.xml` | `pyproject.toml` | |
| Maven (`mvn dependency`) | `uv add` or `pip install` | |
| `mvn package` → `.jar` | `uipath pack` → `.nupkg` | |
| Asset bundle | Solution package | |
| Bundle import (Jenkins) | `uipath publish` (one function) or `uip solution deploy` (a whole Solution) | The repo runs it in Azure DevOps |
| Bitbucket Pipelines | Azure DevOps pipelines, GitHub | |
| JUnit | pytest | |
| Spoke integration tests | Offline pytest parity suites, plus live e2e (`shared/e2e/`) | |

### Observing

| WorkFusion | UiPath | Note |
|---|---|---|
| Elastic APM, worker logs | Job logs in Orchestrator, the Maestro instance view, traces | |
| Superset dashboards | **None.** UiPath Insights covers job metrics only | **Inference** |
| Polling `RequestStatus` | Job status, or an API trigger's status URL | |

### Code: a Java task processor vs a Python coded function

| WorkFusion Java processor | Python coded function |
|---|---|
| `@TaskProcessor(id = "group-alerts-processor")` on a class | An entry in `uipath.json`: `"functions": {"main": "main.py:main"}` |
| `process(inputData)` | `def main(input: EchoIn) -> EchoOut` |
| Input: `JnwJsonInputData` / `in-contract.yaml` | An input class (`@dataclass` or Pydantic `BaseModel`), e.g. `EchoIn` |
| Output: `TaskOutputData` / `out-contract.yaml` | An output class, e.g. `EchoOut` |
| Hand-written contract YAMLs | `entry-points.json`, **generated** from those classes by `uipath init` |
| Many processors in one worker jar | One function with an `operation` input that dispatches |
| SLF4J `log.info(...)` | `logging.getLogger(__name__).info(...)`; shows in the job logs |
| `throw new …Exception` | `raise`, which faults the job. The ports instead return `errorType` / `errorMessage` in the output |
| `SecretService` (a Vault alias) | `sdk.assets.retrieve_credential(...)` / `retrieve_secret(...)` |
| `S3Service.upload(...)` | `sdk.buckets.upload(...)` |
| `TaskConfigurationProvider.getDigitalWorkerConfiguration` | Read a config JSON from a bucket (Isaac), or assets |
| `@SendResultToCaller(true)` | The child Flow's End node output |
| `reprocessAfter(120)` | A loop with `time.sleep` inside the function, under 15 minutes |
| Spring `@Autowired` services | Plain Python modules and imports; no DI container |
| `application.yml` | `.env` locally; assets in the cloud |

### Tracing a Flow node to its code

Line numbers below are from `main` @ `a223e56d`.

In WorkFusion a bot step points at a `@TaskProcessor` class, one class per file. In the ports a
node ID only names the node inside the Flow graph; it is not a file name. Follow two fields of the
node instead. Example: Isaac's `dataValidationTaskProcessor1` in

| Step | Where | What you find |
|---|---|---|
| 1. The node's `type` | The node in the `.flow` | `uipath.core.function.b92ad16a-…`. Its `definitions` entry has `projectName: IsaacWorkflowFunctions`: the function project the node runs |
| 2. The node's `operation` input | `inputs.operation`; on the canvas, Properties → **Parameters** (not Advanced) | `"data-validation"`, the counterpart of `@TaskProcessor(id = …)` |
| 3. The entry point | | `"main": "main.py:main"`; every operation enters at `main.py:66` |
| 4. The dispatch table | (`OPERATIONS`) | `"data-validation": _op_validate_transactions` (`:3213`) |
| 5. The handler | `dispatch.py:1844` | Calls `validate_entity_transactions` |
| 6. The logic | | The port. Its comment cites `DataValidationTaskProcessor at 8c64a2460 (:39)` |
| 7. The Java original | | `@TaskProcessor(id = "data-validation-task-processor")`; the checks at `:35-36`, `recordError` at `:39` |

| WorkFusion | The port |
|---|---|
| A step in the BP's `project.xml` (graph node 318) | Flow node `dataValidationTaskProcessor1` |
| Worker jar `dw-isaac-tmi-jnw`, many processors | Function project `IsaacWorkflowFunctions`, about 70 operations |
| `@TaskProcessor(id = "data-validation-task-processor")` | The key `"data-validation"` in `OPERATIONS` |
| Spring finds the processor by its id | A Python dict lookup |
| `DataValidationTaskProcessor.process`, one class per file | `_op_validate_transactions` → `validate_entity_transactions`, functions in shared modules |

- **Shortcut:** has one row per WorkFusion BP node, with its
  UiPath project and node ID.
- **Search for** the operation name in quotes (`"data-validation"`) or the Java class name in `*.py`;
  the ports cite the Java class in comments. The node ID only finds the `.flow` and the tests.
- **The `1` suffix** counts instances in one Flow; `IsaacAlertInvestigationFlow` has its own
  `dataValidationTaskProcessor1`.
- **Read `.flow` files in a text editor** (Reopen Editor With → Text Editor). On the
  Maestro canvas extension rewrote this `.flow` while it was open: 33 lines, one of them a binding
  replaced by an empty object, as.

### UiPath look-alikes (don't mix these up)

| These two | Difference | Used in the ports? |
|---|---|---|
| **App** vs **Coded App** | Low-code drag-and-drop app built in Studio Web vs React/TypeScript on the UiPath TypeScript SDK | Coded apps only |
| **Coded App** vs **coded action app** | A general web app vs the screen for one Action Center task | Both |
| **Coded function** vs **coded agent** | Deterministic code, no LLM vs an LLM-driven Python agent (LangGraph, LlamaIndex, OpenAI Agents) | Functions; agents only in POCs |
| **Agent** (low-code) vs **coded agent** | `agent.json` built in Agent Builder vs Python code. Both use an LLM | POC only |
| **Coded function** vs **API workflow** | Python code vs a JSON-defined workflow with JavaScript steps | Functions. API workflows only in the Isaac POC, with a practical 10-minute limit |
| **RPA workflow** (`.xaml`) vs **coded workflow** (`.cs`) | Visual vs C#. Both run on a robot, mostly for UI automation | 2 small XAML robots |
| **Maestro Flow** vs **Maestro BPMN** vs **Maestro Case** | Simple visual graph vs standard BPMN process ("agentic process") vs long-lived case management with stages | Flow |
| **Orchestrator** vs **Maestro** | Runs and manages everything (jobs, assets, buckets) vs orchestrates and watches long-running processes | Both |
| **Studio** vs **Studio Web** | Desktop Windows IDE vs browser IDE | Studio Web |
| **Process** vs **job** vs **Flow instance** | A published runnable package vs one run of it vs one run of a Flow, which starts jobs for its nodes | All |
| **Data Service** vs **Data Fabric** | The same product, renamed | OrgClas cache |
| **`uipath`** vs **`uip`** CLI | The Python SDK's CLI for one coded project (`new`, `init`, `run`, `pack`, `publish`) vs UiPath's general CLI (Solutions, Flows, Orchestrator) | Both |
| **Storage bucket** vs **asset** | Files vs named values (text, secret, credential) | Both |
| **Queue** vs **job** | Work items waiting to be processed vs runs of a process | Jobs only |
| **My Workspace** vs **folder** | Your personal folder, where debug runs land vs a shared folder that a Solution deploy creates | Both |

---

## Platform mechanics: summary

| WorkFusion (as Evelyn uses it) | UiPath equivalent | Done in a port? |
|---|---|---|
| Business process (BP) | Maestro Flow | Yes, Isaac: 10 BPs became 15 Flows |
| Bot step / task processor | Flow node running a Python coded function (`uipath.core.function.<key>`) | Yes, everywhere |
| Signal id (a BP's address) | No address layer: call the process by name or release key, by an API trigger URL, or by project key in a Flow node | Yes, Isaac keeps provider process names in config |
| BP_CALL, synchronous | Flow-calls-Flow node with `fireAndForget: false` (same Solution), or start a job and poll (cross-Solution) | Yes, Isaac |
| BP_CALL, asynchronous | Start a job with `processes.invoke`: you get a **job key** right away, which you can poll later. A Flow node with `fireAndForget: true` also works, but whether it returns any id is undocumented | Start-then-poll: Isaac. `fireAndForget: true`: never used |
| `sendResultToCaller` | The child Flow's End output, read as `$vars.<node>.output` | Yes |
| Embedded sub-BP (SubStart/SubEnd) | Inline subflow (`core.subflow`), or a separate Flow project | Isaac used separate Flows; inline only in an old POC |
| REST input connector (`start-record-raw`, then poll status and result) | API trigger, AsyncRequestReply mode | **No** |
| `execute-record-raw` (synchronous) | API trigger, LongPolling mode (15-minute cap) | **No** |
| CSV ingestion from S3 | Input bucket, plus a function that sweeps it, plus a time trigger | Yes, `IsaacFlow` |
| `reprocessAfter(n)` waits and retry loops | Poll inside a function (15-minute job cap). **Not** a Flow Delay node | Yes, Isaac |
| S3 (`S3Service`) | Orchestrator storage bucket (can be backed by Amazon S3) | Yes, everywhere (Orchestrator-stored) |
| MSSQL tables (state) | Data Fabric entity (formerly "Data Service") or bucket files | Partly. Undecided across teams |
| DB cache tables | Data Fabric entity | Yes, OrgClas |
| Spring in-memory cache | Process memory of a warm serverless robot (best effort) | Yes, OrgClas model load |
| Liquibase schema migrations | **No equivalent.** Declarative entity JSON in the Solution, plus scripted `addFields` | Yes, OrgClas |
| Liquibase seed CSVs (reference data) | Files bundled read-only in the function package, or a JSON file in a config bucket | Yes, Evan and Isaac |
| Vault (`SecretService`) | Orchestrator Secret or Credential asset | Yes |
| `configuration.json` (Form.io settings page) | Coded Web App that edits a JSON document in a config bucket ([§13](#13-the-configuration-page-and-the-decision-rules-matrix)) | Yes, Evan's `EvanConfigurationApp`; Isaac's config JSON |
| Decision-rules matrix (`model.rules`) | Rows kept as data in the config JSON, evaluated in Python next to the ported model. Orchestrator Business Rules (BPMN, Preview) not recommended yet | **No** |
| Manual task (`nss-dw-mt`) | Human-in-the-loop node with a coded action app (Action Center) | Yes, Isaac `ActionTaskApp` |
| `bpUuid`, `request_id` | Job key, plus your own request id passed as an input | Yes, Isaac |
| Superset dashboards | None | **No** |
| Control Tower | Orchestrator (run and manage), Studio (design), Maestro (watch Flow runs) | — |

---

## 1. Signal id

- **WorkFusion:** a named address for a BP. A BP declares `<externalSignalId>`. A `BP_CALL` step (`bp-call-event`) sends a `signalId` and a `synchronous` flag, and the platform starts the BP that listens on that id.
  - Listeners: the main BP listens on `nss-signal-id` (`BP[Names Screening]:13141`). QC listens on `qc-signal-id` (`BP[Names Screening QC Report]:570`).
  - Senders: CSV → `nss-signal-id`, async (`BP[CSV File Ingestion]:396-397`). Main → `qc-signal-id`, sync (`BP[Names Screening]:11815-11816`). Main → `nss-custom-enrichment` (`:10952`) and → `tr-clear-adhoc-search` (`:10153`). No BP in the bundle listens on those last two.
  - It only routes; it is not a correlation or idempotency key. `duplicationProtection` is false (`BP[Names Screening]:10954`). Tests give each test its own signal id.
- **UiPath:** there is no indirection layer. You address the process directly:
  - by process name: SDK `processes.invoke(name, args, folder_key)`;
  - by release key: `POST /odata/Jobs/UiPath.Server.Configuration.OData.StartJobs`;
  - by an API trigger URL;
  - for Flow → Flow, by the child's project key in a `uipath.core.flow.<key>` node.
- **Precedent:** Isaac keeps each provider's process name in config, the closest thing to a signal id.

## 2. BP ↔ BP communication

- **WorkFusion:** a BP_CALL to a signal id, sync or async. The callee's step flagged `sendResultToCaller=true` returns its output to the caller step (`BP[Names Screening QC Report]:103-104`). Main passes `bp_uuid` to QC, which makes QC run in automatic mode.
- **UiPath, same Solution:** a Flow-calls-Flow node `uipath.core.flow.<projectKey>` (service type `Orchestrator.StartFlowProcess`).
  - `"fireAndForget": false` means it waits for the child. The child's End output comes back as `$vars.<node>.output`.
  - Isaac has 16 such nodes; 7 are in `IsaacTransactionMonitoringFlow`.
- **UiPath, another Solution or worker:** a function starts the job and polls it.
  - Start with `processes.invoke`, poll with `jobs.retrieve` every 5 s for at most 120 s per call, and read the result with `jobs.extract_output`.
  - A failed child is restarted, up to `provider-max-attempts = 5` (`provider_jobs.py:460-490`).
- **Fire-and-forget and tracking the result later:**
  - `processes.invoke` returns a Job straight away. Its `key` is the tracking handle (≈ WorkFusion's REST `requestId`). Isaac stores it as `requestId`, then polls in a separate call (`provider_jobs.py:274-290,353`).
  - A Flow-calls-Flow node with `fireAndForget: true` is **unknown territory**. All 34 `fireAndForget` values set in the repo's Flows are `false`; the other 2 matches are schema definitions. The node's declared outputs are only `output.result` and `error`. No doc says it returns a job key or instance id; check by inspecting the node output in a debug run.
  - An API trigger in FireAndForget mode returns 200 with nothing to track. AsyncRequestReply returns a status URI instead ([call modes](https://docs.uipath.com/orchestrator/automation-cloud/latest/user-guide/call-modes-explained)).
  - Ways to get the result without the job key:
    - the child writes it to a bucket, or to a Data Fabric row;
    - job webhooks (`job.completed` / `job.faulted`), best effort and **Unconfirmed**;
    - a Maestro custom instance ID set to your request id, to find the run in the instance list.
  - Evelyn's only async call (CSV → main) never reads the main BP's result. Results go to reports, and status to `RequestStatus`.
- **Don't** use a cross-Solution Flow node that waits on the child. It has no timeout and hung for 3 h when the child faulted (D31; `provider_jobs.py`).
- **BPs that only share tables:** Ticker Lookup and Aggregated Analytics are never called. They rewrite DB tables that the main BP reads . How they start is unknown; the BP XML has no schedule. The UiPath equivalent would be a shared bucket file or entity, written by a Flow on a time trigger (**Inference**).
- **`RequestStatus`:** a row per transaction and request, with status FINISHED / ERROR / READY_FOR_MT / MT_COMPLETED. No Java code reads it, so it is polled from outside (**Inference**).

## 3. Sub-BPs (BP inside BP)

- **WorkFusion:** the main BP embeds 7 sub-processes:
  - Screening Systems, which contains Firco Trust Screening (`BP[Names Screening]:12643`) and Thomson Reuters Provider (`:12552`);
  - Data Enrichment, which contains Address Enrichment;
  - Names Classification Model;
  - Names Screening Human-in-the-loop.

  It also calls BPs by signal: custom enrichment (`:12407`), TR (`:12604`) and QC (`:13104`). The CSV BP has a `ProcessCall` to the main BP (`BP[CSV File Ingestion]:740`).
- **UiPath:**
  - Inline subflow `core.subflow`: its own variable scope, explicit inputs and outputs, nests up to 3 levels ([docs](https://docs.uipath.com/maestro/automation-cloud/latest/user-guide/subflows)).
  - Or a separate Flow project, called with a Flow-calls-Flow node.
- **Precedent:** Isaac turned every WorkFusion `process_call` or `call_activity` into a separate Flow project (rows 6, 10, 28, 46, 50, 59-65). Inline subflows appear only in the abandoned POC.
- **Gotchas:**
  - WorkFusion's implicit BP context must become explicit bound inputs.
  - A Studio refresh once replaced those bindings with empty objects without warning (`:158-170`).
  - Many child executions in one long run trigger a Maestro bug: the run stops with no incident (D32).

## 4. Input channels

| Evelyn channel | How it works in WorkFusion | UiPath equivalent | Done in a port? |
|---|---|---|---|
| REST input connector | Main BP input type `EXTERNAL_CONNECTOR` (`BP[Names Screening]:13143`). Records carry `rest_request` and `_sys_ext_record_id`. Response built by `SendResultsBackToCallerProcessor` | **API trigger** ([call modes](https://docs.uipath.com/orchestrator/automation-cloud/latest/user-guide/call-modes-explained)). AsyncRequestReply returns 202 plus a status URI, then a 303 redirect to the output (≈ start / check / get). LongPolling is synchronous with a 15-minute cap. Async callback was **removed**, so use polling or job webhooks | **No.** OWS dropped its HTTP façade. Isaac's `IsaacRestFlow` reads one named JSON file instead |
| CSV File Ingestion BP | `csv-monitor-task` emits a row per S3 CSV, `csv-task` a row per alert, then an async BP_CALL to the main BP | Input bucket, plus a sweep function, plus an Orchestrator **time trigger**. No bucket "file arrived" trigger is documented (**Unconfirmed**), and the AWS connector has no events | **Yes:** `IsaacFlow` sweeps all prefixes and moves consumed files to `isaac-ingested/<date>/<run>/` |
| Firco batches | `download-firco-messages` polls the client's Firco Trust Case Manager API over SOAP and saves to `firco_messages`. `firco-messages-batch` emits up to 1000 rows plus a retry row that loops after `reprocessAfter` | A function that loops and waits within the 15-minute cap, or an Orchestrator **Queue** (unique `Reference`, auto-retry for application exceptions, 1–50 retries) (**Inference**) | Waiting inside a function: Isaac. Queues: none |
| Called by another BP | An async or sync BP_CALL to `nss-signal-id`. No `rest_request` means an internal call | A parent Flow node, or `processes.invoke` | Yes, Isaac → providers |

- **Triggers in the ports today:** every Flow uses `core.trigger.manual`. No queue, time, event or API triggers are declared in any Solution.
- **Trigger types available:** time, queue, event (Integration Service) and API ([about-triggers](https://docs.uipath.com/orchestrator/automation-cloud/latest/user-guide/about-triggers)).

## 5. S3 → storage buckets

- **Evelyn's S3 use:** the platform `S3Service`, which wraps AWS SDK v1 .
  - QC **writes** CSV parts to `name_sanctions_screening/QC_Reports/…`. Its data comes from the `QcReportData` table, not from S3.
  - `send-results-back-to-caller` can read the QC CSV back to inline it (`SendResultsBackToCallerProcessor.java:217-219`).
  - The bucket name comes from `configuration.report_bucket`, default `doc-upload`.
  - Also stored in S3: HTML reports, CSV inputs and Firco format files. The ML model is pulled at build time.
- **UiPath storage buckets:**
  - Providers: Orchestrator, Azure, **Amazon S3** (access key or Integration Service connection, SSE-KMS) and GCS ([about-storage-buckets](https://docs.uipath.com/orchestrator/automation-cloud/latest/user-guide/about-storage-buckets)). The Python code is the same whichever provider backs the bucket.
  - Python access: `sdk.buckets.upload / download / list_files / delete_file`.
  - Isaac addresses buckets by role (INPUT, WORKING, RESULT, DEFERRAL, CONFIGURATION, STORE), mapped through `bindings.json`.
  - No port uses boto3. Raw boto3 with a credential asset would work but loses folder permissions and auditing (**Inference**).
- **Gotchas:**
  - `buckets.exists_file` reports existing files as missing.
  - Buckets are folder-scoped, so a debug run sees empty debug-folder buckets.

## 6. Caches

- **Evelyn:**
  - The Factiva search cache, `ds_uc_B_AML_PEP_search_cache_v3_0`, is optional.
  - The Factiva alert cache, `…alerts_cache_v3_0`, is keyed by PEID and refreshed when the revision changes.
  - Neither has a TTL or a purge.
  - Spring `@EnableCaching` keeps in-memory maps for the life of the worker (Firco format files, the WC1 toolkit).
  - `purge-datastore-task` does **not** touch caches.
- **UiPath:** no cache service is documented (**Unconfirmed**).
  - DB caches → a **Data Fabric entity**. OrgClas folded 2 SQL tables into 1 entity, `OrgClasEntitySearchResult`. It reads candidates with a `contains` filter and re-applies the JPQL ordering in Python.
  - In-memory caches → globals in a warm serverless robot, best effort only (**Inference**). OrgClas loads its NER model once per warm function.

### Status

- No cross-team decision was recorded at that sync. The owner read Slack's main timeline, not the threads.
- **Data Service = Data Fabric**, renamed ([release notes](https://docs.uipath.com/data-service/automation-cloud/latest/release-notes/june-2025)). The connector key is still `uipath-uipath-dataservice`.
- Why Isaac moved off it:
  - an admin had to create the entity out of band, while buckets are provisioned on import;
  - `MULTILINE_TEXT` holds at most 10,000 characters;
  - it added a connection prompt at deploy time.

  Isaac's config now lives in a bucket JSON (`isaacConfig.json`), and its deferral table in the `IsaacStore` bucket.

### Data Fabric limits

From [enabling-the-data-service](https://docs.uipath.com/data-service/automation-cloud/latest/user-guide/enabling-the-data-service) and:

- 200 fields per entity.
- 1,000 records per query or batch call.
- 5,000 API calls per minute per tenant.
- 10K API calls per day per Enterprise licence unit.
- STRING holds up to 4,000 characters, MULTILINE_TEXT up to 10,000, and MULTILINE_MAX about 65K (not filterable).
- Field names must be alphanumeric; a solution deploy rejects `_`.

### Evelyn tables

`ds_uc_B_AML_PEP_` prefix. UiPath homes are **Inference**.

| Kind | Tables | Likely UiPath home |
|---|---|---|
| Reference and config | `tickers`, `countries`, `us_states`, `firco_configuration`, `configuration` | Bundled files or a config-bucket JSON |
| Cache | `search_cache`, `alerts_cache` | Data Fabric entity |
| Per-run scratch (purged) | `master_record`, `firco_retry_monitor` | Bucket files keyed by job key; may disappear in a redesign |
| **Real state** | `transaction`, `qc_report_data`, `request_status`, `firco_messages` | **The open decision** |
| Analytics | `alert_analytics`, `hit_analytics`, `aggregated_analytics` | No precedent (Superset reads these) |

`master_record` picks one leader per run with a unique-constraint insert. Data Fabric has `isUnique`, but it can only be set when the field is created.

### Liquibase → no equivalent

UiPath has no versioned migration runner. Three cases, each with what the ports did:

1. **Schema (DDL changesets) → declarative entity JSON plus scripts.**
   - The entity definition is committed in the Solution at, so a deploy creates the table complete.
   - `uip solution pack` alone emits an empty schema, which gives a table with **no columns**. OrgClas commits the file, generates it from, and pins it with a contract test.
   - Changing an existing table is scripted: re-running `create_cache_entity.sh` adds only missing columns (`addFields`, non-destructive). When the entity already exists, the deploy adopts it with `deploy.sh --use-existing` (`conflictFixingAction: UseExisting`).
   - **Inference:** a deploy creates a table but doesn't migrate an existing one.
   - **Not supported**:
     - changing a field's type;
     - renaming an entity;
     - toggling `isUnique`. The call returns Success but is silently ignored.

     Removing a field drops its data. The only path for these changes is "add a new field or entity, then backfill with a script or function". Renaming a field is unknown.
2. **Seed data (`loadData` CSVs) → bundled read-only files.**
   - Evan copied WorkFusion's Liquibase seed CSVs byte for byte (sha256-checked) into the function package.
   - Later insert and update changesets became a JSON patch applied in changelog order.
   - Alternatives: Data Fabric CSV import (10 MB / 30,000 rows; basic field types only), or a config-bucket JSON like Isaac's.
3. **Moving existing production data from WorkFusion's MSSQL → no precedent.** No port moved historical data. OrgClas only seeded its cache from reference outputs. Whether Evelyn's history moves at all is a question for leads.

**Bucket JSON has no schema.** Versioning is handled in code that reads both the old and new shapes. No port has a schema-version field (unknown whether one is needed).

## 8. Waits, timers, retries

- **Evelyn:**
  - `wait-for-completion` re-checks every 120 s with `reprocessAfter(120)`.
  - The Firco retry loop uses `reprocessAfter(waitTime)`.
  - Platform step retries have an attempt limit.
  - `@EnableScheduling` is , but there are no `@Scheduled` methods.
- **UiPath rule:** poll inside a function, not in a Flow Delay node. No `.flow` in the ports has a Delay node; "This call IS the poll interval" (`provider_jobs.py:366-371`).
  - Evelyn's own test: a `PT30S` Delay never fired and the parent stayed Running.
  - Each job has a 15-minute cap, so long waits become repeated poll calls.
  - Error ports are armed on every call node.

## 9. Human review

- **Evelyn:** a HUMAN step with the `nss-dw-mt.js` template (`BP[Names Screening]:4590`). The task data is `data_on_review`.
- **UiPath:** a HITL node, `uipath.human-in-the-loop.coded-action-app` or `quick-form`. The Flow parks until the task is submitted, through Action Center, email, Slack or Teams.
- **Precedent:** Isaac's "HITL Deferral Approve" node uses `ActionTaskApp`. The reviewer gets a reference to a bucket blob, not inline data, because big Flow variables hang the Flow.

## 10. Correlation ids

- **Evelyn:** `_sys_ext_record_id` and `request_id`, plus `bp_uuid`.
- **UiPath has no single business-id primitive.** The options:
  - **Job key:** returned on start, and present in webhooks. Isaac uses it in place of `bpUuid`, and as the working-folder name, so a retried job rewrites the same blob.
  - **Queue item `Reference`:** can be unique, up to 128 characters.
  - **Maestro custom instance ID:** shows your id in the instance list ([docs](https://docs.uipath.com/maestro/automation-cloud/latest/user-guide/custom-instance-id)).
  - **Your own request id passed as an input.** Isaac's provider calls carry `correlationKey` / `idempotencyKey`.

## 11. Platform limits that shape an Evelyn design

- **Serverless job:**
  - hard cap of 15 minutes;
  - 1 GB by default, up to 10 GB on the Large tier;
  - an out-of-memory kill shows as a silent Faulted;
  - robot size can't be set from the package.
- **Cold start:** about 50 s per job, so batch work per job.
- **Concurrent jobs:** Enterprise runs up to 50 serverless jobs per tenant at once (Community 3), shared by every Flow in the tenant. Past the cap is undocumented, and a Flow Loop has no cap of its own. One job per Function node run, so a loop of 3 Function nodes over 7 items is 21 jobs. Details and sources in [uipath-platform-architecture.md](uipath-platform-architecture.md#3-one-flow-run-step-by-step).
- **Payload size:**
  - big Maestro variables hang Flows, so pass bucket references instead;
  - classic job arguments hold 10,240 characters, and an oversized output is silently dropped. Robot 2025.10.1+ removes the cap; which Robot version serverless functions run on is unknown;
  - queue item data holds up to 256K characters.
- **"Coded Functions as Flow nodes" is still Preview** as of the Flow GA ([release notes](https://docs.uipath.com/maestro/automation-cloud/latest/release-notes/september-2026)).

## 12. No precedent yet: Evelyn would be first

1. An external HTTP entry point, via an API trigger.
2. A relational store of Evelyn's size, plus schema evolution over time.
3. Moving historical data from WorkFusion MSSQL.
4. Analytics and Superset.
5. Queue-based batch processing.

## 13. The configuration page and the decision-rules matrix

### What Evelyn has

**Two files, one settings page.** Both live in the Names Screening package resources.

| File | What it is |
|---|---|
| `configuration.json` | The Form.io **form definition**: the settings page an administrator edits in Control Tower. 118 input fields on 5 pages; 44 of them show or hide depending on other answers |
| `configuration_payload.json` | The **default values** (4 KB) in 6 blocks: `configuration`, `provider`, `providerSettingsThomsonReutersClear`, `enrichment`, `model`, `manualTask` |

Processors read the saved values through `TaskConfigurationProvider.getDigitalWorkerConfiguration`;
26 main classes call it.

**The five pages.**

| Form page (key) | What it sets | Example keys |
|---|---|---|
| `page1` | Input type, screening system, per-provider settings (URL, credential alias, write-back on/off), CSV locations, QC content in the REST answer | `configuration.INPUT_TYPE`, `configuration.PROVIDER_ID`, `provider.*`, `configuration.include_qc_report_in_rest` |
| `enrichment` | Entity-type confirmation, ticker name enrichment, location lookup, custom enrichment | `enrichment.type.entity_type_confirmation`, `enrichment.name.ticker_lookup`, `enrichment.location.provider`, `enrichment.custom` |
| `page2` | Model choice, **the decision-rules matrix**, factor thresholds | `configuration.MODEL_ID`, `model.rules.*`, `model.thresholds.*` |
| `page3` | Human-in-the-loop criteria; auto-QC rate and risk grid | `manualTask.criteria`, `configuration.auto_qc.*` |
| `page5` | CSV QC report and HTML report on/off; where results go | `configuration.reports.csv.enable`, `configuration.reports.html.enable`, `configuration.resulting_path` |

**Defaults** (`configuration_payload.json:3-4,50-51`):
- `INPUT_TYPE` `SCREENING_SYSTEM`
- `PROVIDER_ID` `FACTIVA`
- `report_bucket` `doc-upload`
- `resulting_path` `doc-upload/names_screening/QC_Report/{year}/{month}/`

### The decision-rules matrix

- **Two settings.**
  - `model.rules.fields` switches each factor's comparison on or off. By default name, location,
    date and type are , and gender and identifier are off.
  - `model.rules.configured_rules` is a grid labelled **"If"** with one column per factor. Each
    cell is either blank, meaning "any", or one of `weak_mismatch`, `strong_mismatch`,
    `strong_match` or `bad_info`. Location offers no `strong_mismatch`.
- **Default rows** (`configuration_payload.json`, `model.rules`):
  1. name `strong_mismatch`
  2. date `strong_mismatch`
  3. type `strong_mismatch`
  4. name `weak_mismatch` **and** location `weak_mismatch`
  5. name `weak_mismatch` **and** date `weak_mismatch`
  6. location `weak_mismatch` **and** date `weak_mismatch`
- **How a row is read:**
  - Within a row, every filled cell must match. Blank cells are dropped, and an empty rule set is
    an error.
  - Rows are alternatives. **If any row matches, the hit is a false positive (0); if none
    matches, it escalates (1)**.
  - Hits on a location-type entity ignore the grid and use the fixed rule `location weak_mismatch`
    (`model.py:37-40`). The check uses the **WLE's** entity type, not the screened party's.
- **Porting gotchas:**
  - **Every row is evaluated, not just up to the first match**. So a row
    that names a switched-off factor raises an error on every hit, even hits an earlier row matched.
    Row 1 of the defaults carries `"gender": ""` while gender is off, so the blank-cell cleaning is
    load-bearing.
  - **Location can never be `strong_mismatch`.** Each address part can be, but `compare_fields`
    turns any non-match into `WEAK_MISMATCH` for the location as a whole
    . That is why the grid offers
    no such option.
  - **Line numbers:** `model.py` is 2 lines longer after line 47 on MDL `master` (`d4c9929d`). The
    rules code itself is identical.
- **Where it runs: in the Python ML model, not in Java.**
  - `ModelDocumentBuilder.java:138-141` copies `fields` and `rules`, and `:144-148` the thresholds,
    into the model request's `configuration`.
  - The model evaluates them with `predict_by_rule` from WorkFusion's `wfrules` 0.1.2, a
    401-line Python package.
- **Compliance-sensitive:** `RulesConfiguration` and `ThresholdConfiguration` are on Evelyn's list

### UiPath equivalents

None of the ports found a built-in equivalent of Control Tower's configuration form; they build their
own (**Inference** that none exists):

| Need | UiPath option | Fits Evelyn? | Precedent |
|---|---|---|---|
| A settings page administrators edit | **Coded Web App** (React) that reads and writes a JSON document in a storage bucket | **Yes, the best fit**: copes with 118 fields, 44 conditions and grids | Evan's `EvanConfigurationApp` draws every field of Evan's Form.io page (386 fields, previously 395), with WorkFusion's own show/hide rules, and saves `config/tenant.json` to `EvanInputBucket`. Its `ReasonGrid` edits Form.io `datagrid` rows, the same kind of control as the rules matrix |
| Where the saved values live (≈ WorkFusion's stored configuration) | A JSON document in a config bucket, read when the job starts | Yes | Isaac: `IsaacConfiguration.default.json` plus `.schema.json` in a bucket with the CONFIGURATION role. Evan: `tenant.json` |
| A few flat on/off switches | Orchestrator **assets** (Text, Bool, Integer), per folder | Only for a handful of flags: no nesting, grids or form | None for settings pages |
| Credential aliases (`*_ALIAS` keys) | Credential or Secret assets | Yes | OWS, Evan |
| The rules matrix | Keep its rows as data in the config JSON and port the evaluator into Python, next to the ported model | Yes, and parity-safe: the evaluator is already Python | None; `wfrules` is WorkFusion's, so vendor it (ownership question) or re-implement its `equals` subset |
| Rules as a platform feature | Orchestrator **Business Rules**, run from a Maestro **BPMN** `businessRuleTask`, "Execute business rule [Preview]". UiPath's planner puts "Business Rules / DMN" inside Maestro | **Not now**: it is Preview, appears only in BPMN (not in Flow) in the skill docs, and Evelyn evaluates rules per hit inside the model | None |
| A low-code form instead of React | UiPath **Apps** (Studio Web → App) | Unproven for 118 conditional fields | None |

### How Evan's config app works

Evan's configuration app, read from the port on `main`.

| Question | Answer |
|---|---|
| What kind of project | A **Coded Web App**, not an action app: `type: Coded`, `isActionApp: false`, `bundlePath: dist`. A Solution project like a function |
| Stack | React, Vite, TypeScript, Tailwind, Vitest; UiPath's SDK `@uipath/uipath-typescript` ^1.6.1, locked 1.7.1 |
| How it logs in | As the person using it, through a **Non-Confidential (PKCE) External App** with user scopes `OR.Buckets.Read OR.Buckets.Write` (plus an unused `OR.Assets.Read`) and redirect `http://localhost:5173` for local dev . A deploy registers the deployed redirect URI itself; adding it by hand gives a 409 |
| How it reads the file | `buckets.getByName` → `getFileMetaData` (does it exist?) → `getReadUri` → a plain `fetch` → `JSON.parse`. A missing file is seeded with defaults on first load (`:83-101`) |
| How it saves | (`:73-74`), after a diff preview, then reloads. No version check: the last save wins (**Inference**) |
| How the form is drawn | **Hand-written** JSX in 4 steps over a hand-edited field manifest (386 fields). The JSON Schema is generated from the manifest and used only for TypeScript types . No precedent draws a form from a schema |
| Validation | Hand-rolled: a visible required field can't be empty, plus option checks; errors block the save |
| Build and deploy | `npm run build` writes `dist/`. **`uip solution pack` copies `dist/` but never builds it**, so the pipeline builds first. The routing name must be unique per org |
| How the Function reads it | Evan's `load-input` operation downloads the file from the INPUT bucket and merges it over packaged Python defaults, **top level only**: a nested block replaces the default block whole. If the Flow input `configFileName` is empty it reads `config.json`, not the `config/tenant.json` the app writes |

**Two choices for Evelyn** that cfg1 and Evan make differently:
- **Sparse or full file.** cfg1's file holds only the keys that differ and rejects unknown keys.
  Evan's app writes every visible field, and its schema allows unknown keys.
- **How deep the merge goes.** cfg1 merges key by key at every level (`deep_merge` in its
  `settings.py`); Evan merges only the top level.

**Recommendation (Inference).** Copy Evan:
- a coded settings app;
- one JSON document in a config bucket;
- the function reads it at start and passes `model.rules` and `model.thresholds` into the ported
  model exactly as `ModelDocumentBuilder` does today.

**Open questions:**
- Who may change rules in UiPath, and is there an audit trail? A bucket file is simply overwritten
  on save, and WorkFusion's history of changes is unknown.
- Are the saved configurations per customer migrated from WorkFusion, or re-entered?
- Can the `wfrules` package be shipped in a UiPath function package?

## Keeping this current

Re-check the **Unconfirmed** items against the live docs. The ones that matter most:
- Whether Secret assets work from coded functions. The docs say "only with coded agents", but the ports use them.
- Whether bucket file triggers exist.
- Whether Flows have a maximum runtime. The docs contradict each other.

When a team decides the data store, update §7.
