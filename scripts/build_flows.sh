#!/usr/bin/env bash
# build_flows.sh [solution-dir]        (default: <repo>/EvMigEvelyn)
#
# Builds the two Maestro Flows of the Evelyn CSV path with `uip` commands only (DEC-11). The `.flow` files
# are the SOURCE; nothing in them is edited by hand. Child first (its `in` variables become the Flow-call
# node's fields), then parent.
#
#   EvMigNamesScreeningFlow      <- Evelyn BP "Names Screening" (first slice: Screening System -> csv-schema-producer)
#   EvMigCsvFileIngestionFlow    <- Evelyn BP "CSV File Ingestion" (monitor -> file loop -> record loop -> call)
#
# Needs: the Solution (.uipx) with the three function projects already registered
#   (`uv run uipath init` in each, then `uip solution projects add ./<name>`): EvMigCsvMonitorTask,
#   EvMigCsvTask, EvMigCsvSchemaProducer. Writes only inside <solution-dir>. Touches no tenant: init,
#   node/edge/variable add, validate, format and solution pack --dry-run are all local (tested with an
#   empty HOME in a copy outside ~/UiPathRepos, i.e. no login: `uip` also takes a login from any .uipath/
#   folder above the working folder). Needs `uip` 1.203.0 and `jq` on PATH.
#
# To rebuild over an existing build, first remove both Flow projects (see the message at the "already exists" check).
#
# Node ids come from the CLI (camelCase of the label + counter). The script says which id it expects and
# stops if the CLI derives another, so every edge below can name its nodes by id.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
SOL=${1:-$ROOT/EvMigEvelyn}
cd "$SOL"   # `registry ... --local` needs the .uipx in CWD, its parent or grandparent
LOG=$(mktemp -d)
CHILD=EvMigNamesScreeningFlow
PARENT=EvMigCsvFileIngestionFlow
CF=$CHILD/$CHILD.flow
PF=$PARENT/$PARENT.flow

fail() { echo "build_flows: $*" >&2; echo "build_flows: stderr of every uip call is in $LOG/uip.stderr" >&2; exit 1; }

# --- helpers -------------------------------------------------------------------------------------

# node type of an in-solution project. Each function project has two entries in the local registry
# (Category function, and agent.tool.function); each Flow project has one (Category flow). The type is
# uipath.core.<function|flow>.<key of the project's process resource>: it changes on every new Solution.
type_of() { # <function|flow> <DisplayName>
  local t
  t=$(uip maestro flow registry search "$2" --local --output plain \
        --output-filter "[?DisplayName=='$2' && Category=='$1'].NodeType | [0]" 2>>"$LOG/uip.stderr") || t=
  [[ $t == uipath.core.$1.* ]] || fail "no in-solution $1 node type for '$2' (did you run 'uipath init' in it and 'uip solution projects add'?)"
  echo "$t"
}

# node <file> <node-type> <label> <expected-id> <input-json|''> [parent-id]
node() {
  local file=$1 type=$2 label=$3 want=$4 input=$5 parent=${6:-} got
  local args=("$type" --label "$label")
  [[ -n $input ]]  && args+=(--input "$input")
  [[ -n $parent ]] && args+=(--parent "$parent")   # sets parentId: required for every loop-body node
  got=$(uip maestro flow node add "$file" "${args[@]}" 2>>"$LOG/uip.stderr" | jq -r '.Data.Node.Id') \
    || fail "node add '$label' failed in $file"
  [[ $got == "$want" ]] || fail "node '$label' got id '$got', expected '$want'"
  printf 'ID\t%s\t%s\t%s\t%s\n' "${file%%/*}" "$label" "$got" "$type"
}

# edge <file> <source-id> <target-id> [--source-port P] [--target-port P]   (defaults output -> input)
edge() { local f=$1; shift; uip maestro flow edge add "$f" "$@" >/dev/null 2>>"$LOG/uip.stderr" || fail "edge add failed: $*"; }

# variable <file> <id> <type> <description> [--sub-type T]    (Flow input = direction in, bound to the trigger)
variable() {
  local f=$1 id=$2 type=$3 desc=$4; shift 4
  uip maestro flow variable add "$f" "$id" --direction in --type "$type" --description "$desc" "$@" \
    >/dev/null 2>>"$LOG/uip.stderr" || fail "variable add failed: $id"
}

# validate must say Valid AND carry no Warnings. (validate exits 0 with warnings; they sit in .Data.Warnings.)
check() {
  local out
  out=$(uip maestro flow validate "$1" 2>>"$LOG/uip.stderr") || { echo "$out" >&2; fail "validate failed: $1"; }
  jq -e '.Data.Status == "Valid" and (.Data.Warnings == null)' <<<"$out" >/dev/null \
    || { jq -r '.Data.Warnings' <<<"$out" >&2; fail "validate warnings in $1"; }
}

# assert <file> <jq-expression that must be true>
assert() { jq -e "$2" "$1" >/dev/null || fail "assertion failed in $1: $2"; }

[[ ! -e $CHILD && ! -e $PARENT ]] || fail "$CHILD or $PARENT already exists. To rebuild, for both: uip solution projects remove <dir>; rm -rf <dir>   (remove takes the folder, not project.uiproj)"

# --- the child: EvMigNamesScreeningFlow ----------------------------------------------------------

uip maestro flow init "$CHILD" >/dev/null 2>>"$LOG/uip.stderr" || fail "flow init $CHILD"   # also registers it in the .uipx

# Trigger "start" (core.trigger.manual) already exists. Its inputs are the Flow's `in` variables.
# rest_request is NOT declared: it is an optional producer input that the CSV flow never sets.
variable "$CF" screened_data  object "One screened alert (ScreenedData), from csv-task"
variable "$CF" wle_list       array  "The alert's watch-list entries (WleData)" --sub-type object
variable "$CF" request_id     string "request_id: the data file's name or a UUID"
variable "$CF" provider_id    string "provider_id: CSV on this path (Evelyn: input-task stamps it)"
variable "$CF" bp_run_id      string "Instance id of the CSV flow run (Evelyn: the BP run id)"
variable "$CF" bp_start_time  string "UTC start time of the CSV flow run (Evelyn: BP start time)"

PRODUCER=$(type_of function EvMigCsvSchemaProducer)

# Evelyn rule "Screening System": CSV outcome only; the other six providers are not ported.
node "$CF" core.logic.decision "Screening System" screeningSystem1 \
  '{"expression": "$vars.start.output.provider_id === \"CSV\"", "trueLabel": "CSV", "falseLabel": "Other providers"}'

# Evelyn step csv-schema-producer. Object and array inputs use the object form (DEC-11): with a plain
# "=js:..." string, `flow pack` writes "type":"string" for them into the call's inputSchema in the BPMN;
# with the object form it writes "object".
# rest_request is left to `node add`, which writes it as null (the producer treats null, "" and {} as absent, DEC-3).
node "$CF" "$PRODUCER" "csv-schema-producer" csvSchemaProducer1 "$(cat <<'EOF'
{
  "screened_data": {"type": "jsExpression", "expression": "$vars.start.output.screened_data", "fieldType": "object"},
  "wle_list":      {"type": "jsExpression", "expression": "$vars.start.output.wle_list",      "fieldType": "array"},
  "request_id":    "=js:$vars.start.output.request_id",
  "provider_id":   "=js:$vars.start.output.provider_id",
  "bp_run_id":     "=js:$vars.start.output.bp_run_id",
  "bp_start_time": "=js:$vars.start.output.bp_start_time"
}
EOF
)"

# Evelyn SubEnd "Final Results", and the false branch of "Screening System" (no Evelyn equivalent).
node "$CF" core.control.end "Final Results"                 finalResults1 ''
node "$CF" core.control.end "Other providers (not ported)"  otherProvidersNotPorted1 ''

edge "$CF" start screeningSystem1                                         # trigger.output -> decision.input
edge "$CF" screeningSystem1 csvSchemaProducer1 --source-port true         # CSV
edge "$CF" csvSchemaProducer1 finalResults1                               # function.output -> end.input
edge "$CF" screeningSystem1 otherProvidersNotPorted1 --source-port false

check "$CF"
uip maestro flow format "$CF" >/dev/null 2>>"$LOG/uip.stderr" || fail "format $CF"
check "$CF"

assert "$CF" '[.edges[] | "\(.sourceNodeId).\(.sourcePort)>\(.targetNodeId).\(.targetPort)"] | sort == ([
  "csvSchemaProducer1.output>finalResults1.input",
  "screeningSystem1.false>otherProvidersNotPorted1.input",
  "screeningSystem1.true>csvSchemaProducer1.input",
  "start.output>screeningSystem1.input"] | sort)'
assert "$CF" '[.variables.globals[] | select(.direction == "in") | .id] == ["screened_data","wle_list","request_id","provider_id","bp_run_id","bp_start_time"]'
# format must not have emptied the object inputs (it did once, DEC-11); `validate` would not notice
assert "$CF" '.nodes[] | select(.id == "csvSchemaProducer1") | .inputs
  | (.screened_data.type == "jsExpression") and (.screened_data.expression == "$vars.start.output.screened_data")
  and (.wle_list.type == "jsExpression") and (.wle_list.expression == "$vars.start.output.wle_list")'

# --- the parent: EvMigCsvFileIngestionFlow -------------------------------------------------------

uip maestro flow init "$PARENT" >/dev/null 2>>"$LOG/uip.stderr" || fail "flow init $PARENT"

MONITOR=$(type_of function EvMigCsvMonitorTask)
TASK=$(type_of function EvMigCsvTask)
CALL=$(type_of flow "$CHILD")        # exists only now that the child Flow project is registered; its `in` variables are copied at `node add`

# Trigger "start": no inputs (Evelyn's BP has NO_DATA input).

# Evelyn step csv-monitor-task. No inputs.
node "$PF" "$MONITOR" "csv-monitor-task" csvMonitorTask1 ''

# Implicit Evelyn fan-out over the monitor's rows: one record per data file.
node "$PF" core.logic.loop "For each data file" forEachDataFile1 \
  '{"collection": "=js:$vars.csvMonitorTask1.output.rows", "parallel": false}'

# Evelyn step csv-task, once per file (loop body: --parent).
node "$PF" "$TASK" "csv-task" csvTask1 "$(cat <<'EOF'
{
  "data_file_location":   "=js:$vars.forEachDataFile1.currentItem.data_file_location",
  "format_file_location": "=js:$vars.forEachDataFile1.currentItem.format_file_location"
}
EOF
)" forEachDataFile1

# Implicit Evelyn fan-out over csv-task's rows: one record per alert. A loop inside the loop body.
node "$PF" core.logic.loop "For each record" forEachRecord1 \
  '{"collection": "=js:$vars.csvTask1.output.rows", "parallel": false}' forEachDataFile1

# Evelyn rule "Should proceed?": the stop row ({"stop": "true"}) goes to No, every other row to Yes.
node "$PF" core.logic.decision "Should proceed?" shouldProceed1 \
  '{"expression": "$vars.forEachRecord1.currentItem.stop !== \"true\"", "trueLabel": "Yes", "falseLabel": "No"}' forEachRecord1

# Evelyn ProcessCall "NSS-main-BP" (asynchronous, synchronous=false): Flow-call node, fireAndForget true.
# bp_run_id is the CSV flow's own instance id: `$metadata.InstanceId`, capital I (validate warns on `instanceId`).
# rest_request is left to `node add` here too. Its error port is armed below (Q17).
node "$PF" "$CALL" "NSS-main-BP" nssMainBp1 "$(cat <<'EOF'
{
  "screened_data": {"type": "jsExpression", "expression": "$vars.forEachRecord1.currentItem.screened_data", "fieldType": "object"},
  "wle_list":      {"type": "jsExpression", "expression": "$vars.forEachRecord1.currentItem.wle_list",      "fieldType": "array"},
  "request_id":    "=js:$vars.forEachRecord1.currentItem.request_id",
  "provider_id":   "CSV",
  "bp_run_id":     "=js:$metadata.InstanceId",
  "bp_start_time": "=js:$vars.csvMonitorTask1.output.bp_start_time",
  "fireAndForget": true
}
EOF
)" forEachRecord1

# Evelyn End "Final Results".
node "$PF" core.control.end "Final Results" finalResults1 ''

edge "$PF" start csvMonitorTask1
edge "$PF" csvMonitorTask1 forEachDataFile1
edge "$PF" forEachDataFile1 csvTask1 --source-port start                                  # loop.start -> first body node
edge "$PF" csvTask1 forEachRecord1                                                        # body node -> inner loop.input
edge "$PF" forEachRecord1 shouldProceed1 --source-port start
edge "$PF" shouldProceed1 nssMainBp1 --source-port true
edge "$PF" shouldProceed1 forEachRecord1 --source-port false --target-port continue       # Evelyn link 17: No -> next record
edge "$PF" nssMainBp1 forEachRecord1 --target-port continue                               # call -> next record
edge "$PF" forEachRecord1 forEachDataFile1 --source-port success --target-port continue   # inner loop done -> next file
edge "$PF" forEachDataFile1 finalResults1 --source-port success                           # outer loop done -> End
# Armed error port on csv-task (Q16/D-12): the CLI sets inputs.errorHandlingEnabled=true on csvTask1 by itself.
# A failed file is skipped and the other files go on; the failure stays visible on the node (csvTask1.error).
edge "$PF" csvTask1 forEachDataFile1 --source-port error --target-port continue
# Armed error port on the call (Q17): a child run that fails to start fails only that record, as an error answer to
# Evelyn's BP call fails only that record's step; the loop goes on to the next record (nssMainBp1.error keeps it).
edge "$PF" nssMainBp1 forEachRecord1 --source-port error --target-port continue

check "$PF"
uip maestro flow format "$PF" >/dev/null 2>>"$LOG/uip.stderr" || fail "format $PF"
check "$PF"

assert "$PF" '[.edges[] | "\(.sourceNodeId).\(.sourcePort)>\(.targetNodeId).\(.targetPort)"] | sort == ([
  "csvMonitorTask1.output>forEachDataFile1.input",
  "csvTask1.error>forEachDataFile1.continue",
  "csvTask1.output>forEachRecord1.input",
  "forEachDataFile1.start>csvTask1.input",
  "forEachDataFile1.success>finalResults1.input",
  "forEachRecord1.start>shouldProceed1.input",
  "forEachRecord1.success>forEachDataFile1.continue",
  "nssMainBp1.error>forEachRecord1.continue",
  "nssMainBp1.output>forEachRecord1.continue",
  "shouldProceed1.false>forEachRecord1.continue",
  "shouldProceed1.true>nssMainBp1.input",
  "start.output>csvMonitorTask1.input"] | sort)'
assert "$PF" '[.nodes[] | select(.parentId != null) | "\(.id)>\(.parentId)"] | sort == ([
  "csvTask1>forEachDataFile1","forEachRecord1>forEachDataFile1","nssMainBp1>forEachRecord1","shouldProceed1>forEachRecord1"] | sort)'
assert "$PF" '[.nodes[] | select(.inputs.errorHandlingEnabled == true) | .id] | sort == ["csvTask1","nssMainBp1"]'
assert "$PF" '.nodes[] | select(.id == "nssMainBp1") | .inputs
  | (.fireAndForget == true) and (.provider_id == "CSV") and (.bp_run_id == "=js:$metadata.InstanceId")
  and (.screened_data.type == "jsExpression") and (.screened_data.expression == "$vars.forEachRecord1.currentItem.screened_data")
  and (.wle_list.type == "jsExpression") and (.wle_list.expression == "$vars.forEachRecord1.currentItem.wle_list")'
# fireAndForget drops the call node's output: only .error stays in the variables, so nothing may read $vars.nssMainBp1.output
assert "$PF" '[.variables.nodes[] | select(.id | startswith("nssMainBp1.")) | .id] == ["nssMainBp1.error"]'
# `node add` wrote the child Flow's name binding (resourceSubType Flow) itself; nothing to hand-edit
assert "$PF" '[.bindings[] | select(.resourceSubType == "Flow" and .propertyAttribute == "name") | .default] == ["EvMigNamesScreeningFlow"]'

# --- the Solution --------------------------------------------------------------------------------

# No `uip solution resources refresh` here: it needs a login ("Not logged in" otherwise). Not needed for this
# check: `pack` syncs the resources itself, and `flow init` / `projects add` already wrote them.
uip solution pack . --dry-run >"$LOG/pack.out" 2>>"$LOG/uip.stderr" || fail "pack --dry-run"
jq -e '.Data.Status == "Valid"' "$LOG/pack.out" >/dev/null || fail "pack --dry-run is not Valid: $(cat "$LOG/pack.out")"

echo "build_flows: OK. Both Flows Valid with no warnings; solution pack --dry-run Valid. Logs: $LOG"
