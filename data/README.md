# data/: the bucket mirror

The folder mirrors the Orchestrator bucket `EvMigFiles`: a file's path here is its key there. A local run points
`EVMIG_LOCAL_BUCKET_DIR` at this folder; the tenant run uploads the same files. Placeholder names only (Alice Wonderland,
John Doe, Gill Bates and spellings of them). Each file is written so that a wrong port gives a different answer;
`EvMigEvelyn/EvMigCsvTask/tests/test_data_files.py` pins the answers.

| File (key in the bucket) | What it is |
|---|---|
| `config/configuration_payload.json` | The five keys the three functions read, nested like Evelyn's payload: both file locations, `proceed_with_error_data` true, `keep_input_file_name_for_qc_report` true, `location_wle_enable` false |
| `doc-upload/name_sanctions_screening/csv/nss_input_format.csv` | The format file: NSS column, then the client's column name. Spaces, quotes and capitals are on purpose (both columns are lower-cased and trimmed); the rows with an empty client column are ignored |
| `.../csv/data/screening_batch_1.csv` | A data file at depth 0. Two alerts survive (`A-100`, `A-200`) |
| `.../csv/data/batch/screening_batch_2.csv` | A data file one folder deeper, with a UTF-8 BOM. One alert survives |
| `.../csv/data/header_only.csv` | A header and no rows: `csv-task` answers with the stop row |
| `.../csv/data/notes.txt` | Not a `.csv`: the monitor must not list it |

The monitor lists three data files (`batch/screening_batch_2.csv`, `header_only.csv`, `screening_batch_1.csv`, in that
order). The format file is outside the data folder, so it is not listed. Three alerts survive in all, at most two per file
(the first tenant run uses at most 3 records).

## `screening_batch_1.csv`

Header: ` Alert Id ,CLIENT, Customer Name ,...` (odd case and spaces). It has a `CLIENT` column, so `client_id` is `7`.
Row numbers count the data rows; the blank line is row 4.

| Row | What it exercises |
|---|---|
| 1 `A-100` | The first row of an alert builds it. `06/10/1991` is read month-first: 10 June (month `06`, day `10`) |
| 2 `A-200` | A second alert, so that alert 1's rows are not adjacent. `03/04/1985` is 4 March |
| 3 `A-100`, hit `H-2` | A row of alert 1 that is not next to its first row: its hit joins alert 1 |
| 4 (blank line) | A blank line is a record with no values: an input-name error and a hit-name error, on line 4 |
| 5 `A-200`, hit `H-9` | The same hit id as row 2: both hits are kept, with their own uuids |
| 6 `A-100`, hit `H-3` of type `LOCATION` | Dropped silently while `location_wle_enable` is false (no error); kept when it is true |
| 7 `A-200`, hit `H-10` | A later invalid hit (no hit name): the hit is dropped, the alert stays; the error is on line 7 |

Expected: `A-100` with hits `H-1`, `H-2`; `A-200` with hits `H-9`, `H-9`; ERROR log "Parsing completed. 2 out of 3 alerts will
proceed to NSS main Business Process."; `request_id` `screening_batch_1.csv`.

## `batch/screening_batch_2.csv`

Starts with a BOM (if it were kept, the first header would not be `alert id`). No `CLIENT` column, so `client_id` is the
default `1`.

| Row | What it exercises |
|---|---|
| 1 `B-300` | The first row of an alert is invalid (no customer name): the alert is dropped, and so is every later row with its id |
| 2 (blank `Alert Id`) | A blank input id: the row is its own alert, with a generated id. `12/25/1990` fails if read day-first |
| 3 `B-300` | A valid row of the dropped alert: skipped |

Expected: one alert (generated id, hit `H-5`); ERROR log "Parsing completed. 1 out of 2 alerts will proceed...";
`request_id` `screening_batch_2.csv`.
