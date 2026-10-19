# Evelyn → UiPath, first slice: instructions for AI agents

Read this before you change anything here. The human guide is [README.md](README.md); running it is
[HOW_TO_RUN.md](HOW_TO_RUN.md). The design and its evidence are in [docs/](docs/): `mapping.md` (Evelyn → UiPath,
with `path:line`), `decisions.md` (DEC-n, approved by the owner on 2026-10-19), `differences.md` (D-n),
`out-of-scope.md`.

## What this is

A port of one path of Evelyn (WorkFusion's Names Sanctions Screening worker) to UiPath: the "CSV File Ingestion" BP
calling the main "Names Screening" BP, up to and including `csv-schema-producer`. Translate, don't redesign: every
forced change gets a D-number in `docs/differences.md`.

## Source vs generated

| Edit these | Never edit these (regenerate instead) |
|---|---|
| `evmig-nss/src/`, `evmig-nss/tests/`, `evmig-nss/pyproject.toml` | `evmig-nss/dist/*.whl` (`uv build --wheel`, via `scripts/vendor_wheel.sh`), any `uv.lock` (`uv lock`) |
| Each function's `main.py`, its other `.py` modules, its tests, `conftest.py`, `pyproject.toml` (made by commands, changed by `uv add`) | `wheels/*.whl` in each function (`scripts/vendor_wheel.sh`), `entry-points.json`, `uipath.json`, `project.uiproj`, `main.mermaid`, `.uipath/` (`uv run uipath init` / `uipath new`) |
| The bucket entry in `bindings.json` of `EvMigCsvMonitorTask` and `EvMigCsvTask` (hand-written: `uipath init` cannot see bucket calls inside the wheel) | `AGENTS.md`, `CLAUDE.md`, `.agent/`, `.claude/` inside each function, and `EvMigEvelyn/AGENTS.md`, `EvMigEvelyn/CLAUDE.md`: CLI boilerplate, not this file |
| `EvMigEvelyn/*Flow/*.flow`, **only by changing and re-running `scripts/build_flows.sh`**. The owner may tidy the layout in the Studio Web designer: the rebuild check (`scripts/normalize_flow.sh`, HOW_TO_RUN level 3) ignores layout and designer metadata. Keep the tidied files | `EvMigEvelyn/EvMigEvelyn.uipx`, `EvMigEvelyn/resources/` (`uip solution …`), any `.bpmn` or `operate.json` (generated from the `.flow`); `evals/`, `simulations.json`, `userProfile/` (designer and `uip` scaffolding, gitignored) |
| `docs/mapping.md` §8, then `python3 -I scripts/entities.py --write` | `EvMigEvelyn/entities/*.create.json` (generated from mapping §8) |
| `data/` (mock bucket content), `docs/`, `scripts/`, README, HOW_TO_RUN | |

## Rules

1. **Nothing on a tenant without the owner's go-ahead.** Not allowed: `uip maestro flow debug`, `uip solution
   upload` / `publish` / `deploy`, `uip df entities create`, `uip df records insert`, bucket create or upload, starting
   a job. Read-only calls are fine: `uip login status`, `validate`, `registry`, `resources list` / `refresh`,
   `pack --dry-run`, `uip df entities list`. Tenant steps go into HOW_TO_RUN for the owner to run. To run `uip` with no
   login, use a copy outside `~/UiPathRepos` and `HOME=$(mktemp -d)`: `uip` also takes a login from any `.uipath/`
   folder above the working folder, and `~/UiPathRepos/.uipath/` holds one (check with `uip login status`).
2. **No secrets.** Never run `uipath auth` in a project folder: it writes a token into `.env`, and `pack` ships `.env`.
   Use `uip login`. `uv run uipath init` creates an **empty** `.env` in a function folder; delete it (after checking
   it is 0 bytes) before `pack`. Never commit `.env`. Never copy credentials from any repo.
3. **Read-only elsewhere:** the Evelyn repos under `~/WorkfusionRepos/NSS/`, `~/UiPathRepos/UiPath-WorkFusion/`,
   `~/UiPathRepos/Evelyn Simulation/`, `~/UiPathRepos/learning/`. Don't commit or push here unless the owner asks.
4. **Changing the library:** bump `version` in `evmig-nss/pyproject.toml` (a changed wheel under the same version is
   refused by `uv` with a hash mismatch), then `scripts/vendor_wheel.sh` (rebuilds the wheel and vendors it into all
   three functions), then run every test suite. Each function has a test that its wheel equals `evmig-nss/dist/`.
5. **Changing a function's input or output model:** `uv run uipath init` in that function, then rebuild both Flows
   with `scripts/build_flows.sh`. The Flow nodes hold a snapshot of the schema, and `validate` does not notice a stale
   one.
6. **Flows:** `$metadata.InstanceId` with a capital I. The Flow skill's `$metadata.instanceId` is undefined at runtime
   and `validate` warns on it. `validate` exits 0 with warnings: read `.Data.Warnings`.
7. **Data Fabric** field names are PascalCase (letters and digits only). Entities are tenant-level.
8. **Mock data only**, with placeholder names (Alice Wonderland, John Doe, Gill Bates and spelling variants). Keep
   each `csv-task` output under 8,000 characters (a test checks it): larger job outputs may be dropped silently.
9. **Every tenant-visible name starts with `EvMig`.**
10. **Claims:** cite `ALIAS:path:LINE` “quote” (aliases in `docs/mapping.md` §0); `scripts/check_citations.py`
    checks every one. Label guesses **Inference**; say "unknown" when evidence is thin. The scripts hold absolute
    paths to the owner's checkouts.

## Verify after any change

| Check | Command (from the repo root) | Expect |
|---|---|---|
| Library | `cd evmig-nss && uv run pytest -q` | `465 passed` |
| Monitor | `cd EvMigEvelyn/EvMigCsvMonitorTask && uv run pytest -q` | `33 passed` |
| csv-task | `cd EvMigEvelyn/EvMigCsvTask && uv run pytest -q` | `148 passed` |
| Producer | `cd EvMigEvelyn/EvMigCsvSchemaProducer && uv run pytest -q` | `35 passed` |
| Entities | `python3 -I scripts/entities.py` | three lines, no `FAIL` |
| Citations | `python3 -I scripts/check_citations.py docs/*.md` | `N/N citations verified` |
| Flows | see HOW_TO_RUN level 3 | both `Valid`, no `Warnings`; `pack --dry-run` `Valid` |
| Local run | HOW_TO_RUN level 2 | 3 transactions, 3 alerts, 5 hits |
