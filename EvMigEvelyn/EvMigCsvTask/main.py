"""EvMigCsvTask: Evelyn's `csv-task` step. One data file in, one row per alert out (or a single stop row).

Ports J:task/csv/CsvTaskProcessor.java:35 (J = names-screening-jnw/src/main/java/com/workfusion/dw/nss).
The parsing is in csv_data_service.py (CsvDataService.java), the format-file checks in file_format_validation.py.

How a Java task processor maps to a Python function:
  TaskInputData  (a map)                       ->  CsvTaskInput, a pydantic model (one field per key the step reads)
  TaskOutputData (rows of string maps)         ->  CsvTaskOutput, a pydantic model (a list of CsvTaskRow)
  gson.toJson(screenedData)                    ->  nothing to do: the model is returned as it is and the runtime dumps it
  throwing an exception                        ->  raising one: nss_step gives it Evelyn's text
Evelyn sends `screened_data` and `wle_list` on as JSON text; here they stay objects (difference D-8).
"""
import logging
import uuid

from pydantic import BaseModel, ConfigDict

from evmig_nss.core.bucket_store import BucketStore
from evmig_nss.core.configuration import KEEP_INPUT_FILE_NAME_FOR_QC_REPORT_PATH, load_configuration
from evmig_nss.core.errors import nss_step
from evmig_nss.core.sdk import get_sdk
from evmig_nss.schema.models import ScreenedData, WleData

from csv_data_service import CsvDataService

logger = logging.getLogger(__name__)


class CsvTaskInput(BaseModel):
    # A Flow node also sends fields the step does not know (the loop's context, for one): ignore them.
    model_config = ConfigDict(extra="ignore")

    # The two keys CsvMonitorTaskProcessor puts on each of its rows (J:task/csv/CsvTaskProcessor.java:43-48).
    # Required: a missing or null value fails, as Evelyn fails on a missing key. "" is passed on, and the bucket
    # store then fails it with Evelyn's own text ("Missing bucket name: ").
    format_file_location: str
    data_file_location: str


# Two shapes share this one row model, so a Flow reads `rows[i].stop` on every row:
#   an alert:     screened_data, wle_list and request_id are set; stop is null
#   the stop row: stop is "true" (the text, as in Evelyn); the other three are null
# Evelyn's rows have only the keys they use. Here all four keys are always present (null when unused): one schema for the
# Flow, and "Should proceed?" is a plain `currentItem.stop !== "true"`.
class CsvTaskRow(BaseModel):
    """One output row: an alert with its hits, or the stop row."""

    screened_data: ScreenedData | None = None
    wle_list: list[WleData] | None = None
    request_id: str | None = None
    stop: str | None = None


class CsvTaskOutput(BaseModel):
    rows: list[CsvTaskRow]


def main(input: CsvTaskInput) -> CsvTaskOutput:
    """J:task/csv/CsvTaskProcessor.java:42 `run`."""
    with nss_step("csv-task"):
        # The SDK client and the configuration are created here, not at import: `uipath init` imports this file with no login.
        store = BucketStore(get_sdk().buckets)
        configuration = load_configuration(store)
        csv_data_service = CsvDataService(logger, store)

        format = csv_data_service.map_file_format(input.format_file_location)
        data = csv_data_service.map_data_file(input.data_file_location, format, configuration)

        # One value per file: every alert of the file shares it (J:task/csv/CsvTaskProcessor.java:56-61).
        if configuration.get_required_boolean(KEEP_INPUT_FILE_NAME_FOR_QC_REPORT_PATH):
            request_id = input.data_file_location[input.data_file_location.rfind("/") + 1 :]  # the file's name, extension included
        else:
            request_id = str(uuid.uuid4())

        if not data:
            # No alert can proceed (J:task/csv/CsvTaskProcessor.java:77): one row that tells the Flow to stop this file.
            return CsvTaskOutput(rows=[CsvTaskRow(stop="true")])
        return CsvTaskOutput(
            rows=[
                CsvTaskRow(screened_data=screened_data, wle_list=wle_list, request_id=request_id)
                for screened_data, wle_list in data
                if wle_list  # J:task/csv/CsvTaskProcessor.java:69: an alert with no hits is not sent on
            ]
        )
