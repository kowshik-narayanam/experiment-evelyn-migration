"""Step "csv-schema-producer" of the main Names Screening flow.

Ports CsvSchemaProducerProcessor (J:task/csv/CsvSchemaProducerProcessor.java:35-63; aliases in docs/mapping.md
section 0). Evelyn's class is a Spring bean with two services injected (TransactionService, AnalyticsService) and a
Gson; here the function `main` does the same job and the two services come from the evmig-nss wheel.

What it does, as Java does (J:...Processor.java:44-62):
  1. parse `screened_data` and `wle_list` (Gson fromJson <-> pydantic model_validate),
  2. start the transaction (status NEW), the 3-argument form (mapping claim 15),
  3. write the alert row and one hit row per WLE (mapping claim 16),
  4. return the six fields of mapping claim 17.

Nothing at import time touches the SDK: `uipath init` imports this file without a login (get_sdk() is lazy).
"""
from typing import Any

from pydantic import BaseModel, ConfigDict

from evmig_nss.core.errors import nss_step
from evmig_nss.core.repository import AlertAnalyticsRepository, HitAnalyticsRepository, TransactionRepository
from evmig_nss.core.sdk import get_sdk
from evmig_nss.core.strings import is_blank
from evmig_nss.schema.models import ScreenedData, WleData
from evmig_nss.service.analytics_service import AnalyticsService
from evmig_nss.service.transaction_service import RunContext, TransactionService

STEP_ID = "csv-schema-producer"  # J:task/csv/CsvSchemaProducerProcessor.java:35 @TaskProcessor(id = "csv-schema-producer")


class ProducerIn(BaseModel):
    # Java: a record's keys. A Flow node sends every input it declares (null or "" when unset), and the runtime may add
    # keys of its own, so unknown keys are ignored and "absent" has to be read from the value (docs/decisions.md DEC-3).
    model_config = ConfigDict(extra="ignore")

    # Required inputs. They are typed `| None` only so that a null reaches the step and fails there with Evelyn's text;
    # without it the runtime would refuse the call before `main` runs. They stay `required` in the schema (no default).
    screened_data: dict[str, Any] | None  # ScreenedData as an object, camelCase keys; null or {} fails
    wle_list: list[dict[str, Any]] | None  # WleData objects; [] is fine (J: AnalyticsService.java:65 null-checks, then forEach), null fails
    bp_run_id: str | None  # the CSV flow's instance id; blank fails (RunContext). Stored as StartBpUuid (D-2)
    bp_start_time: str | None  # the UTC text csv-monitor-task returned (D-2)

    # Optional inputs.
    request_id: str | None = ""  # J:...Processor.java:48 .orElse(StringUtils.EMPTY)
    rest_request: str | dict[str, Any] | None = None  # REST input only; null, "" or {} all mean "absent"
    provider_id: str | None = None  # accepted, not used here: the main flow's Decision "Screening System" reads it


class ProducerOut(BaseModel):
    # The runtime dumps this with model_dump(); the field order is J:...Processor.java:56-61. Java names kept (claim 17).
    # The two records go out as plain objects (gson.toJson <-> model_dump(mode="json")), like they came in: a typed
    # ScreenedData here would put the whole nested schema, null variants included, into entry-points.json.
    transaction_id: str  # screened_data.uuid
    screened_data: dict[str, Any]
    wle_list: list[dict[str, Any]]
    request_id: str
    wle_count: int
    is_internal_request: bool  # true unless a REST request came with the record


def main(input: ProducerIn) -> ProducerOut:
    # Java: NSSTaskProcessor.process() catches every exception and rethrows it with the step text (Q14: raise).
    with nss_step(STEP_ID):
        # 1. Parse. Java: gson.fromJson(...) at J:...Processor.java:46-47; a missing value is a NullPointerException there.
        if not input.screened_data:  # null or {}
            raise ValueError("Required input 'screened_data' is missing or empty")
        if input.wle_list is None:
            raise ValueError("Required input 'wle_list' is missing (an empty list is allowed)")
        if is_blank(input.bp_start_time):
            raise ValueError("bp_start_time is empty: the CSV flow must pass the bp_start_time of csv-monitor-task")
        screened_data = ScreenedData.model_validate(input.screened_data)
        wle_list = [WleData.model_validate(wle) for wle in input.wle_list]
        request_id = input.request_id or ""
        is_internal_request = not input.rest_request  # J:...Processor.java:49: no `rest_request` key; None, "" and {} are all falsy

        # What WorkFusion's task context gave Evelyn (D-2). Built before any write: a blank bp_run_id raises here.
        run_context = RunContext.from_inputs(input.bp_run_id or "", input.bp_start_time)

        entities = get_sdk().entities
        transactions = TransactionService(TransactionRepository(entities), run_context)
        analytics = AnalyticsService(AlertAnalyticsRepository(entities), HitAnalyticsRepository(entities))

        # 2. J:...Processor.java:50. clientId defaults to "1" in ScreenedData, as in the Java class.
        transaction = transactions.start_new_transaction(screened_data.clientId, screened_data.uuid, request_id)
        # 3. J:...Processor.java:52
        analytics.init_full_analytics(transaction, screened_data, wle_list)

        # 4. J:...Processor.java:54-62
        return ProducerOut(
            transaction_id=transaction.TransactionUuid,
            screened_data=screened_data.model_dump(mode="json"),
            wle_list=[wle.model_dump(mode="json") for wle in wle_list],
            request_id=request_id,
            wle_count=len(wle_list),
            is_internal_request=is_internal_request,
        )
