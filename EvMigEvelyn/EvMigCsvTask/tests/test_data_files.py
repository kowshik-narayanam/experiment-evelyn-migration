"""The mock data in REPO/data/ (DEC-10): the bucket mirror that local runs and the tenant upload use.

Each file was written so that a wrong port gives a different answer; data/README.md says which row is for what. These tests
run main() on the real files through the library's local SDK (the same path as `uipath run` with EVMIG_LOCAL_BUCKET_DIR) and
pin the answers, plus the size guard of DEC-10 and Q8: a job output above ~10 KB may be dropped silently on the tenant, so
every output stays under 8,000 characters.
"""
import json
import logging
import re
from types import SimpleNamespace

import pytest
from evmig_nss.core.bucket_store import BucketStore
from evmig_nss.core.configuration import (
    DATA_FILE_LOCATION_PATH,
    ENABLE_LOCATION_WLE_PATH,
    FORMAT_FILE_LOCATION_PATH,
    KEEP_INPUT_FILE_NAME_FOR_QC_REPORT_PATH,
    PROCEED_WITH_ERROR_DATA_PATH,
    load_configuration,
)
from evmig_nss.core.sdk import get_sdk, set_sdk
from evmig_nss.core.configuration import CONFIG_FILE_KEY
from evmig_nss.testing import FakeBuckets, FakeEntities, local_sdk

from helpers import DATA_DIR, configuration_document
from main import CsvTaskInput, main

BASE = "doc-upload/name_sanctions_screening/csv/"
FORMAT = BASE + "nss_input_format.csv"
FILE_1 = BASE + "data/screening_batch_1.csv"
FILE_2 = BASE + "data/batch/screening_batch_2.csv"
FILE_3 = BASE + "data/header_only.csv"
OUTPUT_LIMIT = 8_000


@pytest.fixture(autouse=True)
def local_bucket():
    set_sdk(local_sdk(DATA_DIR))  # a folder as the bucket, the in-memory Data Fabric (unused by csv-task)


def use_configuration(**options) -> None:
    """The data folder's files in an in-memory bucket, with a different configuration file (the folder-backed bucket's is fixed)."""
    files = {path.relative_to(DATA_DIR).as_posix(): path.read_bytes() for path in DATA_DIR.rglob("*") if path.is_file()}
    document = configuration_document(**options)
    document["provider"] = {"FORMAT_FILE_LOCATION": FORMAT, "CSV_DATA_FILE_LOCATION": BASE + "data/"}
    files[CONFIG_FILE_KEY] = json.dumps(document).encode()
    set_sdk(SimpleNamespace(buckets=FakeBuckets(files), entities=FakeEntities()))


def run(data_file: str):
    return main(CsvTaskInput(format_file_location=FORMAT, data_file_location=data_file))


def data_files() -> list[str]:
    """The data files the monitor would list: the data folder of the configuration, every .csv at any depth."""
    store = BucketStore(local_sdk(DATA_DIR).buckets)
    return store.get_csv_files_list(load_configuration(store).get_required_property(DATA_FILE_LOCATION_PATH))


# ---- the layout ----


def test_the_configuration_file_holds_the_five_keys_in_the_shapes_the_loader_reads():
    configuration = load_configuration(BucketStore(get_sdk().buckets))

    assert configuration.get_required_property(FORMAT_FILE_LOCATION_PATH) == FORMAT
    assert configuration.get_required_property(DATA_FILE_LOCATION_PATH) == BASE + "data/"
    assert configuration.get_required_boolean(PROCEED_WITH_ERROR_DATA_PATH) is True
    assert configuration.get_required_boolean(KEEP_INPUT_FILE_NAME_FOR_QC_REPORT_PATH) is True
    assert configuration.get_required_boolean(ENABLE_LOCATION_WLE_PATH) is False


def test_the_data_folder_has_two_csv_files_at_different_depths_and_a_header_only_one_and_a_txt_that_is_ignored():
    files = data_files()

    assert files == [FILE_2, FILE_3, FILE_1]  # sorted by key; notes.txt is not listed
    assert len({file.count("/") for file in files}) == 2  # two depths
    assert (DATA_DIR / BASE / "data" / "notes.txt").exists()


def test_the_data_file_with_a_bom_has_one():
    assert (DATA_DIR / FILE_2).read_bytes().startswith(b"\xef\xbb\xbf")


def test_the_first_tenant_run_gets_at_most_two_alerts_per_file_and_three_in_all():
    rows = {file: run(file).rows for file in data_files()}

    alerts = {file: [row for row in file_rows if row.stop is None] for file, file_rows in rows.items()}
    assert all(len(file_alerts) <= 2 for file_alerts in alerts.values())
    assert sum(len(file_alerts) for file_alerts in alerts.values()) == 3  # DEC-4: the first tenant run uses at most 3 records


# ---- the size guard (DEC-10, Q8) ----


@pytest.mark.parametrize("data_file", data_files())
def test_every_data_file_gives_an_output_under_8000_characters(data_file):
    output = run(data_file)

    assert len(json.dumps(output.model_dump())) < OUTPUT_LIMIT
    assert len(output.model_dump_json()) < OUTPUT_LIMIT


# ---- what each file is for ----


def test_file_1_keeps_two_alerts_with_their_hits_and_drops_what_the_rows_are_there_to_drop(caplog):
    caplog.set_level(logging.INFO)

    output = run(FILE_1)

    assert [(row.screened_data.id, [wle.id for wle in row.wle_list]) for row in output.rows] == [
        ("A-100", ["H-1", "H-2"]),  # H-2 is on a row that is not next to the others; H-3 (LOCATION) is dropped, with no error
        ("A-200", ["H-9", "H-9"]),  # two hits with one id are both kept; H-10 (no hit name) is dropped
    ]
    assert {row.request_id for row in output.rows} == {"screening_batch_1.csv"}  # keep_input_file_name_for_qc_report is true
    messages = [(r.levelno, r.getMessage()) for r in caplog.records]
    assert (logging.ERROR, "Parsing completed. 2 out of 3 alerts will proceed to NSS main Business Process.") in messages
    assert (logging.INFO, "Wle H-3 of type Location ignored as Location Wle matching is disabled.") in messages
    details = [r.exc_info[1] for r in caplog.records if r.levelno == logging.ERROR]
    assert len(details) == 1
    assert "Name parsing error in column (missing hit names) on line(s): 4,7" in str(details[0])  # line 4 is the blank line
    assert "Name parsing error in column (missing input names) on line(s): 4" in str(details[0])


def test_file_1_dates_are_read_month_first_and_the_client_id_comes_from_the_client_column():
    alice, john = (row.screened_data for row in run(FILE_1).rows)

    # 06/10/1991 is 10 June, 03/04/1985 is 4 March (a day-first reading would give month 10 and month 04)
    assert alice.dates[0].original.model_dump() == {"type": "DOB", "full": "06/10/1991", "year": "1991", "month": "06", "day": "10"}
    assert john.dates[0].original.model_dump() == {"type": "DOB", "full": "03/04/1985", "year": "1985", "month": "03", "day": "04"}
    assert (alice.clientId, john.clientId) == ("7", "7")
    assert [a.fullName for a in alice.aliases] == ["Ally Wonder"]
    assert alice.name.fullName == "Alice Wonderland"
    assert alice.category == "high" and alice.entityType == "INDIVIDUAL"
    assert alice.locations[0].original.country == "UK"


def test_file_1_hits_carry_their_own_fields():
    output = run(FILE_1)

    h1, h2 = output.rows[0].wle_list
    assert (h1.name.fullName, h2.name.fullName) == ("Alice Wonderland-Smith", "Alicia Wonderland")
    assert (h1.category, h1.entityType) == ("sanctions", "INDIVIDUAL")
    assert [wle.name.fullName for wle in output.rows[1].wle_list] == ["Jon Doe", "Johnny Doe"]
    assert len({wle.uuid for row in output.rows for wle in row.wle_list}) == 4  # even the two H-9 hits have their own uuid


def test_file_2_has_a_bom_no_client_column_a_blank_id_and_an_alert_whose_first_row_is_invalid(caplog):
    caplog.set_level(logging.INFO)

    output = run(FILE_2)

    assert len(output.rows) == 1  # B-300's first row has no name, so its two other rows are dropped; the blank-id row is its own alert
    alert = output.rows[0]
    assert re.fullmatch("[0-9a-f-]{36}", alert.screened_data.id)  # a blank input_id is replaced by a random id
    assert alert.screened_data.clientId == "1"  # no client column: the default
    assert alert.screened_data.name.fullName == "Gill Bates"
    assert alert.screened_data.dates[0].original.model_dump() == {
        "type": "DOB", "full": "12/25/1990", "year": "1990", "month": "12", "day": "25",  # fails day-first: there is no month 25
    }
    assert [wle.id for wle in alert.wle_list] == ["H-5"]  # H-4 is on the invalid first row, H-6 on a row of the dropped alert
    assert alert.request_id == "screening_batch_2.csv"
    error = next(r for r in caplog.records if r.levelno == logging.ERROR)
    assert error.getMessage() == "Parsing completed. 1 out of 2 alerts will proceed to NSS main Business Process."
    assert "Name parsing error in column (missing input names) on line(s): 1" in str(error.exc_info[1])


def test_file_3_has_a_header_and_no_rows_so_it_gives_the_stop_row(caplog):
    caplog.set_level(logging.INFO)

    output = run(FILE_3)

    assert output.model_dump() == {"rows": [{"screened_data": None, "wle_list": None, "request_id": None, "stop": "true"}]}
    assert "Parsing completed. 0 out of 0 alerts will proceed to NSS main Business Process." in [r.getMessage() for r in caplog.records]


def test_with_proceed_with_error_data_off_the_files_with_errors_are_dropped():
    # Both data files carry errors on purpose; with the flag off, Evelyn stops the whole file (CsvDataService.java:196).
    use_configuration(proceed_with_error_data=False, keep_input_file_name=True)

    assert [row.stop for row in run(FILE_1).rows] == ["true"]
    assert [row.stop for row in run(FILE_2).rows] == ["true"]


def test_with_location_hits_on_the_location_hit_of_file_1_is_kept():
    use_configuration(location_wle_enable=True, keep_input_file_name=True)

    output = run(FILE_1)

    # H-3 has a country (the Hit Country column) so it is a usable location hit: A-100 now has three hits
    assert [wle.id for wle in output.rows[0].wle_list] == ["H-1", "H-2", "H-3"]
