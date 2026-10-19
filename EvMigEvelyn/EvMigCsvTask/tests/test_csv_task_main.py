"""Ports CsvTaskProcessorIT (9 methods; JT = names-screening-jnw/src/test/java/com/workfusion/dw/nss) and checks main()'s own rules.

JT:task/csv/it/CsvTaskProcessorIT.java runs the processor in a launcher with an S3 mock. Here main() runs on a fake bucket
(`run_csv_task` puts the files in it as `test-bucket/data/...`, the paths the IT uses). The Java asserts on the task's
output rows: `hasSize(n)` is `len(rows)`.
"""
import json
import logging
import re

import pytest
from evmig_nss.core.errors import NSSProcessingException
from evmig_nss.schema.models import ScreenedData, WleData
from pydantic import ValidationError

import csv_samples as samples
from csv_data_service import CsvDataService
from helpers import install_bucket, replace_configuration, run_csv_task
from main import CsvTaskInput, main

STEP = "Exception was thrown by Evelyn NSS step csv-task: "
FORMAT = "test-bucket/data/format-data.csv"
DATA = "test-bucket/data/input-data.csv"


# ---- CsvTaskProcessorIT ----


def test_run():  # ports CsvTaskProcessorIT.java:81
    actual = run_csv_task(samples.NSS_FULL_FORMAT, samples.INPUT_DATA_1_INPUT_ID_3_HITS)

    assert len(actual.rows) == 3
    first_record = next(row for row in actual.rows if row.screened_data.id == "1")

    # keep_input_file_name_for_qc_report is false in the IT's default configuration: a random UUID
    assert re.fullmatch("[0-9a-f-]{36}", first_record.request_id)

    screened_data = first_record.screened_data
    assert screened_data.id
    assert screened_data.category
    assert screened_data.entityType is not None
    assert screened_data.gender is not None
    assert screened_data.name is not None
    assert len(screened_data.dates) == 1
    assert len(screened_data.locations) == 1
    assert screened_data.locations[0].original.street
    assert len(screened_data.aliases) == 2
    assert screened_data.additionalData
    assert screened_data.goldDecision
    assert screened_data.identifiers

    wle = next(wle for wle in first_record.wle_list if wle.id == "1")
    assert len(wle.locations) == 1
    assert wle.locations[0].original.street
    assert len(wle.aliases) == 3
    assert len(wle.dates) == 1
    assert wle.id
    assert wle.name is not None
    assert wle.gender is not None
    assert wle.goldDecision
    assert wle.category
    assert wle.entityType is not None
    assert wle.additionalData
    assert wle.identifiers

    # "make sure address is parsed correctly": the last alert has a city and no street
    last_record = next(row for row in actual.rows if row.screened_data.id == "3")
    assert len(last_record.screened_data.locations) == 1
    assert not last_record.screened_data.locations[0].original.street
    wle_last = next(wle for wle in last_record.wle_list if wle.id == "4")
    assert len(wle_last.locations) == 1
    assert not wle_last.locations[0].original.street


def test_run_alerts_come_with_their_own_hits_and_one_request_id_per_file():
    # Not in the Java test: which hits belong to which alert, and the shared request id (mapping claim 8).
    actual = run_csv_task(samples.NSS_FULL_FORMAT, samples.INPUT_DATA_1_INPUT_ID_3_HITS)

    assert [(row.screened_data.id, [wle.id for wle in row.wle_list]) for row in actual.rows] == [
        ("1", ["1", "2"]),
        ("2", ["3"]),
        ("3", ["4"]),
    ]
    assert len({row.request_id for row in actual.rows}) == 1


def test_shouldAddHitIdIfMissing():  # ports CsvTaskProcessorIT.java:201
    actual = run_csv_task(samples.NSS_INPUT_FORMAT, samples.INPUT_DATA_NO_HIT_ID)

    assert len(actual.rows) == 1
    wle_list = actual.rows[0].wle_list
    assert wle_list[0].id and wle_list[0].id.strip()  # a generated id: the file has no hit_id column
    assert wle_list[0].goldDecision == "1"


def test_shouldSkipErrorRecords():  # ports CsvTaskProcessorIT.java:234
    actual = run_csv_task(samples.NSS_FULL_FORMAT, samples.INPUT_DATA_INVALID_DATE_AND_RECORD_TYPE)

    assert len(actual.rows) == 5


def test_shouldRemoveBOMEncodingFromCsvFile():  # ports CsvTaskProcessorIT.java:258
    actual = run_csv_task(samples.FORMAT_FILE_WITH_BOM_ENCODING, samples.DATA_FILE_WITH_BOM_ENCODING)

    assert len(actual.rows) == 1
    assert actual.rows[0].stop is None  # an alert, not the stop row


@pytest.mark.parametrize("is_location_wle_enabled", [True, False])
def test_runWithLocationWles(is_location_wle_enabled):  # ports CsvTaskProcessorIT.java:281
    actual = run_csv_task(
        samples.NSS_FULL_FORMAT, samples.INPUT_DATA_1_INPUT_ID_4_HITS_LOCATION, location_wle_enable=is_location_wle_enabled
    )

    assert len(actual.rows) == (4 if is_location_wle_enabled else 3)


def test_shouldUseInputFileNameAsRequestIdWhenFlagEnabled():  # ports CsvTaskProcessorIT.java:304
    actual = run_csv_task(samples.NSS_FULL_FORMAT, samples.INPUT_DATA_1_INPUT_ID_3_HITS, keep_input_file_name=True)

    assert actual.rows
    assert all(row.request_id == "input-data.csv" for row in actual.rows)


def test_runWithNoNameHits():  # ports CsvTaskProcessorIT.java:330
    actual = run_csv_task(samples.NSS_FULL_FORMAT, samples.INPUT_DATA_1_NO_NAME_HIT, location_wle_enable=True)

    assert len(actual.rows) == 1  # the one row is the stop row (see the next two tests)


def test_shouldReleaseStopSignalWhenAllRecordsHaveErrors_proceedWithCorrectRecordsOn():  # ports CsvTaskProcessorIT.java:353
    actual = run_csv_task(
        samples.NSS_FULL_FORMAT, samples.INPUT_DATA_1_NO_NAME_HIT, location_wle_enable=True, proceed_with_error_data=True
    )

    assert actual.rows[0].stop == "true"


def test_shouldReleaseStopSignalWhenAllRecordsHaveErrors_proceedWithCorrectRecordsOff():  # ports CsvTaskProcessorIT.java:381
    actual = run_csv_task(
        samples.NSS_FULL_FORMAT, samples.INPUT_DATA_1_NO_NAME_HIT, location_wle_enable=True, proceed_with_error_data=False
    )

    assert actual.rows[0].stop == "true"


# ---- the output shape (this port's choice: one row model for both shapes) ----


def test_the_stop_row_and_an_alert_row_dump_with_the_same_four_keys():
    stop = run_csv_task(samples.NSS_FULL_FORMAT, samples.ONLY_HEADERS_FILE).model_dump()
    alert = run_csv_task(samples.NSS_FULL_FORMAT, samples.INPUT_DATA_1_INPUT_ID_3_HITS).model_dump()

    assert stop == {"rows": [{"screened_data": None, "wle_list": None, "request_id": None, "stop": "true"}]}
    assert set(alert["rows"][0]) == {"screened_data", "wle_list", "request_id", "stop"}
    assert alert["rows"][0]["stop"] is None  # so `currentItem.stop !== "true"` lets an alert through
    assert isinstance(alert["rows"][0]["screened_data"], dict)  # objects, not JSON text (D-8)
    assert isinstance(alert["rows"][0]["wle_list"], list)


def test_the_output_is_plain_json_whichever_way_it_is_dumped():
    # The runtime calls model_dump() with no mode (uipath/functions/type_conversion.py:95); it must carry as JSON all the same.
    actual = run_csv_task(samples.NSS_FULL_FORMAT, samples.INPUT_DATA_1_INPUT_ID_3_HITS)

    assert json.loads(json.dumps(actual.model_dump())) == json.loads(actual.model_dump_json())


def test_an_alert_without_hits_is_not_sent_on(monkeypatch):
    # J:task/csv/CsvTaskProcessor.java:69 filters them. CsvDataService never produces one (an alert exists only because its
    # first row gave a hit), so it is staged: the service is made to return an alert with an empty hit list.
    monkeypatch.setattr(CsvDataService, "map_file_format", lambda self, location: {})
    monkeypatch.setattr(CsvDataService, "map_data_file", lambda self, *args: [(ScreenedData(id="a"), []), (ScreenedData(id="b"), [WleData(id="h")])])
    install_bucket({})

    actual = main(CsvTaskInput(format_file_location="b/f.csv", data_file_location="b/d.csv"))

    assert [row.screened_data.id for row in actual.rows] == ["b"]


# ---- the request id, the input, and the errors ----


@pytest.mark.parametrize(
    "data_file_location, expected",
    [
        ("test-bucket/data/input-data.csv", "input-data.csv"),
        ("test-bucket/data/deeper/folder/Other Name.csv", "Other Name.csv"),
        ("test-bucket/file.csv", "file.csv"),
    ],
)
def test_request_id_is_what_follows_the_last_slash(data_file_location, expected):  # J:task/csv/CsvTaskProcessor.java:57
    install_bucket(
        {"test-bucket/f.csv": samples.NSS_FULL_FORMAT, data_file_location: samples.INPUT_DATA_1_INPUT_ID_3_HITS}, keep_input_file_name=True
    )

    actual = main(CsvTaskInput(format_file_location="test-bucket/f.csv", data_file_location=data_file_location))

    assert {row.request_id for row in actual.rows} == {expected}


def test_input_ignores_unknown_fields_and_requires_both_locations():
    assert CsvTaskInput(format_file_location="a/b.csv", data_file_location="a/c.csv", iterator={"x": 1}).data_file_location == "a/c.csv"
    with pytest.raises(ValidationError):
        CsvTaskInput(format_file_location="a/b.csv", data_file_location=None)
    with pytest.raises(ValidationError):
        CsvTaskInput(data_file_location="a/c.csv")


def test_an_empty_location_fails_with_the_bucket_stores_text():
    install_bucket({})

    with pytest.raises(NSSProcessingException) as thrown:
        main(CsvTaskInput(format_file_location="", data_file_location=DATA))

    assert str(thrown.value) == STEP + "Missing bucket name: "


def test_a_path_without_a_bucket_segment_fails_with_evelyns_text():
    install_bucket({})

    with pytest.raises(NSSProcessingException) as thrown:
        main(CsvTaskInput(format_file_location="nss_input_format.csv", data_file_location=DATA))

    assert str(thrown.value) == STEP + "Missing bucket name: nss_input_format.csv"


def test_a_zero_byte_data_file_fails_with_evelyns_text():
    with pytest.raises(NSSProcessingException) as thrown:
        run_csv_task(samples.NSS_FULL_FORMAT, "")

    assert str(thrown.value) == STEP + "File test-bucket/data/input-data.csv is empty"
    assert isinstance(thrown.value.__cause__, ValueError)  # the original error stays attached for the job log


def test_a_zero_byte_format_file_fails_with_evelyns_text():
    with pytest.raises(NSSProcessingException) as thrown:
        run_csv_task("", samples.INPUT_DATA_1_INPUT_ID_3_HITS)

    assert str(thrown.value) == STEP + "File test-bucket/data/format-data.csv is empty"


def test_a_format_file_with_only_a_header_fails_as_empty():
    # The case CsvDataServiceTest.mapFileFormat_emptyFile reaches by reading a zero-byte file as no rows.
    with pytest.raises(NSSProcessingException) as thrown:
        run_csv_task("nss_column,client_column\n", samples.INPUT_DATA_1_INPUT_ID_3_HITS)

    assert str(thrown.value).startswith(STEP + "Errors found: [Format file is empty, ")


def test_a_bad_format_file_fails_the_step_with_the_format_errors():
    with pytest.raises(NSSProcessingException) as thrown:
        run_csv_task(samples.NSS_INCORRECT_FORMAT, samples.INPUT_DATA_1_INPUT_ID_3_HITS)

    assert str(thrown.value) == STEP + (
        "Errors found: [Format file should contain input_full_name mapping, "
        "Format file should contain input_id mapping, Format file should contain hit_matched_name mapping]"
    )


def test_a_client_column_twice_in_the_format_file_fails():
    # Collectors.toMap throws IllegalStateException("Duplicate key ..."), J:task/csv/service/CsvDataService.java:66
    format_text = "nss_column,client_column\ninput_id,id\ninput_alias_name,ID\ninput_full_name,name\nhit_matched_name,hit\n"

    with pytest.raises(NSSProcessingException) as thrown:
        run_csv_task(format_text, samples.INPUT_DATA_2_INPUT_ID_5_HITS)

    assert str(thrown.value) == STEP + "Duplicate key id (attempted merging values input_id and input_alias_name)"


@pytest.mark.parametrize(
    "format_text",
    [
        "nss_column,client_column\ninput_id\ninput_full_name,name\n",  # a row with one value
        "nss_column,client_column\ninput_id,id\n\ninput_full_name,name\nhit_matched_name,matched_name\n",  # a blank line
    ],
    ids=["one-value-row", "blank-line"],
)
def test_a_format_file_row_without_a_second_column_fails_like_java(format_text):
    # CSVRecord.get(1) on a row with one value: ArrayIndexOutOfBoundsException
    with pytest.raises(NSSProcessingException) as thrown:
        run_csv_task(format_text, samples.INPUT_DATA_2_INPUT_ID_5_HITS)

    assert str(thrown.value) == STEP + "Index 1 out of bounds for length 1"


def test_two_data_columns_for_one_nss_column_fail_with_javas_duplicate_key_text():
    # `name` and `Name` both lower-case to a client column the format file maps, so Collectors.toMap in formatRow fails.
    # The InputAttribute is printed as a Java record prints it, with the value as read (a quoted value keeps its spaces).
    data = 'id,name,Name,matched_name\n1,Alice Wonderland," Alice ",Alice Wonderland\n'
    format_text = "nss_column,client_column\ninput_id,id\ninput_full_name,name\nhit_matched_name,matched_name\n"

    with pytest.raises(NSSProcessingException) as thrown:
        run_csv_task(format_text, data)

    assert str(thrown.value) == STEP + (
        "Duplicate key input_full_name (attempted merging values "
        "InputAttribute[value=Alice Wonderland, clientColumn=name] and InputAttribute[value= Alice , clientColumn=name])"
    )


def test_a_missing_configuration_key_fails_in_javas_order():
    # CsvDataService.java:75-76 reads location_wle_enable, then proceed_with_error_data, before the data file is read;
    # CsvTaskProcessor.java:56 reads keep_input_file_name_for_qc_report after the file was parsed.
    install_bucket({FORMAT: samples.NSS_FULL_FORMAT, DATA: samples.INPUT_DATA_1_INPUT_ID_3_HITS})
    run = lambda: main(CsvTaskInput(format_file_location=FORMAT, data_file_location=DATA))  # noqa: E731

    replace_configuration({})
    with pytest.raises(NSSProcessingException) as thrown:
        run()
    assert str(thrown.value) == STEP + "Configuration does not contain property 'model.thresholds.location_wle_enable'"

    replace_configuration({"model": {"thresholds": {"location_wle_enable": False}}})
    with pytest.raises(NSSProcessingException) as thrown:
        run()
    assert str(thrown.value) == STEP + "Configuration does not contain property 'configuration.proceed_with_error_data'"

    replace_configuration({"model": {"thresholds": {"location_wle_enable": False}}, "configuration": {"proceed_with_error_data": True}})
    with pytest.raises(NSSProcessingException) as thrown:
        run()
    assert str(thrown.value) == STEP + "Configuration does not contain property 'configuration.keep_input_file_name_for_qc_report'"


def test_the_format_file_is_checked_before_the_configuration_keys_are_read():
    install_bucket({FORMAT: samples.NSS_INCORRECT_FORMAT, DATA: samples.INPUT_DATA_1_INPUT_ID_3_HITS})
    replace_configuration({})

    with pytest.raises(NSSProcessingException) as thrown:
        main(CsvTaskInput(format_file_location=FORMAT, data_file_location=DATA))

    assert str(thrown.value).startswith(STEP + "Errors found: [")


def test_main_logs_the_parse_result_with_evelyns_text(caplog):
    caplog.set_level(logging.INFO, logger="main")

    run_csv_task(samples.NSS_FULL_FORMAT, samples.INPUT_DATA_1_INPUT_ID_3_HITS)

    assert "Parsing completed. 3 out of 3 alerts will proceed to NSS main Business Process." in [r.getMessage() for r in caplog.records]
