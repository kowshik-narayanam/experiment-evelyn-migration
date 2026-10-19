"""EvMigCsvMonitorTask: ports the csv-monitor-task step of Evelyn's CSV File Ingestion BP.

Java class: CsvMonitorTaskProcessor (J:task/csv/CsvMonitorTaskProcessor.java:19-45), `@TaskProcessor(id = "csv-monitor-task")`.
It reads the two file locations from the configuration, checks that the format file exists, lists the CSV data files
and outputs one row per data file. The Spring services it uses are the library's: S3DownloadService is
evmig_nss.core.bucket_store.BucketStore (over the bucket EvMigFiles), the configuration reader is
evmig_nss.core.configuration.

Added by the port (docs/decisions.md DEC-5, D-2): `bp_start_time`, the UTC time this function starts. Evelyn gets the
BP's start time from Control Tower; the Flow passes this value on to csv-schema-producer.
"""
from evmig_nss.core.bucket_store import BucketStore
from evmig_nss.core.configuration import DATA_FILE_LOCATION_PATH, FORMAT_FILE_LOCATION_PATH, load_configuration
from evmig_nss.core.data_fabric_row import format_utc, utc_now
from evmig_nss.core.errors import nss_step
from evmig_nss.core.sdk import get_sdk
from pydantic import BaseModel, ConfigDict

STEP_ID = "csv-monitor-task"  # J:task/csv/CsvMonitorTaskProcessor.java:19


# A Python function's input and output are pydantic models, where Java's processor reads and writes
# TaskInputData / TaskOutputData. The Flow node's fields are these models' field names.
class MonitorIn(BaseModel):
    # The step reads no input (J:task/csv/CsvMonitorTaskProcessor.java:27: `run` never touches `input`).
    # extra="ignore": Maestro adds fields of its own to a job's input, and they must not fail the step.
    model_config = ConfigDict(extra="ignore")


class DataFileRow(BaseModel):
    # One TaskOutputRow. The keys are the lower-cased enum names (J:task/csv/CsvMonitorTaskProcessor.java:40-41),
    # not the configuration keys. Snake_case, no aliases: the runtime dumps the output by field name.
    data_file_location: str
    format_file_location: str


class MonitorOut(BaseModel):
    rows: list[DataFileRow]  # TaskOutputData's rows, one per CSV data file
    bp_start_time: str  # UTC text, e.g. 2026-10-19T07:15:00.123Z (library's format_utc)


def main(input: MonitorIn) -> MonitorOut:
    # Taken first, before any bucket call: the run's start time (DEC-5, Q3). No run id is made here (DEC-5).
    bp_start_time = format_utc(utc_now())

    # nss_step makes any error come out as "Exception was thrown by Evelyn NSS step csv-monitor-task: <message>",
    # as NSSTaskProcessor.process() + CustomErrorHandling do in Java. The error is raised (Q14).
    with nss_step(STEP_ID):
        # get_sdk() is called here, not at import: `uipath init` imports this file without a login.
        store = BucketStore(get_sdk().buckets)  # Java: the injected S3DownloadService
        configuration = load_configuration(store)  # Java: taskConfigurationProvider.getDigitalWorkerConfiguration()

        # The same two required properties, in the same order (CsvMonitorTaskProcessor.java:30-31).
        format_file_location = configuration.get_required_property(FORMAT_FILE_LOCATION_PATH)
        csv_data_file_location = configuration.get_required_property(DATA_FILE_LOCATION_PATH)

        store.validate_file_exists(format_file_location)  # :33, fails when the format file is missing
        csv_data_files = store.get_csv_files_list(csv_data_file_location)  # :34, fails when there are none

        # :37-42, one row per data file; every row carries the same format file.
        rows = [DataFileRow(data_file_location=csv_file, format_file_location=format_file_location) for csv_file in csv_data_files]

    return MonitorOut(rows=rows, bp_start_time=bp_start_time)
