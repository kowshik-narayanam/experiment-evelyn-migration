# Python coded Functions

- **Sources:** the SDK docs at https://uipath.github.io/uipath-python/ (mainly `core/functions/`,
  `core/studio_web/`, `cli/`, `FAQ/`), checked against SDK `main` (`uipath` 2.14.27), and the
  UiPath-WorkFusion ports.
- **Newer source, not yet compared:** official Functions docs at
  https://docs.uipath.com/functions/automation-cloud/latest/user-guide/about-functions.
  Check a claim here against them before relying on it.
- **Status:** the docs label coded Functions **"Preview Feature … subject to changes"** (doc
  source in `UiPath/uipath-python`).

## The short version

A coded Function is one ordinary Python function with a typed input and a typed output. UiPath
packs it and runs each call as a short Orchestrator job on a UiPath-managed **serverless** robot:
no robot UI, no desktop, no LLM loop. It is conceptually like AWS Lambda, but that is only an
analogy: UiPath runs it (see [Where it runs](#where-it-runs)). A caller sends JSON and gets JSON
back; in these repos the caller is almost always a Maestro Flow step.

## What you write

```python
# main.py
from dataclasses import dataclass

@dataclass
class Input:
    name: str

@dataclass
class Output:
    score: float = 0.0
    error_type: str = ""     # business errors go here, not in exceptions

def main(input: Input) -> Output:
    return Output(score=0.9)
```

```json
{ "functions": { "main": "main.py:main" } }
```

- `uipath.json` maps a function name to `file:function`. Several entries are allowed.
- `pyproject.toml`: Python ≥3.11 and the `uipath` package. `uipath pack` also needs
  `description` and `authors`.
- Input/Output can be stdlib dataclasses, pydantic models or pydantic dataclasses. The function can
  be `def` or `async def`.
- Generated or plumbing files:
  - **`entry-points.json`:** JSON Schema built from the Input/Output types. Maestro uses it to show
    typed fields. `uipath init` regenerates it; re-run `init` after changing the models or it goes
    stale.
  - **`bindings.json`:** the Orchestrator resources the code names (asset, bucket, process…). After
    deploy, each can be re-pointed per environment without a code change. Written by hand
    SDK v2.2.0.
  - **`.env`:** local login token and URL from `uipath auth`.

## Lifecycle

```
uipath auth                         # browser login, writes .env
uipath new my-fn --type function    # scaffold
uipath init                         # generate the schema files
uipath run main '{"name":"x"}'      # run locally, plain Python
uipath pack                         # .uipath/<name>.<version>.nupkg
uipath publish --my-workspace       # appears in Orchestrator as a "Function (python)" process
```

In the cloud the job installs dependencies from `uv.lock`, injects auth and folder context
(`UIPATH_FOLDER_KEY`, `UIPATH_ROBOT_KEY`), calls `main(input)` and stores the return value as the
job output. `uipath init` imports your code, so keep module level free of side effects.

## How it gets called

- **Maestro Flow (normal):** a Service Task node points at the Function. Inputs are bound from flow
  variables and the output becomes a flow variable.
- **Anything else:** Orchestrator `StartJobs` API, `uipath invoke`, or another Function via
  `sdk.processes.invoke(...)`. None of these wait: you get a job key, poll `sdk.jobs.retrieve`
  until it finishes, then read `sdk.jobs.extract_output`.
- Inside the Function, `UiPath()` gives platform access: `sdk.assets.retrieve_secret(...)`,
  `sdk.buckets.download/upload`, `sdk.connections`. Credentials are injected in a job.
- `@traced` goes on inner steps, never on the entry point (the runtime already wraps it).

## Where it runs

- Function jobs run on **Automation Cloud Robots - Serverless**, which "execute Agent, Function,
  and Api jobs through Unified Runtime" (UiPath docs, *Automation Cloud Robots - Serverless*).
- **Not AWS.** UiPath Automation Cloud is hosted on **Microsoft Azure**: UiPath-provided VM robots
  are Azure `Standard_E2s_v4` VMs, and UiPath announced Automation Cloud "on the Microsoft Azure
  platform" in South Korea. The serverless docs don't name the infrastructure under
  serverless robots (**Inference:** Azure too).
- The migration's CI runs on Azure DevOps. That is the build pipeline, separate from where jobs run.

## How UiPath-WorkFusion uses them

13 Function projects, all on the same pattern. This is the template an Evelyn port would copy.

- **One function, many operations.** Each project exposes one `main`; an `operation` input field
  picks the step. This replaces WorkFusion's Java task processors. Example:
  Isaac's workflow Function has about 70 operations
- **Never raise.** Exceptions are caught and returned as `errorType`/`errorMessage`. The Flow treats
  a step as successful only when `errorType === ""`.
- **Flow node:**

  sets `"operation": "classify"`; other inputs are JS expressions over flow variables.
- **Pinned SDK:** every project pins `uipath>=2.10.0, <2.11.0` (e.g.
- **Deploy** uses `uip solution pack/publish/deploy` on a `.uipx` from Azure pipelines
  , not `uipath publish`.
- **Isaac and its providers:** Isaac starts Evan, OWS and OrgClas as separate jobs and polls every
  5 s,
  because the built-in flow-call node hung for hours when a child job faulted (`:1-21`, D31).
- **Offline tests** replace the SDK with fakes and block sockets

## Sharp edges

Mostly from the repo, not the docs. Source unless stated:

- **15-minute hard cap per job; 1 GB memory by default.** Running out of memory is a silent
  Faulted. Medium 4 GB and Large 10 GB are set after deploy via OData
  . The SDK docs don't mention limits.
- **Cold starts are slow:** 52.4 s cold vs 9.0 s warm on a run's first job
  . Don't make every tiny step a job.
- **Big payloads can hang a Flow** through Maestro variables. Put data in a bucket, pass a reference.
- **Resources bind by name:** a same-named process in a personal workspace took over a binding (404).
- **Never call `buckets.exists_file`** on staging: it reports present blobs as missing.
- **Output aliases are ignored:** the runtime dumps output without `by_alias`
- **Armed error ports inject `errorHandlingEnabled`** into the input; with `extra="forbid"` every
  call faulted.
- **SDK breaking changes between minors:** v2.10.0 changed the schema `type` from `"agent"` to
  `"function"`. The FAQ says use `uipath>=2.1.169` or cloud jobs can hang.
- **`uip solution pack` ships each project's `.env`, login token included.** It put
  `content/.env` in the package and ignored `packOptions.filesExcluded: [".env"]` (tested in the
  playground, `uip` 1.202.1). `uip maestro flow debug` uploads through the same pack.
  The SDK's own `uipath pack` leaves `.env` out (example1's three packages have none). So inside a
  Solution, log in with `uip login`, never `uipath auth`, which writes the
  token into `.env`. CI packs from a clean checkout, and the migration repo ignores `.env`,
  so the risk is a local pack or debug.

## Docs that contradict the code

- `core/functions/` shows `buckets.upload(..., content_file_path=...)`. No such parameter; the code
  takes `source_path` or `content`.
- The reference that `uipath init` copies into projects recommends
  `uipath init --infer-bindings`. No such flag.
- Getting Started says `init` creates 2 files; it creates about 10 (`AGENTS.md`, `CLAUDE.md`,
  `.agent/*.md`, `<ep>.mermaid`, `project.uiproj`, …).

## In WorkFusion terms

| WorkFusion | UiPath |
|---|---|
| Business Process (BP) | Maestro Flow |
| Java task processor | One `operation` inside a Python coded Function |
| Worker called over REST | Orchestrator job, started then polled |
| Vault secret | Orchestrator secret asset |
| Control Tower | Orchestrator |

Full mapping: [equivalent.md](equivalent.md).
