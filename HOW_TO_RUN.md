# How to run it

Four levels. Levels 1-3 run on your machine and touch no tenant. Level 4 is the tenant run, written as steps for
you: nobody has run it yet. Each step ends with a **Check**. Run the commands from the repo root unless a step says
otherwise. Tools: `uv` 0.13.0, Python 3.11 (uv fetches it), `uip` 1.203.0, `jq`, `rsync`, `uuidgen`, `unzip`, and a system
`python3` for the two stdlib scripts (`scripts/entities.py`, `scripts/check_citations.py`).

## Get it

The repo is local only (no remote). To work in a fresh copy, without the virtual environments and local-run files:

```bash
rsync -a --delete --exclude .venv --exclude .local-run --exclude .pytest_cache --exclude __pycache__ ~/UiPathRepos/experiment-evelyn-migration/ /tmp/evmig-copy/
```

`--delete` matters when the copy already exists: it removes files the repo no longer has, such as an older wheel in a
function's `wheels/` beside the new one (owner's tenant run, 2026-10-19: `evmig_nss-0.1.1` stayed beside `0.1.2`).
The excluded folders are left alone.

```bash
cd /tmp/evmig-copy
```

**Check:** `ls` shows `AGENTS.md CLAUDE.md EvMigEvelyn HOW_TO_RUN.md README.md data docs evmig-nss scripts`.

## Level 1: tests

Each suite builds its own `.venv` on the first run (`uv` downloads the packages; the library comes from the wheel
in each function's `wheels/`).

```bash
(cd evmig-nss && uv run pytest -q)
```

**Check:** `465 passed`.

```bash
(cd EvMigEvelyn/EvMigCsvMonitorTask && uv run pytest -q)
```

**Check:** `33 passed`.

```bash
(cd EvMigEvelyn/EvMigCsvTask && uv run pytest -q)
```

**Check:** `148 passed`.

```bash
(cd EvMigEvelyn/EvMigCsvSchemaProducer && uv run pytest -q)
```

**Check:** `35 passed`.

```bash
python3 -I scripts/entities.py
```

**Check:** `EvMigTransaction: 14 fields`, `EvMigAlertAnalytics: 20 fields`, `EvMigHitAnalytics: 14 fields`, and no
`FAIL` line. (It reads Evelyn's Liquibase files from `~/WorkfusionRepos/NSS/names-screening`.)

## Level 2: a local run of the three functions

The same as the CSV flow, by hand: the monitor once, `csv-task` once per data file, the producer once per record.
`EVMIG_LOCAL_BUCKET_DIR` makes the library serve the bucket from `data/`, and `EVMIG_LOCAL_DATAFABRIC_FILE` keeps the
Data Fabric rows in a JSON file instead of a tenant. No login is needed.

```bash
R=$(pwd)
```

```bash
export EVMIG_LOCAL_BUCKET_DIR="$R/data" EVMIG_LOCAL_DATAFABRIC_FILE="$R/.local-run/datafabric.json"
```

```bash
rm -rf .local-run && mkdir .local-run
```

**2a. `csv-monitor-task`:**

```bash
(cd EvMigEvelyn/EvMigCsvMonitorTask && uv run uipath run main '{}' --output-file "$R/.local-run/monitor.json")
```

**Check:** `jq -r '.rows[].data_file_location' .local-run/monitor.json` prints three keys, `…/data/batch/screening_batch_2.csv`,
`…/data/header_only.csv`, `…/data/screening_batch_1.csv` (not `notes.txt`); `jq -r .bp_start_time .local-run/monitor.json`
prints a UTC time ending in `Z`. The line "Resource overwrites config file not found" is harmless.

**2b. `csv-task`, once per data file:**

```bash
i=0; jq -c '.rows[]' .local-run/monitor.json | while read -r row; do i=$((i+1)); (cd EvMigEvelyn/EvMigCsvTask && uv run uipath run main "$row" --output-file "$R/.local-run/csvtask-$i.json"); done
```

**Check:** `jq -c '[.rows[] | {stop, request_id, id: .screened_data.id}]' .local-run/csvtask-*.json` prints one record
from `screening_batch_2.csv` (a generated id), one stop row (`"stop":"true"`) and two records from
`screening_batch_1.csv` (`A-100`, `A-200`). The log of file 3 has "Parsing completed. 2 out of 3 alerts will proceed to
NSS main Business Process." and an error block listing lines 4 and 7: that is the mock data working as designed
(`data/README.md`).

**2c. `csv-schema-producer`, once per record**, with one run id for the whole run (the CSV flow passes its
`$metadata.InstanceId`):

```bash
RUN=$(uuidgen | tr A-Z a-z); BPT=$(jq -r .bp_start_time .local-run/monitor.json)
```

```bash
for f in .local-run/csvtask-*.json; do jq -c '.rows[] | select(.stop != "true")' "$f" | while read -r rec; do in=$(jq -c --arg r "$RUN" --arg t "$BPT" '{screened_data, wle_list, request_id, provider_id: "CSV", bp_run_id: $r, bp_start_time: $t}' <<<"$rec"); (cd EvMigEvelyn/EvMigCsvSchemaProducer && uv run uipath run main "$in" --output-file "$R/.local-run/producer.json"); done; done
```

**Check:**

```bash
jq -c 'to_entries[] | {entity: .key, rows: (.value | length)}' .local-run/datafabric.json
```

prints `EvMigTransaction-entity` 3, `EvMigAlertAnalytics-entity` 3, `EvMigHitAnalytics-entity` 5. Run 2c again: the
counts stay the same (a rerun overwrites the transaction and adds no duplicate rows, D-7).

**2d. Clean up.** `uv run uipath init` leaves an empty `.env` in a function folder, and `pack` would ship it. `uipath run`
created none in the Phase 6 check; this command is a safety net:

```bash
find EvMigEvelyn -name .env -size 0 -delete
```

**Check:** `find EvMigEvelyn -name .env` prints nothing. (A `.env` that is not empty means someone ran `uipath auth`:
don't open it; tell the owner.)

## Level 3: the Flows, locally

```bash
cd EvMigEvelyn
```

```bash
uip maestro flow validate EvMigNamesScreeningFlow/EvMigNamesScreeningFlow.flow --output json | jq -c '{status: .Data.Status, warnings: .Data.Warnings}'
```

```bash
uip maestro flow validate EvMigCsvFileIngestionFlow/EvMigCsvFileIngestionFlow.flow --output json | jq -c '{status: .Data.Status, warnings: .Data.Warnings}'
```

**Check:** both `{"status":"Valid","warnings":null}`. `validate` exits 0 even with warnings, so read them.

```bash
uip solution pack . --dry-run --output json | jq -c .Data
```

**Check:** `"Status":"Valid"`. `--dry-run` writes nothing. A `pack` without it rewrites all 11 files under
`resources/` (it adds `"isOverridable": true` to each): don't commit that, and pack into a copy.

**Rebuild check:** the Flows are built only by `scripts/build_flows.sh`. Rebuild them in a scratch copy and compare:

```bash
cd ..
```

```bash
T=$(mktemp -d) && rsync -a --exclude .venv EvMigEvelyn/ "$T/EvMigEvelyn/"
```

```bash
(cd "$T/EvMigEvelyn" && uip solution projects remove ./EvMigCsvFileIngestionFlow && uip solution projects remove ./EvMigNamesScreeningFlow && rm -rf EvMigCsvFileIngestionFlow EvMigNamesScreeningFlow)
```

```bash
scripts/build_flows.sh "$T/EvMigEvelyn"
```

**Check:** the last line starts with `build_flows: OK. Both Flows Valid with no warnings; solution pack --dry-run Valid.`
(1-2 minutes). Then:

```bash
for F in EvMigNamesScreeningFlow EvMigCsvFileIngestionFlow; do diff <(scripts/normalize_flow.sh EvMigEvelyn/$F/$F.flow) <(scripts/normalize_flow.sh "$T/EvMigEvelyn/$F/$F.flow") && echo "$F same"; done
```

**Check:** `EvMigNamesScreeningFlow same` and `EvMigCsvFileIngestionFlow same`. `normalize_flow.sh` blanks generated
ids and drops what the Studio Web designer adds (positions, sizes, `uniqueId`, `collapsed`, copied `outputs` and
icons, `.in-solution` categories, the error handle it draws). So a Flow tidied in the designer passes, and a changed
input, expression, edge, variable or node fails.

These `uip` commands are local. To prove it, run them in `/tmp/evmig-copy` with `HOME=$(mktemp -d)` in front:
`uip login status` then says `Not logged in`, and they still work. Inside `~/UiPathRepos` an empty HOME is not
enough: `uip` also looks for a login in every `.uipath/` folder above the working folder, and
`~/UiPathRepos/.uipath/` holds one. (`uip` still checks for its own updates over the network.)

## Level 4: on the tenant (for the owner)

Stage A passed on 2026-10-19 (owner's tenant run: A0-A4 and the optional rerun). Stage B has not run yet. In two
stages, so that a failure points at one cause:
- **Stage A**, the main flow alone with one record: Data Fabric from a job, the wheel with real dependencies,
  `UIPATH_FOLDER_KEY`, the object-typed `screened_data` input.
- **Stage B**, the CSV flow with the three mock records: the bucket and its listing, the two loops, the Decision,
  `fireAndForget: true`, `$metadata.InstanceId`, the object and array inputs passed from Flow to Flow.

Section C removes from the tenant what both stages made.

Data Fabric budget: about 9 calls per record, about 80 for the first pass of both stages including checks and
clean-up, plus up to 30 for B4's wait; the Community plan allows 1,000 a day. Whether your tenant is Community is not visible read-only.

Before you start: `flow debug` uploads the Solution to Studio Web and writes your Studio Web `SolutionId` into
`EvMigEvelyn/EvMigEvelyn.uipx`, and `resources refresh` adds fields to files under `EvMigEvelyn/resources/` (as does a
`pack` without `--dry-run`, level 3). Don't commit those changes: run level 4 in the `/tmp/evmig-copy` of "Get it",
so they stay out of the repo. A new terminal forgets the shell variables below: B0 sets them again.

### A0. Login

```bash
uip --version
```

```bash
uip login status
```

**Check:** `1.203.0` (the `.flow` files were built with it), and `Logged in` with your tenant. If not, run
`uip login` (it opens a browser).

### A1. Create the three entities

```bash
uip df entities list --native-only --output plain --output-filter "[?Name=='EvMigTransaction' || Name=='EvMigAlertAnalytics' || Name=='EvMigHitAnalytics'].Name"
```

**Check:** it prints nothing (none exist yet).

```bash
uip df entities create EvMigTransaction --file EvMigEvelyn/entities/EvMigTransaction.create.json
```

```bash
uip df entities create EvMigAlertAnalytics --file EvMigEvelyn/entities/EvMigAlertAnalytics.create.json
```

```bash
uip df entities create EvMigHitAnalytics --file EvMigEvelyn/entities/EvMigHitAnalytics.create.json
```

**Check:** each prints `"Code": "EntityCreated"`, and the list command above now prints the three names. These are the
first `DATETIME_WITH_TZ`, `BOOLEAN` and `MULTILINE_TEXT` fields created by command on your tenant; a refusal names
the field ("When a run fails" has the steps). The server also refuses some names the CLI lets through: it
refused `Uuid` on 2026-10-19 (D-5), and it reports one name per attempt.

```bash
TXN_ENTITY=$(uip df entities list --native-only --output plain --output-filter "[?Name=='EvMigTransaction'].Id | [0]")
```

```bash
ALERT_ENTITY=$(uip df entities list --native-only --output plain --output-filter "[?Name=='EvMigAlertAnalytics'].Id | [0]")
```

```bash
HIT_ENTITY=$(uip df entities list --native-only --output plain --output-filter "[?Name=='EvMigHitAnalytics'].Id | [0]")
```

**Check:** `echo "$TXN_ENTITY $ALERT_ENTITY $HIT_ENTITY"` prints three GUIDs.

### A2. Debug the main flow with one record

The input: one alert (Alice Wonderland) with two hits, a fresh uuid each time.

```bash
jq -n --arg u "$(uuidgen | tr A-Z a-z)" --arg t "$(date -u +%Y-%m-%dT%H:%M:%S.000Z)" '{screened_data: {uuid: $u, id: "A-1", clientId: "5", category: "Sanctions", entityType: "INDIVIDUAL", name: {fullName: "Alice Wonderland"}, goldDecision: "1"}, wle_list: [{id: "H-1", category: "Sanctions", entityType: "INDIVIDUAL", name: {fullName: "Alyce Wonderland"}, goldDecision: "1"}, {id: "H-2", category: "Sanctions", entityType: "LOCATION", name: {fullName: "Gill Bates"}, goldDecision: "0"}], request_id: "alice.csv", provider_id: "CSV", bp_run_id: "11111111-2222-3333-4444-555555555555", bp_start_time: $t}' > /tmp/evmig-stage-a.json
```

```bash
cd EvMigEvelyn
```

```bash
uip solution resources refresh
```

```bash
uip maestro flow debug EvMigNamesScreeningFlow --inputs "$(cat /tmp/evmig-stage-a.json)" --output json > /tmp/evmig-debug-a.json
```

It packs and uploads the Solution, runs the Flow once and waits (1-5 minutes; a cold function job takes about 50 s).

**Check:**

```bash
jq '.Data.finalStatus' /tmp/evmig-debug-a.json
```

prints `"Completed"`, and

```bash
jq -r '.Data.variables.elements[] | select(.outputs.Error) | "\(.elementId) \(.outputs.Error.detail)"' /tmp/evmig-debug-a.json
```

prints nothing. The producer's output (`jq '.Data.variables.elements[] | select(.elementId == "csvSchemaProducer1")'
/tmp/evmig-debug-a.json`) should show `transaction_id` equal to the input's uuid, `wle_count` 2, `request_id`
`alice.csv`, `is_internal_request` true.

**Check the wheel was installed** from the function's job log. A debug run's function jobs run in your personal
workspace, not in `Debug_<Flow>`, and `jobs list` shows their `ProcessName` as `""`. `jobs get` shows `ProcessType`
`Function`, `ServerlessJobType` `PythonCodedFunction`, and `ParentJobKey` equal to the debug output's
`.Data.instanceId` (owner's tenant run, 2026-10-19). So find the job by its parent:

```bash
WORKSPACE=$(uip or folders list --limit 100 --output plain --output-filter "[?Type=='Personal'].Path | [0]")
```

```bash
INSTANCE=$(jq -r .Data.instanceId /tmp/evmig-debug-a.json)
```

```bash
for K in $(uip or jobs list --folder-path "$WORKSPACE" --limit 20 --output json | jq -r '.Data[].Key'); do [ "$(uip or jobs get $K --output json | jq -r '.Data.ParentJobKey')" = "$INSTANCE" ] && echo "$K"; done
```

**Check:** it prints one job key (the producer's). It looks at your 20 newest workspace jobs, so run it soon after
the debug run.

`jobs logs` returns the newest lines first and stops at `--limit`, and the install lines are among the oldest. So ask
for 1,000 and check that fewer came back:

```bash
uip or jobs logs <job key> --limit 1000 --output json --output-filter "[].Message" > /tmp/evmig-a2-log.json
```

```bash
jq '.Data | length' /tmp/evmig-a2-log.json
```

**Check:** below 1000, so the whole log came back. (At 1000, run it again with `--offset 1000` for the older lines.)

```bash
jq -r '.Data[].Message' /tmp/evmig-a2-log.json | grep -e 'evmig-nss==' -e 'Hash mismatch'
```

**Check:** a line `+ evmig-nss==0.1.2 (from file:///tmp/home/.job-data/<id>/wheels/evmig_nss-0.1.2-py3-none-any.whl)`,
and no `Hash mismatch`. (Owner's tenant run, 2026-10-19: the log was 112 lines and had that line.)

### A3. Check the rows

```bash
UUID=$(jq -r '.screened_data.uuid' /tmp/evmig-stage-a.json)
```

```bash
uip df records query "$TXN_ENTITY" --limit 100 --body "{\"filterGroup\": {\"logicalOperator\": 0, \"queryFilters\": [{\"fieldName\": \"TransactionUuid\", \"operator\": \"=\", \"value\": \"$UUID\"}]}}" --output json --output-filter "Items[].{status: Status, startBpUuid: StartBpUuid, bpStartTime: BpStartTime, dwVariation: DwVariation, dwVersion: DwVersion, modelVersion: ModelVersion, ext: ExtRecordId, clientId: ClientId}"
```

**Check:** one row: `NEW`, `StartBpUuid` `11111111-2222-3333-4444-555555555555`, `BpStartTime` the same instant as
the input, `DwVersion` `0.1.2`, `ModelVersion` `nss-classification-model-v5.3.0`, `ExtRecordId` `alice.csv`, `ClientId`
`5`. Data Fabric gave the times back with `+00:00`: the input `…T06:15:07.000Z` came back as
`2026-10-19T06:15:07+00:00` (the same instant, without the zero milliseconds), while `StartTime` kept its milliseconds
(`…T06:15:54.886+00:00`) (owner's tenant run, 2026-10-19). **`DwVariation` is a GUID**: your personal workspace's folder key, from `UIPATH_FOLDER_KEY`, because the
function job runs in the workspace, not in `Debug_<Flow>` (owner's tenant run, 2026-10-19; Q4). Empty would mean the
variable is not set inside a job.

```bash
uip df records query "$ALERT_ENTITY" --limit 100 --body "{\"filterGroup\": {\"logicalOperator\": 0, \"queryFilters\": [{\"fieldName\": \"TransactionUuid\", \"operator\": \"=\", \"value\": \"$UUID\"}]}}" --output json --output-filter "Items[].{alertId: AlertId, category: AlertCategory, type: AlertEntityType, gold: GoldDecision, autoQC: AutoQC, ticker: Ticker, clientId: ClientId}"
```

**Check:** one row: `A-1`, `Sanctions`, `INDIVIDUAL`, gold `1`, `AutoQC` false, `Ticker` false, `ClientId` `5`.

```bash
uip df records query "$HIT_ENTITY" --limit 100 --body "{\"filterGroup\": {\"logicalOperator\": 0, \"queryFilters\": [{\"fieldName\": \"TransactionUuid\", \"operator\": \"=\", \"value\": \"$UUID\"}]}}" --output json --output-filter "Items[].{wleId: WleId, type: WleEntityType, gold: GoldDecision}"
```

**Check:** two rows, `H-1` `INDIVIDUAL` gold `1`, and `H-2` `LOCATION` gold `0`.

**Optional rerun:** debug again with the same file. The counts stay 1 / 1 / 2 (the transaction is overwritten, the
alert and hits are not duplicated: D-7). This is the first run of the SDK's `update_record` on your tenant.

### A4. Reset before stage B

Stage B's counts assume empty entities. Delete every row of the three (each command lists the ids, then deletes them):

```bash
for E in "$TXN_ENTITY" "$ALERT_ENTITY" "$HIT_ENTITY"; do uip df records query "$E" --limit 100 --output json --output-filter "Items[].Id" | jq -r '.Data[].Id' | xargs uip df records delete "$E" --yes --reason "EvMig stage reset"; done
```

(`--output-filter` turns a list of plain values into objects named after the last field, here `[{"Id": …}]`, hence
`.Data[].Id`.)

**Check:** `uip df records query "$TXN_ENTITY" --limit 100 --output plain --output-filter "length(Items)"` (and the
same for the other two) prints 0. (`records delete` takes several ids in one call: it deleted 1, 1 and 2 rows here,
owner's tenant run, 2026-10-19.)

### B0. Set the variables again

Stage B uses Stage A's shell variables and runs in the same `EvMigEvelyn` folder (B2 reads `../data`). In the terminal
of Stage A, skip this. In a new one:

```bash
cd /tmp/evmig-copy/EvMigEvelyn
```

(or the `EvMigEvelyn` folder you used in Stage A)

```bash
TXN_ENTITY=$(uip df entities list --native-only --output plain --output-filter "[?Name=='EvMigTransaction'].Id | [0]")
```

```bash
ALERT_ENTITY=$(uip df entities list --native-only --output plain --output-filter "[?Name=='EvMigAlertAnalytics'].Id | [0]")
```

```bash
HIT_ENTITY=$(uip df entities list --native-only --output plain --output-filter "[?Name=='EvMigHitAnalytics'].Id | [0]")
```

```bash
WORKSPACE=$(uip or folders list --limit 100 --output plain --output-filter "[?Type=='Personal'].Path | [0]")
```

```bash
DEBUG_FOLDER="$WORKSPACE/Debug_EvMigCsvFileIngestionFlow"
```

**Check:** `ls EvMigEvelyn.uipx` finds the file, and `echo "$TXN_ENTITY $ALERT_ENTITY $HIT_ENTITY | $DEBUG_FOLDER"`
prints three GUIDs and `<your email>'s workspace/Debug_EvMigCsvFileIngestionFlow`.

### B1. First debug of the CSV flow: it creates the bucket, and fails

The bucket is a Solution resource: the first debug run creates it, empty, in
`<your email>'s workspace/Debug_EvMigCsvFileIngestionFlow`. Don't create it by hand.

```bash
uip solution resources refresh
```

```bash
uip maestro flow debug EvMigCsvFileIngestionFlow --output json > /tmp/evmig-debug-b1.json
```

**Check:** `jq '.Data.finalStatus' /tmp/evmig-debug-b1.json` is `"Faulted"`, at `csvMonitorTask1`, because the
configuration file is not there yet. The step's text sits inside the node's error detail:

```bash
jq -r '.Data.variables.elements[] | select(.elementId == "csvMonitorTask1") | .outputs.Error.detail' /tmp/evmig-debug-b1.json | grep -o 'Exception was thrown by Evelyn NSS step csv-monitor-task: Please provide correct path to file: config/configuration_payload.json'
```

**Check:** it prints that text once. If it prints nothing, read the whole detail (the command without `| grep …`). If the
detail says "Bucket with name 'EvMigFiles' not found" instead, the monitor's job (which runs in your workspace, A2)
did not reach the bucket in `Debug_EvMigCsvFileIngestionFlow`: the SDK sends a bucket call to another folder only
when the run gives it the Solution's resource override for that bucket (**Inference** from the SDK's
`resource_override`, `uipath/platform/common/_bindings.py:218`; not seen yet).

### B2. Upload the mock files

```bash
BUCKET_KEY=$(uip or buckets list --folder-path "$DEBUG_FOLDER" --limit 100 --output plain --output-filter "[?Name=='EvMigFiles'].Key | [0]")
```

**Check:** `echo "$DEBUG_FOLDER | $BUCKET_KEY"` prints `<your email>'s workspace/Debug_EvMigCsvFileIngestionFlow | <GUID>`.

The key of each file is its path under `data/` (do not upload `data/README.md`):

```bash
uip or bucket-files upload "$BUCKET_KEY" config/configuration_payload.json --folder-path "$DEBUG_FOLDER" --file ../data/config/configuration_payload.json --content-type application/json
```

```bash
uip or bucket-files upload "$BUCKET_KEY" doc-upload/name_sanctions_screening/csv/nss_input_format.csv --folder-path "$DEBUG_FOLDER" --file ../data/doc-upload/name_sanctions_screening/csv/nss_input_format.csv --content-type text/csv
```

```bash
uip or bucket-files upload "$BUCKET_KEY" doc-upload/name_sanctions_screening/csv/data/screening_batch_1.csv --folder-path "$DEBUG_FOLDER" --file ../data/doc-upload/name_sanctions_screening/csv/data/screening_batch_1.csv --content-type text/csv
```

```bash
uip or bucket-files upload "$BUCKET_KEY" doc-upload/name_sanctions_screening/csv/data/batch/screening_batch_2.csv --folder-path "$DEBUG_FOLDER" --file ../data/doc-upload/name_sanctions_screening/csv/data/batch/screening_batch_2.csv --content-type text/csv
```

```bash
uip or bucket-files upload "$BUCKET_KEY" doc-upload/name_sanctions_screening/csv/data/header_only.csv --folder-path "$DEBUG_FOLDER" --file ../data/doc-upload/name_sanctions_screening/csv/data/header_only.csv --content-type text/csv
```

```bash
uip or bucket-files upload "$BUCKET_KEY" doc-upload/name_sanctions_screening/csv/data/notes.txt --folder-path "$DEBUG_FOLDER" --file ../data/doc-upload/name_sanctions_screening/csv/data/notes.txt --content-type text/plain
```

**Check:**

```bash
uip or bucket-files list "$BUCKET_KEY" --folder-path "$DEBUG_FOLDER" --prefix doc-upload/name_sanctions_screening/csv/data --output json --output-filter "Items[].FullPath"
```

shows the four files under `csv/data` (three `.csv` and `notes.txt`), the nested `batch/screening_batch_2.csv`
included. That is the listing the monitor relies on, without a trailing `/`.

### B3. Debug the CSV flow

```bash
uip maestro flow debug EvMigCsvFileIngestionFlow --output json > /tmp/evmig-debug-b3.json
```

Four function jobs run one after another (the monitor, then `csv-task` three times): expect a few minutes. The CSV
flow does not wait for the three main-flow runs it starts.

**Check:** `jq '.Data.finalStatus' /tmp/evmig-debug-b3.json` is `"Completed"`, and no node has an error:

```bash
jq -r '.Data.variables.elements[] | select(.outputs.Error) | "\(.elementId) \(.outputs.Error.detail)"' /tmp/evmig-debug-b3.json
```

prints nothing.

### B4. Check the three main-flow runs and the rows

Wait for the three child runs to write their transactions. (The producer jobs run in your workspace and `jobs list`
shows no process name for them, A2, so count the rows instead; A4 or B5 left the entities empty.) Each poll is one Data
Fabric call:

```bash
for i in $(seq 30); do N=$(uip df records query "$TXN_ENTITY" --limit 100 --output plain --output-filter "length(Items)"); echo "$N"; [ "$N" = "3" ] && break; sleep 10; done
```

**Check:** it reaches `3` within the 5 minutes. Fewer means a child was lost or failed: Community runs 3 jobs at once,
and what happens past that is undocumented.

```bash
for E in "$TXN_ENTITY" "$ALERT_ENTITY" "$HIT_ENTITY"; do uip df records query "$E" --limit 100 --output plain --output-filter "length(Items)"; done
```

**Check:** 3, 3 and 5.

```bash
uip df records query "$TXN_ENTITY" --limit 100 --output json --output-filter "Items[].{ext: ExtRecordId, clientId: ClientId, startBpUuid: StartBpUuid, bpStartTime: BpStartTime, dwVariation: DwVariation, status: Status}"
```

**Check:** `screening_batch_1.csv` twice (`ClientId` 7) and `screening_batch_2.csv` once (`ClientId` 1), all `NEW`,
one shared `BpStartTime`, and **one shared `StartBpUuid`**, which is what `$metadata.InstanceId` held in the CSV flow.
Compare it with the two ids of the B3 run:

```bash
jq -r '.Data | "instanceId \(.instanceId)", "runId      \(.runId)"' /tmp/evmig-debug-b3.json
```

**Check:** `StartBpUuid` equals one of them. Note which: D-2 assumes the instance id. An empty `StartBpUuid` cannot
happen: the producer refuses it, and the three child runs would show incidents instead (then see "When a run fails").

The child runs are their own instances. To list them you need the debug folder's key (matched by the end of its path:
the apostrophe in `<your email>'s workspace` would end a quoted path inside the filter):

```bash
DEBUG_FOLDER_KEY=$(uip or folders list --limit 100 --output plain --output-filter "[?ends_with(Path,'Debug_EvMigCsvFileIngestionFlow')].Key | [0]")
```

```bash
uip maestro flow instance list --folder-key "$DEBUG_FOLDER_KEY" --limit 20 --output json
```

**Check:** one `EvMigCsvFileIngestionFlow` instance and three `EvMigNamesScreeningFlow` instances. If it lists none,
the instances may sit in your workspace, as the function jobs do (**Inference**): run it again with `--folder-key` set
to the workspace's key, which is A3's `DwVariation`. (The field names of
this list are not recorded anywhere yet; read them off the output.)

### B5. Reset between runs

Every `csv-task` run mints new uuids, so a second B3 adds three more transactions. To start clean, repeat A4. The
bucket files and the debug folders can stay.

### C. Clean up the tenant

When you are done with both stages, remove what they made. Every step is irreversible. Nobody has run these yet;
the commands come from `uip … --help`. Run them from `EvMigEvelyn` with B0's variables set.

**C1. The three entities** (their rows go with them):

```bash
for E in "$TXN_ENTITY" "$ALERT_ENTITY" "$HIT_ENTITY"; do uip df entities delete "$E" --yes --reason "EvMig clean-up"; done
```

**Check:** the list command of A1 prints nothing.

**C2. The Studio Web solution** that `flow debug` uploaded. Each debug output names it:

```bash
jq -r '.Data.solutionId' /tmp/evmig-debug-*.json | sort -u
```

```bash
uip solution delete <solution id> --yes
```

Run the delete once per id printed. **Check:** each prints the `SolutionId` it deleted.

**C3. The bucket, then the two debug folders.** List the buckets of both folders:

```bash
for F in Debug_EvMigNamesScreeningFlow Debug_EvMigCsvFileIngestionFlow; do echo "$F"; uip or buckets list --folder-path "$WORKSPACE/$F" --limit 100 --output plain --output-filter "[].[Name, Key]"; done
```

Delete each bucket it prints. `--force` because `EvMigFiles` still holds the mock files, which go with it:

```bash
uip or buckets delete <bucket key> --folder-path "$WORKSPACE/<folder>" --force
```

```bash
uip or folders delete "$WORKSPACE/Debug_EvMigNamesScreeningFlow" --yes
```

```bash
uip or folders delete "$WORKSPACE/Debug_EvMigCsvFileIngestionFlow" --yes
```

**Check:** each prints `Deleted successfully`. `folders delete` refuses a folder that still holds anything; if it
does, delete the folder in Orchestrator → **My Workspace** instead, or leave it.

**C4. Locally**, `EvMigEvelyn.uipx` and `resources/` carry your `SolutionId` and the fields `resources refresh`
added. If you ran level 4 in `/tmp/evmig-copy`, delete that copy; the repo itself is untouched.

### Where to look in the browser

| To see | Where |
|---|---|
| One run, node by node, with Incidents | `jq -r '.Data.studioWebUrl' /tmp/evmig-debug-b3.json`: the canvas in Debug mode |
| The three child runs | Maestro → **Flow instances**: each child is its own instance |
| The bucket and its files | Orchestrator → **My Workspace** → `Debug_EvMigCsvFileIngestionFlow` → **Storage Buckets** → `EvMigFiles` (buckets don't show while **Tenant** is selected) |
| Function jobs and their logs | Orchestrator → **My Workspace** → **Automations** → **Jobs** (a debug run's function jobs run in your workspace, not in `Debug_<Flow>`), or `uip or jobs logs <job key>` with the key found as in A2 |
| The rows | Data Fabric → **Entities** → `EvMigTransaction`, `EvMigAlertAnalytics`, `EvMigHitAnalytics` |

### Things only the tenant run can confirm

| Question | Where you see the answer |
|---|---|
| Does `fireAndForget: true` start one child run per record? (Q1; never run anywhere before) | B4: three transactions and three child instances |
| Does `$metadata.InstanceId` hold the CSV flow's id, and which one? | B4: `StartBpUuid` equals the B3 run's `instanceId` or its `runId` |
| Does `ListFiles` with a prefix without a trailing `/` return nested keys? | B2's check, then B3 (the monitor lists 3 files) |
| Do the object and array inputs survive the Flow-to-Flow call? | B4: rows with the right ids and hit counts |
| Is a `csv-task` failure contained by its error port (the CSV flow goes on)? | Upload a broken file under `csv/data/` and debug: the run completes, the node shows the error (D-12) |
| Is a call that fails to start contained by the "NSS-main-BP" error port? | Only seen if it happens: the run completes and `nssMainBp1` shows an error (D-18) |
| What happens past 3 concurrent jobs? | B4 with more records (not in the mock data) |

Answered by Stage A, so no longer in the table (owner's tenant run, 2026-10-19): the three entities were created with these field names;
Data Fabric works from a debug run's job; the vendored wheel installs with its dependencies from `uv.lock`;
`UIPATH_FOLDER_KEY` is set in a job (your workspace's key); `DATETIME_WITH_TZ` takes UTC text ending in `Z`;
`BOOLEAN` takes the booleans; `update_record` overwrites the transaction in place (the rerun gave 1 / 1 / 2 rows);
`records delete` takes several ids in one call.

### When a run fails

| Symptom | Cause, and what to do |
|---|---|
| `Not logged in` | `uip login` |
| A1: "Field name for '<name>' is a reserved SQL word and cannot be used as an entity or field name." | The server refuses names the CLI lets through, one per attempt, and nothing is created. Rename the field in `docs/mapping.md` §8, add the name to `REFUSED_BY_TENANT` in `scripts/entities.py` and to `REFUSED_FIELD_NAMES` in `evmig-nss/src/evmig_nss/testing.py`, rename it in the row models, then `python3 -I scripts/entities.py --write`, bump the library and `scripts/vendor_wheel.sh` (as for `Uuid`, D-5) |
| A function node `Faulted` with "Exception was thrown by Evelyn NSS step …" | The text after the colon is Evelyn's message. `jq` the element's `.outputs.Error.detail`; the job log has the traceback (`uip or jobs logs <key> --level Error`, the key found as in A2 with the `instanceId` of the run whose node failed) |
| `Hash mismatch for evmig-nss` in a job log | The wheel in `wheels/` and `uv.lock` disagree: rerun `scripts/vendor_wheel.sh` (bump the library's version first) |
| A Data Fabric 401 or 403 | The job's identity has no role. Your runs of 2026-10-16 and 2026-10-19 needed none; if it happens, Data Fabric → Manage Access → Data Writer for the robot of your workspace, where the jobs run |
| "Value uniqueness violation … 2627" | A second insert of the same `TransactionUuid` (or `AlertUuid`, `HitUuid`); the producer treats a lost race as "already exist", other cases are bugs |
| No child runs in B4 | Look at `nssMainBp1`'s error in `/tmp/evmig-debug-b3.json` (its error port is armed, so a failed start does not stop the run, D-18). If there is none, `fireAndForget: true` did not start them (Q1). Fallback 1 (DEC-4): set `"fireAndForget": false` in `scripts/build_flows.sh`, rebuild the Flows (README → Rebuild), and debug again. Its risk: the CSV flow waits for each child, and a faulted child may never release it |
| `StartBpUuid` empty or the producer says "bp_run_id is empty" | `$metadata.InstanceId` was empty: the fallback is a UUID made by `csv-monitor-task` (DEC-5, out-of-scope item 12) |
| The parent stays `Running` after a node fault | Known behaviour of a waiting Flow call (`learning/KT/coded-functions.md`); with `fireAndForget: true` it should not happen. Stop the instance in Maestro |
