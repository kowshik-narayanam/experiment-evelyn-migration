# CoreWF: status

- **Snapshot:** `develop` @ `c67ebe3` (PR #404), 612 commits. Paths are relative to
  `CoreWF/` unless they start with `UiPath-WorkFusion/`.
- **Short answer:** CoreWF is UiPath's .NET port of Microsoft's Windows Workflow Foundation. It is
  not part of the WorkFusion migration. At most it is the engine that runs the migration's 2 XAML
  robots inside the UiPath Robot (Inference).

## What it is

- **Windows Workflow Foundation (WF)** is Microsoft's .NET Framework engine for workflows built from
  nested *activities* (small steps that can contain other steps), often saved as XAML. CoreWF runs
  that on modern .NET. It loads XAML with `ActivityXamlServices` and runs it with `WorkflowInvoker`
  (`README.md:5,13-15,53-58`). The visual designer is not included (`README.md:66`).
- It calls itself an unofficial "derivative work" of Microsoft's WF (`README.md:8-9`). It is MIT
  licensed and a .NET Foundation project (`README.md:95-97`). The first commit is
  "Initial port of WF to .NET Core".
- **It keeps WF's identity.** The runtime assembly is still named `System.Activities`
  (`src/UiPath.Workflow.Runtime/UiPath.Workflow.Runtime.csproj:4`), and it claims WF's XAML
  namespace (`src/UiPath.Workflow.Runtime/AssemblyInfo.cs:23-27`). Existing WF XAML therefore loads
  unchanged.
- **It is a UiPath product component.** Packages are `UiPath.Workflow` and
  `UiPath.Workflow.Runtime`. Code comments mention Studio Web
  (`src/UiPath.Workflow/Activities/ScriptingAotCompiler.cs:89`), and commits cite Studio tickets
  (STUD-). Inference: it is the XAML engine inside UiPath Studio and the UiPath Robot. The Robot's
  code is in neither repo, so this can't be confirmed here.

## Layout (`src/`)

| Project | Role |
|---|---|
| `UiPath.Workflow.Runtime` | The core engine: activities, bookmarks, durable instances. Assembly name `System.Activities` |
| `UiPath.Workflow` | Statements, XAML loading, debugger, validation, VB/C# expression compilation through Roslyn |
| `System.Xaml` | A copy of Microsoft's XAML library, used by the portable build |
| `VisualBasic` | A VB scripting helper, bundled into `UiPath.Workflow` |
| `CoreWf.EtwTracking` | Windows event tracing; not packaged by CI |
| `Perf`, `Test` | BenchmarkDotNet benchmarks; xUnit tests on both target frameworks |

Target frameworks are `net6.0` (cross-platform) and `net6.0-windows`.

## Build and publish

- **CI:** Azure Pipelines builds `main`, `develop`, `support/*` and `release/*`, plus PRs into
  `develop`, on Windows (`azure-pipelines.yaml:1-45`).
- **Version:** `6.0.0` on `develop`, plus a date suffix (`src/Directory.Build.props:3`).
- **Publish:** the packages are signed.
  - Builds from `develop`, `support/*` and `release/*` go to the internal feed `UiPath-Internal`.
  - Only `main` publishes to nuget.org (`.pipelines/release.yaml:28-62`).
- **Local build:** `dotnet build` / `dotnet test` in `src` (`CONTRIBUTING.md`). Inference: it
  probably fails on macOS, because Release post-build runs `rd /S /Q` and `net6.0-windows` turns on
  WPF.

## Relationship to UiPath-WorkFusion

| Question | Answer | Evidence |
|---|---|---|
| Direct dependency? | **No** (high confidence) | UiPath-WorkFusion has no hits for `corewf`, `UiPath.Workflow`, `WorkflowInvoker`, `ActivityXamlServices` or "Windows Workflow". It has no `.cs`, `.csproj`, `.sln` or `packages.config` |
| Indirect runtime? | **For 2 projects only** (Inference, medium confidence) | See the next list |
| Everything else? | **Unrelated** | Maestro Flows declare `"runtime": "maestro"` (`UiPath-WorkFusion/OWS/OpenWebSearchUiPath/OpenWebSearchFlow/OpenWebSearchFlow.flow:5`). Functions are Python; apps are TypeScript |
| Linked by timing or people? | **No** | CoreWF had 9 commits in 2026, the last on 08-06; it was quiet during the migration's September peak. One shared contributor, Daniel Dinca (CoreWF `724fb36`, 2024). Inference: shared staffing, not a technical link |

**The 2 indirect projects.** The only XAML in UiPath-WorkFusion is in two RPA processes:
`Isaac/IsaacUiPath/Demo` and `OWS/OpenWebSearchUiPath/OpenWebSearchPreview`.
- Both use `"targetFramework": "Portable"` (cross-platform) and VB expressions. They depend on
  `UiPath.System.Activities` 26.6.2, which is an activities package, not CoreWF itself.
- Their XAML imports `System.Activities`, exactly the assembly name and namespace CoreWF provides.
  So the Robot very likely runs them on a CoreWF build bundled inside it.
- The unmerged branch `feat/ede-sos-ui` would add a third such process.

**What would change the verdict**
- A NuGet reference or C# host code in UiPath-WorkFusion would make CoreWF a direct dependency.
- More XAML robots would deepen the indirect link.
- Porting the two XAML processes to Functions would make CoreWF unrelated.

## State: maintenance

- **Phases:**
  1. 2016–2018: Dustin Metzgar's port.
  2. 2018–2020: UiPath takes over (Lucian Bargaoanu from 2018-11).
  3. 2020–2022: rebuilt as `UiPath.Workflow`.
  4. 2023–2026: maintenance tracked by STUD- and ROBO- tickets.
- **Recent work:** expression-compiler and serialization fixes, Studio validation messages, and
  moving CI to a managed GitHub pool (the latest commit).
- **Branches:**
  - `main` has been frozen since at 6.0.3.
  - `support/23.10`, `support/24.10` and `support/25.10` look like servicing branches for UiPath's
    yearly releases (Inference). `release/s184` was last touched on .
  - No branch is active; the newest tip is .
- **Contributors:** mostly Lucian Bargaoanu and Dustin Metzgar. Also Alexandru Oltean, Mihai
  Ciureanu, Marius Bughiu, Alexandru-Ionut Mustata, gpanaitescu and others. Recently: Pavel Drăgan
  and Dan Boanta. CODEOWNERS: @aoltean16, @vuplea.

## Observations (for the CoreWF owners, not tasks)

- **Stale public package.** `README.md:79` points users to nuget.org, but public releases come only
  from `main`, frozen since 2022. Inference: nuget.org's package is probably 2022-era (not checked;
  that needs the network).
- **Wrong badge label.** `README.md:85` says "MyGet (dev)" but links the Azure feed `UiPath-Internal`.
- **Old runtime.** Everything targets .NET 6, which Microsoft stopped supporting in
  (outside knowledge). CI already installs the .NET 8 SDK.
- **Robot upgrades can change XAML behaviour with no repo diff.** Inference: the tenant's Robot
  decides which CoreWF build runs the migration's XAML robots.

## Key files

- `CoreWF/README.md`
- `CoreWF/azure-pipelines.yaml`, with `.pipelines/build.yaml` and `.pipelines/release.yaml`
- `UiPath.Workflow.Runtime.csproj`
- The two XAML robots: `Demo/project.json` and `OpenWebSearchPreview/project.json`