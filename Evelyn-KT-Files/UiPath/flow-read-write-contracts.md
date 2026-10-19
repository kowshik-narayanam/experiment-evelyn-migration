# Flow read and write contracts

How every Maestro Flow node gets its inputs, how its outputs are named, and how a later node reads
them. Sources: the UiPath docs (the Flow pages under
  [variables and data flow](https://docs.uipath.com/maestro/automation-cloud/latest/user-guide/variables-and-data-flow)),
  the UiPath Flow skill (VE below), Flows in the ports, and local experiments.

Examples below use short names (AML, ITM, OWS-S, IAI, EDE, EO, FR) for Flows that were checked while writing these rules. The rules cover nearly every case in a ten-node Flow.

## 1. The one rule

`$vars` is one map for the whole run. When a node finishes, the engine puts its result in the map
under the node's ID. Any later node on the same path reads it by name. **Edges carry no data**:
they only say what runs after what.

In Java terms: `Map<String, NodeResult> vars`, and a node's input is
`vars.get("loadSettings1").output.run_id`. Nothing is passed from hand to hand, so node 10 can read

Every read has the same five pieces:

```
=js:$vars.loadSettings1.output.run_id
```

| Piece | Means | Who decides it |
|---|---|---|
| `=js:` | "The rest is JavaScript." Only in `.flow` JSON value fields; the canvas hides it | The file format |
| `$vars` | Everything this run has produced so far | The engine |
| `loadSettings1` | The **node ID** (or, for a process variable, the variable ID) | `node add --label "Load settings"` → camelCase + number (§7) |
| `.output` | The **slot**: what the node returned. Other slots: `.error`, `.currentItem`, `.status` | The node type (§2) |
| `.run_id` | A field of the result, then sub-fields: `.a.b`, `[0]`, `.length` | The callee's output contract: the Python output class, a Script's `return`, a child Flow's `out` variables |

**The check that always works:** `variables.nodes` in the `.flow` lists every `<id>.<slot>` the
Flow can read, with its schema. Example: `loadSettings1.output` with `run_id` and `min_tokens`
(FR, `variables.nodes`). Anything you write must be `$vars.` plus one of those IDs, or a global
variable ID, then a field from its schema.

## 2. Reading: what to write for each source

| You want | Write | Notes and evidence |
|---|---|---|
| A Flow input (`in` variable) | `$vars.start.output.<input>` | Through the trigger, **not** `$vars.<input>` (VE:169). The trigger is `start` when built by `uip`, `manualTrigger1` in Studio Web (AML:353) |
| Any earlier node's result, any distance | `$vars.<nodeId>.output.<field>` | FR: node 10 reads node 2, eight nodes back |
| A Python Function's result | `$vars.<fn>.output.<field of its output class>` | No extra wrapper. In Isaac, `.output.payload` and `.output.result` are field names the Python classes chose (OWS-S:248) |
| A Script's result | `$vars.<script>.output.<field>` | Whatever the script `return`s (FR: `$vars.trim1.output.name`) |
| A child Flow's result | `$vars.<flowNode>.output.<child out variable>` | OWS-S:422 `.output.owsResult`; |
| A subflow's result | `$vars.<subflow>.output.<its End output>` | EDE:375 |
| The current item, inside a Loop | `$vars.<loop>.currentItem` (and `.field`) | EO:195. Pass number: `.currentIteration`, from 1 (`node-loop` docs; the CLI declares it) |
| All passes, after a Loop | `$vars.<loop>.output` | An array, one entry per pass, keyed by body node ID: `.map(p => p.square1.output)` (ITM:2676). The docs describe it differently, see §8 |
| A node's failure | `$vars.<n>.error.message` (also `code`, `detail`, `category`, `status`) | Only when the node's error port is wired ([flow-error-handling](https://docs.uipath.com/maestro/automation-cloud/latest/user-guide/flow-error-handling)). OWS-S:422 |
| A human task's answer | `$vars.<task>.output.<form field>`; the button pressed is `$vars.<task>.status` | IAI:634; `actionApp1.status` declared at IAI:16139 |
| An HTTP call | `$vars.<http>.output.body`, `.statusCode`, `.headers` | [node-http-request](https://docs.uipath.com/maestro/automation-cloud/latest/user-guide/node-http-request) |
| An agent | `$vars.<agent>.output.content`, plus its declared output fields | [node-agent](https://docs.uipath.com/maestro/automation-cloud/latest/user-guide/node-agent) |
| An RPA workflow | `$vars.<rpa>.output.out_<Argument>` | |
| A Data Fabric query / create | `.output[0].Id` (a query returns an array) / `.output.Id` | AML:13693, AML:13243 |
| A process (`inout`) variable | `$vars.<variable>`, **no** `.output` | `$vars.document`, `$vars.providerState` (OWS-S:422) |
| A Decision's or Switch's result | Nothing to read: they route by port (`true`/`false`, a case) | EO:195 |

## 3. Writing: where each value is declared

| You want | How (CLI) | Lands in the `.flow` | Read back as |
|---|---|---|---|
| A Flow input | `uip maestro flow variable add F.flow alertId --direction in --type string` | `variables.globals` with `"triggerNodeId": "start"` (FR) | `$vars.start.output.alertId` |
| A node's output | Nothing: automatic | Node `outputs.output` and `variables.nodes "<id>.output"`, schema copied from the callee | `$vars.<id>.output…` |
| A node's input | `node add … --input '{"<callee field>": "=js:<where from>"}'` | Node `inputs.<field>` | (it is the callee's input) |
| A process variable | `variable add --direction inout`, then **Update Variable**: a hand edit of `variables.variableUpdates` | `variableUpdates.<nodeId> = {variableId, expression}`, set after that node finishes (OWS-S:2460) | `$vars.<variable>` |
| A Flow output | `variable add --direction out`, then the End node's `outputs` (hand edit) | End `outputs.<variable>.source = "=js:…"` (FR, `end1`) | The caller: `$vars.<flowNode>.output.<variable>` |

**A node input has two sides.** The key is the **callee's** field name, from its contract. The
value says where the data **comes from**, from any earlier node. Like a Java call with named
arguments:

| Example 2.8, node 10 | Left: the callee's field (`WriteScreeningResultFunction`, `ResultIn`) | Right: where from |
|---|---|---|
| `"alert_id": "=js:$vars.start.output.alertId"` | `alert_id` (Python, snake_case) | the Flow input `alertId` (Flow, camelCase) |
| `"run_id": "=js:$vars.loadSettings1.output.run_id"` | `run_id` | node 2's output field `run_id` |

**The three directions** (VE:63-67, 351):

| Direction | Read | Written by |
|---|---|---|
| `in` | `$vars.<trigger>.output.<id>` | The caller, at start. Read-only |
| `out` | (rarely read) | An End node's `outputs` only |
| `inout` | `$vars.<id>` | Update Variable (`variableUpdates`) after any node |

The docs say every variable is read-write
([variables-and-data-flow](https://docs.uipath.com/maestro/automation-cloud/latest/user-guide/variables-and-data-flow));
the skill says only `inout`. Follow the skill; the repo has 25 `inout` variables in 15 of its 32 files.

## 4. The three wrappers

| Wrapper | Where | Example |
|---|---|---|
| `"=js:<expr>"` | `.flow` value fields: node `inputs`, End `outputs.*.source`, Loop `collection`, `variableUpdates` | `"collection": "=js:$vars.generate1.output.numbers"` (EO:108) |
| Bare JavaScript, **no** `=js:` | Decision `expression`, Switch `cases.expression`, a Script's `script` | `"$vars.forEachNumber1.currentItem < 0"` (EO:195) |
| `{{ $vars.x }}` | Canvas text fields, inside a sentence | Not used in any of the 32 repo `.flow` files |

Two equivalent spellings in the JSON. Both mean "evaluate this JavaScript":

| String form | Object form (seen in EDE, AML, Kayla) |
|---|---|
| `"owsInput": "=js:$vars.start.output.request.providerPayload"` | `"owsInput": {"type": "jsExpression", "expression": "$vars.start.output.request.providerPayload", "fieldType": "object"}` (OWS-S:303-307) |

In the object form the expression has no `=js:`. A Script body can be `{"type": "literal", …}`
(AML:50). In the canvas you type only the expression; it shows neither form
([expression-syntax](https://docs.uipath.com/maestro/automation-cloud/latest/user-guide/expression-syntax)).

**JavaScript you can use:** `?.`, `??`, `||`, `a ? b: c`, template literals, arrow functions,
`map`/`filter`/`reduce`, spread `...`, `Object.keys`, `JSON`, `Math`. **Blocked:** `fetch`,
`XMLHttpRequest`, `eval`, `Function` ([node-script](https://docs.uipath.com/maestro/automation-cloud/latest/user-guide/node-script));
the skill also lists `console`, timers and `async` (VE:570-577). `return` only in a Script.

## 5. What a node can see, and what `validate` catches

| Case | At runtime | `validate` says | Evidence |
|---|---|---|---|
| An earlier node on the same path, any distance | Readable | Valid | FR |
| The Flow input, from anywhere | Readable | Valid | FR |
| Node ID misspelled (`loadSetings1`) | Nothing: a Script faults, a connector gets an empty value | **Error**, with "did you mean" | Experiment on a copy of FR |
| Field misspelled (`.output.runId`) | `undefined` | **Warning only**, still `Valid` | Same |
| A node that runs later (`$vars.end1…` in node 10) | No value yet | **Error**: "runs AFTER" | Same |
| A node on a Decision branch that wasn't taken | `undefined` | **Valid, no warning** | A copy of FR with a Decision before node 10 |
| A node in a parallel sibling branch | Not visible | not tested | [variables-and-data-flow](https://docs.uipath.com/maestro/automation-cloud/latest/user-guide/variables-and-data-flow) |
| Inside a Loop or subflow, the parent's nodes | Readable (docs); not visible (skill) | not tested | §8 |

So: **read the warnings, not just the status**, and guard every read from a branch that may not
have run: `$vars.noteLong1.output?.note ?? "none"`.

One more, from EDE's own code comment (EDE:630): in a **parallel** Loop, a body node that produced
nothing in this pass can still show **another pass's** value. EDE checks the result against
`currentItem` before trusting it. Not in the docs.

## 6. Reading a long expression

The long ones in the repo are the same rule with guards around it. To read one:

1. Drop the `=js:`.
2. Find each `$vars.X`. X is a node ID (look it up in the node list) or a process variable.
3. Read the rest left to right: the slot (`.output`), then the field path.
4. Decode the guards:

| Symbol | Means |
|---|---|
| `a?.b` | `b` of `a`, or `undefined` if `a` is missing (no crash) |
| `a ?? b` | `a`, or `b` if `a` is `null`/`undefined` |
| `a \|\| b` | The older form of the same, also replaces `""`, `0`, `false` |
| `c ? a: b` | If `c` then `a` else `b` |
| `?.[0]`, `?.["key"]` | Index or key, skipping if missing |
| `{...x, k: v}` | Copy of `x` plus or overriding `k` |
| `arr.map(p => p.n1.output)` | One value per element |
| `( => { … })` | An inline function, run at once |

**Why they get long**, with a real one each:

| Pattern | Expression (shortened) | Where |
|---|---|---|
| Only one of several branches ran | `$vars.persistDeferralQueryGatewayDecision?.output?.[0]?.Id ?? $vars.persistDeferralUpdateGatewayDecision?.output?.Id ?? $vars.persistDeferralCreateGatewayDecision?.output?.Id` | AML:16678 |
| Unwrapping a Loop's passes | `$vars.counterpartyServiceFanOut1.output.map(item => item.emitCounterpartyServiceResult1.output)` | ITM:2676 |
| Checking a child Flow's error first | `$vars.openwebsearchflow1.error ? null: $vars.openwebsearchflow1.output.owsResult` | OWS-S:422 |
| Keep or replace a process variable | `$vars.fileIngestionUpdateDeferralListProcessor1.output.document ?? $vars.document` |, a common idiom in `variableUpdates` |
| A deep contract | `$vars.prepareForHumanTaskProcessor1.output.payload.manual_task_input_data.alertDetailsList` | IAI:634 |
| Unsure of a connector's response shape | `.output?.[0]?.Id ??.output?.items?.[0]?.Id ??.output?.Items?.[0]?.Id` | AML:15588 |

The first one, piece by piece: "the gateway decision's `Id` from the **query** node (its first
row), or else from the **update** node, or else from the **create** node". Only one of the three
ran, so `?.` turns the other two into `undefined` and `??` moves on to the next.

## 7. Node IDs

| Built by | ID | Example |
|---|---|---|
| `uip maestro flow node add --label "…"` | camelCase(label) + a counter | "Load settings" → `loadSettings1`, a second one → `loadSettings2` |
| `node add` with no label | The type's default | `script1`, `decision1`, `httpRequest1` |
| `uip maestro flow init` | The trigger is `start` | every playground Flow |
| Studio Web | Named by type, label ignored | `manualTrigger1`, `function1`; "HITL Deferral Approve" is `actionApp1` (IAI:1279) |
| By hand | Anything | EDE's `sosLookup` |

- **Renaming a label doesn't change the ID.** `id` and `display.label` are separate keys; EDE's
  `mock1` is labelled "PostProcessing". Changing an ID by hand means changing every
  `$vars.<old>`, the `variables.nodes` entries, the edges and the `layout` keys.
- Pick labels that read well as IDs **before** wiring
- IDs must start with a letter (the skill's file-format reference). `uip` turned "2nd step" into
  `2ndStep1` and `validate` didn't object.

## 8. Where the sources disagree

Trust the CLI's own declarations (what `node add` writes into `variables.nodes`) first, then the
repo, then the skill, then the docs. Confirm on the tenant before relying on any of these.

| Topic | One says | The other says |
|---|---|---|
| Loop pass number | Docs `control-flow`: `currentIndex`, from 0 | Docs `node-loop`, the skill and the CLI: `currentIteration`, from 1 |
| Loop output after it ends | Docs `node-loop`: an array of returned values | Skill and Isaac (ITM:2676): entries keyed by body node ID |
| Subflow sees the parent's nodes | Docs `subflows`: yes | Skill (VE:605): no; pass values in as subflow inputs |
| Which variables are writable | Docs: all | Skill: only `inout`, through `variableUpdates` |
| `variableUpdates` expression form | Skill VE:275-306: object form | Isaac at file version 1.9: `"=js:…"` strings (OWS-S:2460) |
| Text templates | Docs: `{{ $vars.x }}` | Skill VE:399-407: `{ }` |
| Merge | Docs `control-flow`: waits for the branch that ran | Docs `node-merge` and the skill: waits for all; hangs after a Decision |
