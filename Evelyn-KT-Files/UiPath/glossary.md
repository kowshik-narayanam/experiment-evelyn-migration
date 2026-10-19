# Glossary and concept map

Plain-language definitions of the terms used in these notes and in the repos. "Inference" marks
a meaning that no file states outright.

## Concept map: WorkFusion → UiPath, as these ports do it

For the full term-by-term dictionary (Control Tower → Studio Web + Orchestrator + Maestro, Java processor → `main.py`, App vs Coded App…) and platform mechanics through the Evelyn lens, see [equivalent.md](equivalent.md).

| WorkFusion | UiPath equivalent | Example |
|---|---|---|
| Digital worker (`dw-…` repo) | A Solution (`.uipx`) | `dw-isaac-tmi` → `IsaacUiPath.uipx` |
| Business Process (BP) zip | Maestro Flow (`.flow` + `.bpmn`) | Isaac: 10 BPs → 15 Flows |
| Task processor in a Java worker | Python coded Function, one `operation` per step | `Evan/EvanUiPath/EvanAmmFunction/entrypoints.py` |
| Worker called over REST | Orchestrator job started with `processes.invoke`, polled with `jobs.retrieve` | Isaac → Evan, OWS, OrgClas |
| Asset bundle import (Jenkins) | `uip solution` pack → publish → deploy, run by Azure DevOps | `pipelines/*-deploy.yml` |
| Control Tower | No single equivalent: Studio Web (design), Orchestrator (run, assets, buckets), Maestro (watch Flows), Action Center (human tasks) | |
| Vault secret | Orchestrator Secret asset | Vertex API key |
| Configuration JSON and Form.io page | Assets, a JSON file in a bucket, a coded config app | `EvanConfigurationApp` |
| Python Bridge / AutoML model | Model files in a storage bucket, run in a Python 3.11 child process | Evan, OrgClas |
| SQL Server tables | Data Fabric entity | OrgClas cache (the only use) |
| Manual-task React UI | Coded action app in Action Center | Isaac `ActionTaskApp` |
| Spoke integration tests | Offline pytest parity suites plus live e2e scenarios | `shared/e2e/` |
| Document Harvester | Document Understanding Classic | IDP; models retrained, not moved |
| Bitbucket `work-fusion` repos | Pinned snapshots in `<Domain>/workfusion-code-ref/` | `Isaac/workfusion-code-ref/` |

## WorkFusion terms

- **Digital worker:** WorkFusion's packaged, persona-named automation product: Isaac, Evan, Evelyn,
  Edward. Repos use the `dw-` prefix.
- **Skill:** one capability of a digital worker, e.g. Isaac's TMI.
- **Java Native Worker (JNW), or worker:** a queue-driven Java background process that runs task
  processors.
- **Task processor / Bot Task:** the code for one step, e.g. a `@TaskProcessor(id = "...")` class.
- **Business Process (BP):** WorkFusion's workflow of tasks and decision gates, exported as a zip.
- **Asset bundle:** WorkFusion's deployable package: BPs, datastore migrations, ML models,
  dashboards and configuration.
- **Control Tower:** WorkFusion's admin console.
- **Vault / Zookeeper:** the secret store / the configuration store.
- **Python Bridge / AutoML:** how Java workers run Python ML models / WorkFusion's model packaging.
- **REST input connector:** lets external HTTP clients start a business process and get its result.
- **Signal (signal id):** a BP's named address. REST calls (`start-record-raw/{signalId}`) and
  `BP_CALL` steps in other BPs target it to start that BP. It only routes; it is not a request id.
- **Spoke:** WorkFusion's integration-test framework.
- **Document Harvester:** WorkFusion's document classification and extraction product.
- **Form.io:** the form technology behind WorkFusion's configuration pages.

## UiPath terms

- **Orchestrator:** UiPath's control plane. It runs jobs and holds folders, assets and buckets.
- **Folder:** Orchestrator's unit of organisation and permissions; a Solution deploy creates one.
  Your **personal workspace** is your own folder, and Studio debug runs execute there.
- **Process / job:** a published, runnable package / one run of it.
- **Robot:** the agent that runs jobs.
  - A **serverless robot** is hosted by UiPath.
  - **Robot size** is its memory tier, e.g. Medium = 4 GB, or Large.
  - A **robot account** is the identity unattended jobs run as.
- **Solution (`.uipx`):** a bundle of projects and resources, packed, published and deployed as one
  unit with `uip solution`.
- **Feed:** a tenant's package catalogue.
- **Maestro Flow:** a visual orchestration graph (`.flow` + `.bpmn`, `"runtime": "maestro"`).
- **Coded Function:** deterministic Python or TypeScript code run as a job, with no LLM loop. Its
  entry point (usually `main.py:main`) is declared in `uipath.json`.
- **Coded app (AppV2) / coded action app:** a React app built on UiPath's SDK. An action app is the
  screen for a human task.
- **Action Center / HITL:** UiPath's inbox for human-in-the-loop tasks.
- **RPA process (XAML):** a workflow built in Studio and run by a robot. "Portable" means
  cross-platform; "Windows" means Windows-only.
- **Agent:** an LLM-driven project. Here it exists only in Isaac's POC.
- **API workflow:** a JSON-defined workflow. Here it exists only in Isaac's POC; the Isaac team found
  a practical ten-minute limit on its runs.
- **Storage bucket:** an Orchestrator file store.
- **Asset (Text / Secret):** a named setting / an encrypted, write-only value stored in Orchestrator.
- **Data Fabric entity:** a UiPath-managed data table.
- **Document Understanding (DU) Classic:** UiPath's older, project-based document classification
  and extraction, with trained classifiers and extractors.
  - **Document Manager:** its labelling tool.
  - **AI Units:** the unit its use is billed in.
- **LLM Gateway:** UiPath's proxy to hosted language models.
- **Integration Service connector:** a managed connector to an external API. None are used here.
- **Bindings / link:** how a project declares the resources it needs (`bindings.json`) / how a
  deploy points them at resources that already exist (`deploy config link`).
- **External application / grant:** an OAuth client-credentials identity / its allowed scopes. The
  pipelines use `WorkfusionAzurePipelines`.
- **`uip`:** UiPath's general command-line tool (Solutions, Flows, pack, publish, deploy, link,
  codedapp). Not the same as the Python SDK's `uipath`: see [the two CLIs](#the-two-clis-uipath-and-uip).
- **Studio / Studio Web:** UiPath's authoring tools.

## The two CLIs: `uipath` and `uip`

A single function uses `uipath`. A Flow and a Solution use `uip`.

| | `uipath` | `uip` |
|---|---|---|
| What it is | The Python SDK's CLI | UiPath's general CLI |
| Where it comes from | `uv add uipath`, installed into each project's `.venv` | npm package `@uipath/cli` (1.202.1) |
| How you run it | `uv run uipath …` inside one function folder | `uip …` from anywhere |
| What it knows | **One** Python project | Solutions, Flows, functions, RPA, Orchestrator |
| Login | `uipath auth` → the project's `.env` | `uip login` → the UiPath CLI login store |
| `pack` output | `.uipath/<name>.<version>.nupkg`: one package | `<out>/<Solution>_1.0.0.zip`: one `.nupkg` per project, plus what to create in Orchestrator |
| Maven | `mvn package` in one module | `mvn package` on the parent POM of a multi-module build |
| WorkFusion | Building one bot's jar | The asset bundle Jenkins imports |

**Which CLI for which job** (Examples 2.5 and 2.6)

| Job | Command | Why this CLI |
|---|---|---|
| Create the Python project | `uv run uipath new` | Only `uipath` has the Python template |
| Generate `entry-points.json` | `uv run uipath init` | It reads your Python code |
| Run one function locally | `uv run uipath run main` | It runs Python |
| Create the Solution (`.uipx`) | `uip solution init` | `uipath` has no Solutions |
| Create the Flow | `uip maestro flow init` | `uipath` has no Flows |
| Register a function in the Solution | `uip solution projects add` | Edits the `.uipx`, like adding a `<module>` to the parent POM |
| Find node types, check the `.flow` | `uip maestro flow registry` / `validate` / `format` | Flow-only tools |
| Pack Flow + functions together | `uip solution pack` | Builds every project in one go |
| Run the whole Flow on the tenant | `uip maestro flow debug` | Uploads the Solution and runs it |

- **The migration repo deploys with `uip`:** `uip solution pack/publish/deploy` from Azure
  pipelines (`pipelines/templates/{pack,publish,deploy}-solution.steps.yml`), not `uipath publish`.
- **`uip function` hands off to `uipath`:** its help calls it a "thin passthrough". So
  `uip function new -l py` fails with "'uipath' not found" unless the Python CLI is on your PATH;
  it lives only in a project's `.venv`.
- **Don't mix the logins:** `uip solution pack` (and `flow debug`) ships each project's `.env`, so a
  token from `uipath auth` would travel in the package. Inside a Solution, use `uip login`. Details
  in [coded-functions.md, Sharp edges](coded-functions.md#sharp-edges).
- See for yourself: `which uip`, `uip --help`, `npm ls -g --depth=0` (lists `@uipath/cli` and its
  `function`, `maestro`, `rpa` and `solution` tools).

## Source vs generated files

Read and debug the source files; regenerate a generated file instead of
debugging it. Counts are committed files in `UiPath-WorkFusion`, and paths are relative to it.

**`.flow` vs `.bpmn`.** The `.flow` (UiPath JSON) is the source that Studio Web and the
`uip maestro flow` CLI edit. The `.bpmn` (BPMN 2.0 XML, `exporter="UiPath Flow"`) is generated
from it, and the package's entry point is that `.bpmn`
(`Isaac/IsaacUiPath/IsaacTransactionMonitoringFlow/operate.json`). The `.bpmn` uses `vars.x`
where the `.flow` has `$vars.x` (`EDE/README.md:201`).
- The committed `.bpmn` lags: `IsaacTransactionMonitoringFlow.flow` changed in 32 commits, its
  `.bpmn` in 5. Their node ids still match; the `.bpmn` adds an implicit start and end event
  per loop.
- **Inference:** a stale committed `.bpmn` doesn't reach the tenant, because pack writes a fresh
  one into the package (UiPath skill `uipath-maestro-flow/references/author/CAPABILITY.md:131`;
  `EDE/README.md:201`; `Isaac/docs/isaac-anatomy.md:3013-3016`).
  `Isaac/docs/isaac-anatomy.md:3243` says the opposite: only Studio Web regenerates it.
- EDE copies the packed `.bpmn` back into git by hand, so a mismatch there is a chore, not a bug.

**Skip entirely**

| File | Generated by | Read instead |
|---|---|---|
| `*.bpmn` (21) | Studio Web save, or pack | The `.flow` beside it |
| `*.mermaid` (15) | `uipath init` ("AUTO-GENERATED … Do not edit") | `main.py` |
| `.agent/*.md`, `.claude/commands/*.md`, and `AGENTS.md`/`CLAUDE.md` starting "Agent Code Patterns Reference" (11) | `uipath init`: the same SDK docs in every project | The SDK docs |
| `operate.json`, `package-descriptor.json` (22 each) | The Flow CLI, for packaging | Nothing |
| `project.uiproj` (54), `simulations.json`, `evals/**/initialized.json` | Scaffolding | Nothing |
| `uv.lock`, `poetry.lock` | `uv` / `poetry` | `pyproject.toml` |
| `.uipath/*.nupkg`, `dist/`, `dist-package/` | `uipath pack`, app builds; committed by mistake | The source folders |

**Generated, but harmful when stale: regenerate and diff, don't debug**

| File | What goes wrong | Fix |
|---|---|---|
| `entry-points.json` | Maestro shows the old fields after the Input/Output classes change ([coded-functions.md](coded-functions.md)) | Re-run `uipath init` |
| `bindings_v2.json` (Flows) | CLI 1.202 writes the wrong `ActivityName` (`EDE/README.md:201`) | Diff against the committed copy |
| `resources/solution_folder/**`, `*.uipx` | Managed by `uip solution`, yet they decide what a deploy creates | Leave them unless a deploy fails |

**Look generated, but aren't**
- A function's `bindings.json`: hand-written since SDK v2.2.0.
- `workfusion-code-ref/`: a copied WorkFusion snapshot. Read-only, and the authority for business
  logic.

**The source per project type:** Flow → the `.flow`. Function → `main.py`, its package folder,
`pyproject.toml`, `uipath.json`, `bindings.json`. Coded app → `source/`. RPA → `Main.xaml`,
`project.json`.

**Local checkouts:** `.env` and `.uipath/.auth.json` come from `uipath auth` and hold a
login token; don't open or share them.

## Maestro Flow: naming, files and the canvas

From the Flow skill (`uip` 1.202.1).

**Naming rules for a `.flow`**

| Rule | Example (Example 2.5) | Hard rule or convention? |
|---|---|---|
| Two-level nesting: `<Solution>/<Project>/<Project>.flow` | `PrimesPipeline/PrimesFlow/PrimesFlow.flow` | **Hard.** A single-nested project fails Studio Web upload and packaging |
| The `.flow` sits next to `project.uiproj`, in the same folder | `PrimesFlow/project.uiproj` + `PrimesFlow/PrimesFlow.flow` | **Hard.** The CLI, debug and Studio find it there; a `.flow` elsewhere is ignored |
| File name = project folder name | `uip maestro flow init PrimesFlow` creates both | Convention from the scaffold. Unknown whether another name works, so don't rename |
| One `.flow` per Flow project | Each of Isaac's 15 Flow folders has one | Convention |
| Node and edge IDs start with a letter | `generate`, `edge_generate_output_filterPrimes_input` | **Hard.** A leading digit makes the engine skip every node after Start |
| Project names in the ports | `Isaac<Purpose>Flow`, e.g. `IsaacTransactionMonitoringFlow` | Team convention |
| Node IDs | camelCase; the canvas appends `1`, `2`… (`dataValidationTaskProcessor1`) | Convention |

**Which file does what**

| File | Format | Role | Written by | Read by |
|---|---|---|---|---|
| `<Name>.flow` | UiPath JSON | **The design:** nodes, edges, variables, bindings, canvas layout | You, via the canvas, the CLI or an agent | The canvas, `validate`, `pack` |
| `<Name>.bpmn` | BPMN 2.0 XML | **The executable:** what the Maestro engine runs | Generated by `pack` / a Studio Web save | The engine; the package's `operate.json` has `"main": "content/<Name>.bpmn#start"` |
| `entry-points.json` | JSON Schema | The Flow's public contract (inputs and outputs) | Generated from the `.flow`'s variables | Orchestrator's start form, callers |
| `operate.json`, `package-descriptor.json` | JSON | Package metadata | Generated | The packager |

Example 2.5's project has no `.bpmn` at all, yet it packs: the package holds a freshly generated
`content/PrimesFlow.bpmn` and an `entry-points.json` with `limit` as the only input. Isaac's repo
commits a `.bpmn` beside each `.flow` because Studio Web writes one on save. In WorkFusion terms:
the `.flow` is the BP drawn in Control Tower, the `.bpmn` its compiled form.

**Building on the canvas** (Studio Web and the Maestro extension in Cursor/VS Code are the same canvas)

| Action | How |
|---|---|
| Add a node | The **+** on a node's right edge (on hover), or **+** in the bottom toolbar, opens the node list |
| Connect | Drag from a node's output dot to the next node's input dot |
| Configure | Click the node → **Properties**: **Parameters** (inputs), **Error handling** (error port), **Advanced** (ID, variable updates) |
| Fill an input | A fixed value (`generate`), or **Insert** an earlier node's output, which writes `=js:$vars.<node>.output…` |
| Save | The save icon. It rewrites the `.flow`, so never save one in a read-only repo |

**Control Tower → canvas**

| Control Tower BP element | Maestro node | Registry type |
|---|---|---|
| Start | Manual / Scheduled trigger | `core.trigger.manual`, `core.trigger.scheduled` |
| Bot task (a `@TaskProcessor`) | **Function** node: a published or in-solution function | `uipath.core.function.<key>` |
| Rule node / gateway, yes or no | **Decision**: one JavaScript expression → true and false branches | `core.logic.decision` |
| Rule node with several outcomes | **Switch**: one branch per case | `core.logic.switch` |
| Loop over records | **Loop**, and **Merge** to join branches | `core.logic.loop`, `core.logic.merge` |
| Small inline logic | **Script**: JavaScript, 30 s limit, no external calls | `core.action.script` |
| Map/filter fields | **Transform**, **Filter**, **Map**, **Group by** | `core.action.transform.*` |
| Sub-BP | **Subflow**, or a node that calls another Flow | `core.subflow`, `uipath.core.flow.<key>` |
| `BP_CALL` to another worker | Flow or process nodes | `uipath.core.flow.*`, `uipath.core.rpa-workflow.*` |
| Human task | Human-in-the-loop node (Action Center) | `uipath.human-in-the-loop.*` |
| End | **End** (maps the Flow's outputs) or **Terminate** | `core.control.end`, `core.logic.terminate` |
| Wait | **Delay**. Avoid: Evelyn's test hung on one | `core.logic.delay` |

- **A rule operator is a Decision node** with a JavaScript expression. Isaac's "check for
  transactions" uses
  `$vars.start.output.payload.has_transactions === true || $vars.start.output.payload.fetch_transactions === false`.
- **Functions aren't written on the canvas.** The canvas lists them; their code lives in your
  editor (`PrimesFunction/main.py`). Studio Web's "Create New" has no Function option. Once a
  function project is in the Solution, its node appears in the list.

## Compliance domain terms

- **AML:** anti-money laundering. **FCC:** Financial Crime Compliance (Inference).
- **Alert:** a flag raised by monitoring or screening that must be reviewed.
- **Auto-clear / escalate:** close an alert automatically as a false positive / send it on for
  investigation.
- **TMI / TMR:** Transaction Monitoring Investigator (Isaac's skill) / the Transaction Monitoring
  Report (Word).
- **Party / counterparty:** the bank's customer / the other side of a transaction.
- **AMM:** adverse media monitoring, i.e. screening news for negative coverage (Evan).
- **OWS / OpenFIGI:** Open Web Search / a public API that tells whether a company is listed.
- **OrgClas ("VertexAI"):** Organisation Classification. The nickname comes from its Gemini step.
- **NAICS / NER / TF-IDF:** industry codes / a model that tags a name as company or person / a
  keyword-weighting technique.
- **Risk matrix:** OrgClas's 38×38 grid of party industry × counterparty industry.
- **EDD / IDP / EDE:** Enhanced Due Diligence (Edward) / intelligent document processing / Entity
  Data Enrichment.
- **FinCEN MSB / SOS / MAP:** the US register of Money Services Businesses / state Secretary of State
  business registries / a map or Street View check of an address.
- **TR CLEAR:** Thomson Reuters CLEAR (Inference).
- **Deferral:** an approved postponement of an alert review.
- **MVB:** both a rule set in Isaac and the customer documents behind IDP. Inference: a customer's
  name.
- **PEP:** politically exposed person.
- **Sanctions screening:** checking names against sanctions and watch lists.
  - **Watchlist entry (WLE):** one entry on a provider's list.
  - **Hit:** a possible match between a screened name and a WLE.
- **Factiva / World-Check One / Firco Trust:** Evelyn's screening data sources:
  - Factiva comes from Dow Jones.
  - World-Check One comes from Refinitiv, over REST signed with HMAC.
  - Firco Trust is the client's case manager. Evelyn polls it over SOAP and writes decisions back.

  Details: [evelyn-helper-repos.md](evelyn-helper-repos.md).
- **QC:** quality control, i.e. checking a sample of decisions.

## Evelyn (NSS) terms

- **NSS:** Names Sanctions Screening, Evelyn's product. **B-AML-PEP:** its use-case code.
- **`nss_schema.yaml`:** Evelyn's OpenAPI contract, from the `names-screening-contract` artifact.
- **`nss-classification-model`:** Evelyn's ML model, which decides per hit.
- **`nss-dw-mt`:** Evelyn's React manual-task UI.
- **Liquibase:** a database schema migration tool. Evelyn's migrations are append-only.
- **Superset / Elastic APM:** Apache's dashboard tool / application performance monitoring.

## Repo and process terms

- **Port / migration:** translating a WorkFusion worker to UiPath like for like.
- **Parity:** equivalent business behaviour, proven with tests and live runs.
  - **Cell-identical:** spreadsheet outputs match cell by cell.
  - **D-number (D1, D9, …):** a tracked difference from WorkFusion's output
    (`Isaac/docs/workfusion-parity-differences.md`).
  - **Run N:** a numbered live run in `Isaac/docs/live-run-report.md`.
- **Reference snapshot:** WorkFusion source checked in under `workfusion-code-ref/`, pinned to a
  commit.
- **Reference (golden) outputs:** WorkFusion-generated outputs used as expected results.
- **Tier:** an e2e scenario class: smoke, regression, parity or performance.
- **Registry:** `shared/e2e/registry.yaml`, per-solution facts for the e2e harness.
- **Stub mode:** canned answers used to test wiring (Evan's `evan-mode: stub`).
- **Cold start:** the ~50 s a job takes to start.
- **AI Workspace Guide:** a domain's `AGENTS.md`. **superpowers:** AI skills for spec → plan →
  test-driven development.
- **ADO:** Azure DevOps. A **variable group** is a shared set of variables and secrets; an
  **environment** is a named deploy target.
- **Ticket prefixes:** EXPERT- and SW- on the WorkFusion side; STUD- and ROBO- for CoreWF (Studio,
  Robot).
- **POC:** `Isaac/POC/AMLRulesIntegrationShadowCandidate`, an earlier UiPath attempt kept for
  comparison.
- **StableIsaac / PatrickIsaac:** hand-deployed Orchestrator folders used for the parity runs.

## CoreWF and .NET terms

- **Windows Workflow Foundation (WF):** Microsoft's .NET Framework workflow engine.
  - **Activity:** one composable step.
  - **XAML workflow:** a workflow saved as XML.
- **CoreWF (`UiPath.Workflow`):** UiPath's port of WF to modern .NET.
- **TFM:** target framework moniker, the .NET version a project builds for (`net6.0`,
  `net6.0-windows`).
- **NuGet / feed:** the .NET package format / a package server.
- **`UiPath.System.Activities`:** UiPath's core activities package. It is not CoreWF itself.
