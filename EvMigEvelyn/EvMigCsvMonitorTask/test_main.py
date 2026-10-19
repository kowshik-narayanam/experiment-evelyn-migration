"""Tests of EvMigCsvMonitorTask.

Ports CsvMonitorTaskProcessorTest (the unit test) and CsvMonitorTaskProcessorIT (the 11 integration tests), then adds
the checks the Java tests leave out (the start time, the order of the steps, the bindings, the vendored wheel).

How the Java tests map here (Java -> Python):
  - Mockito mocks of S3DownloadService and the configuration  ->  FakeBuckets holding real files and a real
    configuration_payload.json (the library's fake of `sdk.buckets`), so the library's BucketStore runs for real;
  - the jnw S3MockClient of the IT                             ->  the same FakeBuckets, one bucket (EvMigFiles) whose
    object keys are the whole S3 path, "test-bucket/data/a.csv" (DEC-7);
  - ConfigurationPayload.CSV(format, data)                     ->  configuration_payload(format, data) below;
  - TaskResultAssert.hasError(text)                            ->  assert_fails_with(text, ...).
"""
import hashlib
import importlib
import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import main
import pytest
from evmig_nss.core import sdk as sdk_module
from evmig_nss.core.bucket_store import BucketStore
from evmig_nss.core.configuration import CONFIG_FILE_KEY, load_configuration
from evmig_nss.core.constants import BUCKET_NAME
from evmig_nss.core.data_fabric_row import parse_utc, utc_now
from evmig_nss.core.errors import NSSProcessingException
from evmig_nss.core.processing_attributes import DATA_FILE_LOCATION, FORMAT_FILE_LOCATION
from evmig_nss.core.sdk import LOCAL_BUCKET_DIR_ENV, set_sdk
from evmig_nss.testing import FakeBuckets, FakeEntities
from main import MonitorIn

HERE = Path(__file__).parent
REPO = HERE.parents[1]

DATA_TEXT = "input_id,input_full_name\n1,Alice Wonderland\n"  # the monitor never reads a data file; any text will do
FORMAT_TEXT = "nss_name,client_name\ninput_id,input_id\ninput_full_name,input_full_name\n"

# Java prints this in front of a failed step's message; Python raises only the message (D-8).
JAVA_CLASS_PREFIX = "com.workfusion.dw.nss.exceptions.NSSProcessingException: "


def configuration_payload(format_location: str, data_location: str) -> str:
    """ConfigurationPayload.CSV(...): the two provider keys, nested as in Evelyn's payload."""
    return json.dumps({"provider": {"FORMAT_FILE_LOCATION": format_location, "CSV_DATA_FILE_LOCATION": data_location}})


def install_buckets(files: dict, format_location: str, data_location: str) -> FakeBuckets:
    """Put the configuration and `files` in a fake EvMigFiles and make it the SDK's bucket service."""
    buckets = FakeBuckets({CONFIG_FILE_KEY: configuration_payload(format_location, data_location), **files})
    set_sdk(SimpleNamespace(buckets=buckets, entities=FakeEntities()))
    return buckets


def run_monitor(files: dict, format_location: str, data_location: str) -> dict:
    """Run the function and return its output the way the runtime dumps it (field names, JSON values)."""
    install_buckets(files, format_location, data_location)
    return main.main(MonitorIn()).model_dump(mode="json")


def assert_fails_with(java_text: str, files: dict, format_location: str, data_location: str) -> None:
    """The step fails with Java's text, apart from the class name in front of it (D-8)."""
    install_buckets(files, format_location, data_location)
    with pytest.raises(NSSProcessingException) as raised:
        main.main(MonitorIn())
    assert JAVA_CLASS_PREFIX + str(raised.value) == java_text


# ---------------------------------------------------------------------------------------------------------------
# CsvMonitorTaskProcessorTest
# ---------------------------------------------------------------------------------------------------------------


def test_run():  # ports CsvMonitorTaskProcessorTest.java:45 run
    # Java mocks the file list as "bucket/data_1.scv" and "bucket/data_2.scv". A real listing keeps only keys ending
    # in ".csv" (S3DownloadService.java:84), so the data files here end in ".csv"; the format file keeps Java's ".scv"
    # and is therefore not listed as data. Asserted values: two rows of two keys, the format path in each.
    output = run_monitor(
        {"bucket/nss/nss_input_format.scv": FORMAT_TEXT, "bucket/data_1.csv": DATA_TEXT, "bucket/data_2.csv": DATA_TEXT},
        format_location="bucket/nss/nss_input_format.scv",
        data_location="bucket/",
    )
    rows = output["rows"]
    assert len(rows) == 2
    for row in rows:
        assert len(row) == 2
        assert "data_file_location" in row
        assert row["format_file_location"] == "bucket/nss/nss_input_format.scv"
    assert sorted(row["data_file_location"] for row in rows) == ["bucket/data_1.csv", "bucket/data_2.csv"]


# ---------------------------------------------------------------------------------------------------------------
# CsvMonitorTaskProcessorIT
# ---------------------------------------------------------------------------------------------------------------


def test_csv_run():  # ports CsvMonitorTaskProcessorIT.java:37 csvRun ("process multiple files")
    files = {
        "test-bucket/data/input-data-1.csv": DATA_TEXT,
        "test-bucket/data/other-file.txt": DATA_TEXT,  # not a csv: ignored
        "test-bucket/data/input-data-2.csv": DATA_TEXT,
        "test-bucket/data/data-october/input-data-3.csv": DATA_TEXT,  # a deeper folder: listed
        "test-bucket/nss_input_format.csv": FORMAT_TEXT,  # outside data/: not listed
        "test-bucket/input-data_with_empty_input_id.csv": DATA_TEXT,  # outside data/: not listed
    }
    rows = run_monitor(files, "test-bucket/nss_input_format.csv", "test-bucket/data/")["rows"]
    assert len(rows) == 3
    # Java: containsExactlyInAnyOrder, so the order is not compared here (it is, in the test after the IT ports)
    assert sorted((row["data_file_location"], row["format_file_location"]) for row in rows) == [
        ("test-bucket/data/data-october/input-data-3.csv", "test-bucket/nss_input_format.csv"),
        ("test-bucket/data/input-data-1.csv", "test-bucket/nss_input_format.csv"),
        ("test-bucket/data/input-data-2.csv", "test-bucket/nss_input_format.csv"),
    ]


def test_csv_run_with_concrete_file():  # ports CsvMonitorTaskProcessorIT.java:68 csvRunWithConcreteFile ("process single file")
    files = {"test-bucket/data/input-data.csv": DATA_TEXT, "test-bucket/nss_input_format.csv": FORMAT_TEXT}
    rows = run_monitor(files, "test-bucket/nss_input_format.csv", "test-bucket/data/input-data.csv")["rows"]
    assert rows[0]["data_file_location"] == "test-bucket/data/input-data.csv"
    assert rows[0]["format_file_location"] == "test-bucket/nss_input_format.csv"
    assert len(rows) == 1


def test_csv_run_input_format_file_not_exist():  # ports CsvMonitorTaskProcessorIT.java:92 csvRunInputFormatFileNotExist
    assert_fails_with(
        "com.workfusion.dw.nss.exceptions.NSSProcessingException: Exception was thrown by Evelyn NSS step csv-monitor-task: Please provide correct path to file: test-bucket/nss_input_format"
        ".csv",
        {"test-bucket/nss_input_format_other.csv": FORMAT_TEXT},
        "test-bucket/nss_input_format.csv",
        "test-bucket/data/",
    )


def test_csv_run_not_valid_path_to_csv_data_file():  # ports CsvMonitorTaskProcessorIT.java:114 csvRunNotValidPathToCsvDataFile
    assert_fails_with(
        "com.workfusion.dw.nss.exceptions.NSSProcessingException: Exception was thrown by Evelyn NSS step csv-monitor-task: Please provide correct path to file: test-bucket/data/input-data"
        ".csv",
        {"test-bucket/data/other-file.csv": DATA_TEXT, "test-bucket/nss_input_format.csv": FORMAT_TEXT},
        "test-bucket/nss_input_format.csv",
        "test-bucket/data/input-data.csv",
    )


def test_csv_run_no_csv_files_in_folder():  # ports CsvMonitorTaskProcessorIT.java:138 csvRunNoCsvFilesInFolder
    assert_fails_with(
        "com.workfusion.dw.nss.exceptions.NSSProcessingException: Exception was thrown by Evelyn NSS step csv-monitor-task: There are no csv files in test-bucket/data/. Please provide "
        "correct path to csv data.: test-bucket/data/",
        {"test-bucket/data/other-file.txt": DATA_TEXT, "test-bucket/nss_input_format.csv": FORMAT_TEXT},
        "test-bucket/nss_input_format.csv",
        "test-bucket/data/",
    )


def test_csv_run_no_csv_files_in_bucket():  # ports CsvMonitorTaskProcessorIT.java:161 csvRunNoCsvFilesInBucket
    assert_fails_with(
        "com.workfusion.dw.nss.exceptions.NSSProcessingException: Exception was thrown by Evelyn NSS step csv-monitor-task: There are no csv files in empty-bucket/. Please provide correct "
        "path to csv data.: empty-bucket/",
        {"empty-bucket/file.txt": DATA_TEXT, "test-bucket/nss_input_format.csv": FORMAT_TEXT},
        "test-bucket/nss_input_format.csv",
        "empty-bucket/",
    )


def test_csv_run_data_file_is_not_csv():  # ports CsvMonitorTaskProcessorIT.java:184 csvRunDataFileIsNotCsv
    assert_fails_with(
        "com.workfusion.dw.nss.exceptions.NSSProcessingException: Exception was thrown by Evelyn NSS step csv-monitor-task: There are no csv files in test-bucket/data/input-data.txt. Please"
        " provide correct path to csv data.: test-bucket/data/input-data.txt",
        {"test-bucket/data/input-data.txt": DATA_TEXT, "test-bucket/nss_input_format.csv": FORMAT_TEXT},
        "test-bucket/nss_input_format.csv",
        "test-bucket/data/input-data.txt",
    )


def test_csv_run_no_bucket_name():  # ports CsvMonitorTaskProcessorIT.java:206 csvRunNoBucketName
    assert_fails_with(
        "com.workfusion.dw.nss.exceptions.NSSProcessingException: Exception was thrown by Evelyn NSS step csv-monitor-task: Missing bucket name: nss_input_format.csv",
        {},
        "nss_input_format.csv",
        "test-bucket/data/",
    )


def test_csv_run_no_source():  # ports CsvMonitorTaskProcessorIT.java:223 csvRunNoSource
    # Java creates an empty bucket (s3Client.createBucket). Here a bucket "exists" when a key lies under its folder
    # (D-4), so one unrelated file stands in for the empty bucket.
    assert_fails_with(
        "com.workfusion.dw.nss.exceptions.NSSProcessingException: Exception was thrown by Evelyn NSS step csv-monitor-task: Path to file or folder isn't correct: test-bucket/",
        {"test-bucket/data/other.csv": DATA_TEXT},
        "test-bucket/",
        "test-bucket/data/",
    )


def test_csv_run_wrong_bucket_name_in_path_to_format_file():  # ports CsvMonitorTaskProcessorIT.java:242 csvRunWrongBucketNameInPathToFormatFile
    assert_fails_with(
        "com.workfusion.dw.nss.exceptions.NSSProcessingException: Exception was thrown by Evelyn NSS step csv-monitor-task: Bucket with such name doesn't exist on S3: other-wrong-bucket",
        {},
        "other-wrong-bucket/nss_input_format.csv",
        "wrong-bucket/data/input-data.csv",
    )


def test_csv_run_wrong_bucket_name_in_path_to_csv_data_file():  # ports CsvMonitorTaskProcessorIT.java:262 csvRunWrongBucketNameInPathToCsvDataFile
    assert_fails_with(
        "com.workfusion.dw.nss.exceptions.NSSProcessingException: Exception was thrown by Evelyn NSS step csv-monitor-task: Bucket with such name doesn't exist on S3: wrong-bucket",
        {"other-wrong-bucket/nss_input_format.csv": FORMAT_TEXT},
        "other-wrong-bucket/nss_input_format.csv",
        "wrong-bucket/data/input-data.csv",
    )


# ---------------------------------------------------------------------------------------------------------------
# Own tests: what the Java tests leave out
# ---------------------------------------------------------------------------------------------------------------


def test_the_output_is_exactly_the_rows_and_the_start_time_and_no_run_id(monkeypatch):
    # DEC-5: bp_start_time is added; a run id is not made here (the Flow passes $metadata.InstanceId on).
    monkeypatch.setattr(main, "utc_now", lambda: datetime(2026, 10, 19, 7, 15, 0, 123456, tzinfo=UTC))
    output = run_monitor(
        {"test-bucket/data/a.csv": DATA_TEXT, "test-bucket/nss_input_format.csv": FORMAT_TEXT},
        "test-bucket/nss_input_format.csv",
        "test-bucket/data/",
    )
    assert output == {
        "rows": [{"data_file_location": "test-bucket/data/a.csv", "format_file_location": "test-bucket/nss_input_format.csv"}],
        "bp_start_time": "2026-10-19T07:15:00.123Z",
    }


def test_the_row_keys_are_the_lower_cased_enum_names():
    # J:task/csv/CsvMonitorTaskProcessor.java:40-41: DATA_FILE_LOCATION.name().toLowerCase(), not the config key.
    assert set(main.DataFileRow.model_fields) == {DATA_FILE_LOCATION, FORMAT_FILE_LOCATION}
    assert (DATA_FILE_LOCATION, FORMAT_FILE_LOCATION) == ("data_file_location", "format_file_location")


def test_the_start_time_is_taken_before_any_bucket_call(monkeypatch):
    buckets = install_buckets(
        {"test-bucket/data/a.csv": DATA_TEXT, "test-bucket/nss_input_format.csv": FORMAT_TEXT},
        "test-bucket/nss_input_format.csv",
        "test-bucket/data/",
    )

    def clock():
        buckets.calls.append("clock")  # lands in the same list as the bucket calls, so the order shows
        return datetime(2026, 10, 19, 7, 15, 0, tzinfo=UTC)

    monkeypatch.setattr(main, "utc_now", clock)
    main.main(MonitorIn())
    assert buckets.calls[0] == "clock"
    assert buckets.calls.count("clock") == 1


def test_the_start_time_is_the_real_utc_clock_by_default():
    before = utc_now()
    output = run_monitor(
        {"test-bucket/data/a.csv": DATA_TEXT, "test-bucket/nss_input_format.csv": FORMAT_TEXT},
        "test-bucket/nss_input_format.csv",
        "test-bucket/data/",
    )
    after = utc_now()
    started = parse_utc(output["bp_start_time"])
    assert output["bp_start_time"].endswith("Z")
    assert before.replace(microsecond=before.microsecond // 1000 * 1000) <= started <= after  # the text keeps milliseconds


def test_the_data_files_come_in_the_lexicographic_order_of_the_store():
    files = {f"test-bucket/data/{name}": DATA_TEXT for name in ("b.csv", "data-october/c.csv", "a.csv")}
    files["test-bucket/nss_input_format.csv"] = FORMAT_TEXT
    rows = run_monitor(files, "test-bucket/nss_input_format.csv", "test-bucket/data/")["rows"]
    assert [row["data_file_location"] for row in rows] == [
        "test-bucket/data/a.csv",
        "test-bucket/data/b.csv",
        "test-bucket/data/data-october/c.csv",
    ]


def test_a_format_file_under_the_data_folder_is_listed_as_data_too():
    # Evelyn does not exclude the format file from the listing (mapping claim 5, Q9): a quirk kept on purpose.
    files = {"test-bucket/data/a.csv": DATA_TEXT, "test-bucket/data/nss_input_format.csv": FORMAT_TEXT}
    rows = run_monitor(files, "test-bucket/data/nss_input_format.csv", "test-bucket/data/")["rows"]
    assert [row["data_file_location"] for row in rows] == ["test-bucket/data/a.csv", "test-bucket/data/nss_input_format.csv"]


def test_the_format_file_is_checked_before_the_data_files_are_listed():
    # CsvMonitorTaskProcessor.java:33 before :34: with both wrong, the format error is the one that comes out.
    assert_fails_with(
        JAVA_CLASS_PREFIX
        + "Exception was thrown by Evelyn NSS step csv-monitor-task: Please provide correct path to file: test-bucket/missing_format.csv",
        {"test-bucket/data/other.txt": DATA_TEXT},
        "test-bucket/missing_format.csv",
        "test-bucket/data/",  # would fail with "There are no csv files"
    )


@pytest.mark.parametrize(
    "document, missing",
    [
        ({"provider": {"CSV_DATA_FILE_LOCATION": "test-bucket/data/"}}, "provider.FORMAT_FILE_LOCATION"),
        ({"provider": {"FORMAT_FILE_LOCATION": "test-bucket/f.csv"}}, "provider.CSV_DATA_FILE_LOCATION"),
        ({}, "provider.FORMAT_FILE_LOCATION"),  # the format key is read first (CsvMonitorTaskProcessor.java:30-31)
    ],
    ids=["no format key", "no data key", "neither: the format key is reported"],
)
def test_a_missing_configuration_key_fails_the_step_with_the_toolkits_text(document, missing):
    set_sdk(SimpleNamespace(buckets=FakeBuckets({CONFIG_FILE_KEY: json.dumps(document)}), entities=FakeEntities()))
    with pytest.raises(NSSProcessingException) as raised:
        main.main(MonitorIn())
    assert str(raised.value) == f"Exception was thrown by Evelyn NSS step csv-monitor-task: Configuration does not contain property '{missing}'"


def test_a_missing_configuration_file_fails_the_step_with_the_original_error_as_cause():
    set_sdk(SimpleNamespace(buckets=FakeBuckets({}), entities=FakeEntities()))
    with pytest.raises(NSSProcessingException) as raised:
        main.main(MonitorIn())
    assert str(raised.value).startswith("Exception was thrown by Evelyn NSS step csv-monitor-task: ")
    assert isinstance(raised.value.__cause__, FileNotFoundError)


def test_an_empty_bucket_does_not_exist_here_unlike_s3():
    # D-4: Java's csvRunNoSource creates an empty bucket and gets "Path to file or folder isn't correct";
    # here a bucket with no key under its folder is a missing bucket.
    assert_fails_with(
        JAVA_CLASS_PREFIX + "Exception was thrown by Evelyn NSS step csv-monitor-task: Bucket with such name doesn't exist on S3: test-bucket",
        {},
        "test-bucket/",
        "test-bucket/data/",
    )


def test_the_configuration_is_read_once_per_process():
    buckets = install_buckets({"test-bucket/data/a.csv": DATA_TEXT, "test-bucket/f.csv": FORMAT_TEXT}, "test-bucket/f.csv", "test-bucket/data/")
    main.main(MonitorIn())
    main.main(MonitorIn())
    assert buckets.calls.count(("download", CONFIG_FILE_KEY)) == 1  # DEC-8: cached in the process


def test_the_input_takes_no_fields_and_ignores_the_ones_maestro_adds():
    # A Flow node sends every input it has, and Maestro adds fields of its own (loop context, error-port flags).
    for sent in ({}, {"iterator": [1], "errorHandlingEnabled": False, "anything": None}):
        assert MonitorIn.model_validate(sent).model_dump() == {}
    assert MonitorIn.model_fields == {}


def test_main_works_unchanged_against_a_local_folder(tmp_path, monkeypatch):
    # The local-run switch of the library (EVMIG_LOCAL_BUCKET_DIR): the folder is the bucket, no login.
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "configuration_payload.json").write_text(configuration_payload("b/f.csv", "b/data/"), encoding="utf-8")
    (tmp_path / "b" / "data").mkdir(parents=True)
    (tmp_path / "b" / "f.csv").write_text(FORMAT_TEXT, encoding="utf-8")
    (tmp_path / "b" / "data" / "one.csv").write_text(DATA_TEXT, encoding="utf-8")
    monkeypatch.setenv(LOCAL_BUCKET_DIR_ENV, str(tmp_path))
    output = main.main(MonitorIn())
    assert [row.data_file_location for row in output.rows] == ["b/data/one.csv"]


def test_importing_main_creates_no_sdk_client():
    # `uipath init` imports main.py without a login; UiPath() would fail there. The library creates it lazily.
    set_sdk(None)
    importlib.reload(main)
    assert sdk_module._sdk is None


# ---------------------------------------------------------------------------------------------------------------
# The project's own files
# ---------------------------------------------------------------------------------------------------------------


def test_bindings_json_declares_the_one_bucket_the_library_uses():
    # `uipath init` cannot infer it (the bucket calls are inside the wheel), so it is hand-written and checked here.
    resources = json.loads((HERE / "bindings.json").read_text(encoding="utf-8"))["resources"]
    assert [(r["resource"], r["key"]) for r in resources] == [("bucket", "EvMigFiles")]
    assert resources[0]["key"] == BUCKET_NAME  # the name BucketStore asks for
    assert resources[0]["value"]["name"]["defaultValue"] == BUCKET_NAME
    assert resources[0]["value"]["folderPath"]["defaultValue"] == ""


def test_entry_points_json_matches_the_models():
    # entry-points.json is generated by `uipath init`; this fails when the models changed and init was not re-run.
    entry = json.loads((HERE / "entry-points.json").read_text(encoding="utf-8"))["entryPoints"]
    assert [e["filePath"] for e in entry] == ["main"]
    assert set(entry[0]["input"]["properties"]) == set(MonitorIn.model_fields)
    assert set(entry[0]["output"]["properties"]) == set(main.MonitorOut.model_fields) == {"rows", "bp_start_time"}
    assert set(entry[0]["output"]["required"]) == {"rows", "bp_start_time"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_vendored_wheel_is_the_librarys_built_wheel():
    # DEC-2: the copy in wheels/ is byte-identical to evmig-nss/dist/. A rebuilt library that was not re-vendored fails here.
    vendored = sorted((HERE / "wheels").glob("evmig_nss-*.whl"))
    assert len(vendored) == 1
    built = REPO / "evmig-nss" / "dist" / vendored[0].name
    assert built.exists(), f"{built} is missing"
    assert sha256(vendored[0]) == sha256(built)


def test_uv_lock_pins_the_vendored_wheel():
    lock = tomllib.loads((HERE / "uv.lock").read_text(encoding="utf-8"))
    package = next(p for p in lock["package"] if p["name"] == "evmig-nss")
    wheel = next(HERE.glob("wheels/evmig_nss-*.whl"))
    assert package["source"] == {"path": f"wheels/{wheel.name}"}
    assert package["wheels"][0]["hash"] == "sha256:" + sha256(wheel)
    assert next(p for p in lock["package"] if p["name"] == "uipath")["version"] == "2.14.27"  # DEC-9


def test_the_library_is_imported_from_the_vendored_wheel_not_from_its_source():
    import evmig_nss

    assert "site-packages" in Path(evmig_nss.__file__).parts
    # and BucketStore/load_configuration are the library's: this file only wires them
    assert BucketStore.__module__ == "evmig_nss.core.bucket_store"
    assert load_configuration.__module__ == "evmig_nss.core.configuration"
