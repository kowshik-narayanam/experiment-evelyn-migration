"""Shared by the tests of EvMigCsvTask."""
import json
import logging
from pathlib import Path
from types import SimpleNamespace

from evmig_nss.core.configuration import CONFIG_FILE_KEY, Configuration, reset_configuration_cache
from evmig_nss.core.sdk import get_sdk, set_sdk
from evmig_nss.testing import FakeBuckets, FakeEntities

from csv_data_service import CsvDataService, parse_csv
from main import CsvTaskInput, main

FUNCTION_DIR = Path(__file__).resolve().parent.parent  # .../EvMigEvelyn/EvMigCsvTask
REPO = FUNCTION_DIR.parents[1]
DATA_DIR = REPO / "data"  # the bucket mirror (EvMigFiles)

LOGGER_NAME = "csv_data_service_test"


def configuration_document(*, proceed_with_error_data=True, location_wle_enable=False, keep_input_file_name=False) -> dict:
    """The configuration file's content, nested as Evelyn's configuration_payload.json is.

    Defaults are those of the Java test helper ConfigurationPayload.CSV() (names-screening-test-utils, ConfigurationData.java:35,41
    and Model.java:107): keep_input_file_name_for_qc_report false, proceed_with_error_data true, location_wle_enable false.
    """
    return {
        "provider": {"FORMAT_FILE_LOCATION": "test-bucket/data/format-data.csv", "CSV_DATA_FILE_LOCATION": "test-bucket/data/"},
        "configuration": {
            "proceed_with_error_data": proceed_with_error_data,
            "keep_input_file_name_for_qc_report": keep_input_file_name,
        },
        "model": {"thresholds": {"location_wle_enable": location_wle_enable}},
    }


def make_configuration(**options) -> Configuration:
    """For the CsvDataService tests, where Java mocks JsonConfiguration."""
    return Configuration(configuration_document(**options))


def service_serving(files: dict[str, str]) -> CsvDataService:
    """A CsvDataService whose file reads are stubbed, as CsvDataServiceTest stubs S3DownloadService with Mockito.

    Java: `when(s3DownloadServiceMock.downloadS3Content(fileName)).thenReturn(TestUtils.readCsv(fileName))`. TestUtils.readCsv
    parses a resource file with the same CSV format as the real download; here parse_csv does. A file that was not stubbed
    answers an empty list, as an unstubbed Mockito mock does for a List return type.
    """
    service = CsvDataService(logging.getLogger(LOGGER_NAME), store=None)
    service.download_s3_content = lambda path: parse_csv(files[path]) if path in files else []
    return service


def install_bucket(files: dict[str, str | bytes], **configuration_options) -> FakeBuckets:
    """The SDK that main() gets: a fake bucket holding `files` plus the configuration file, and an empty Data Fabric."""
    files = {CONFIG_FILE_KEY: json.dumps(configuration_document(**configuration_options)), **files}
    buckets = FakeBuckets(files)
    set_sdk(SimpleNamespace(buckets=buckets, entities=FakeEntities()))
    return buckets


def replace_configuration(document: dict) -> None:
    """Swap the configuration file in the fake bucket installed by install_bucket, and forget the cached configuration."""
    get_sdk().buckets.files[CONFIG_FILE_KEY] = json.dumps(document)
    reset_configuration_cache()


def run_csv_task(format_text: str, data_text: str, *, data_name="input-data.csv", **configuration_options):
    """The IT's setup in one call: put the two files in the bucket as test-bucket/data/<name>, and run the step."""
    install_bucket({"test-bucket/data/format-data.csv": format_text, f"test-bucket/data/{data_name}": data_text}, **configuration_options)
    return main(CsvTaskInput(format_file_location="test-bucket/data/format-data.csv", data_file_location=f"test-bucket/data/{data_name}"))


def unordered_equal(actual: list, expected: list) -> bool:
    """Same items, any order. Java builds dates in HashMap order (CsvDataServiceTest ignores their order); the port keeps the row's order (D-8)."""
    remaining = list(expected)
    for item in actual:
        if item not in remaining:
            return False
        remaining.remove(item)
    return not remaining


def error_lines(caplog) -> list[str]:
    """The lines of the DataException that the one ERROR record carries, trimmed (Java: thrownCaptor.getValue().getMessage().split("\\n"))."""
    errors = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(errors) == 1, "exactly one ERROR record is expected"
    return [line.strip() for line in str(errors[0].exc_info[1]).split("\n")]


def error_message(caplog) -> str:
    errors = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(errors) == 1, "exactly one ERROR record is expected"
    return errors[0].getMessage()


def info_messages(caplog) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.levelno == logging.INFO]
