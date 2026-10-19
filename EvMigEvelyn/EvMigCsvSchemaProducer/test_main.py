"""Tests of the csv-schema-producer function. Java tests are under
/Users/knarayanam/WorkfusionRepos/NSS/names-screening/names-screening-jnw/src/test/java/com/workfusion/dw/nss/task/csv/ ;
every test says `ports <JavaTestFile>:<line>` or `own test` (nothing in Java covers it).

No tenant and no network: Data Fabric is the library's FakeEntities (see conftest.py). `run()` builds the input the way the
UiPath runtime does (ProducerIn.model_validate of a dict) and calls main().
"""
import hashlib
import json
import tomllib
import uuid
from datetime import UTC, datetime, timedelta
from importlib.metadata import version
from pathlib import Path
from unittest import mock

import pytest

import main
from evmig_nss.core.data_fabric_row import parse_utc
from evmig_nss.core.errors import NSSProcessingException
from evmig_nss.schema.models import EntityType, NameEntity, ScreenedData, WleData
from evmig_nss.service.analytics_service import AnalyticsService
from evmig_nss.service.transaction_service import TransactionService

HERE = Path(__file__).parent
REPO = HERE.parents[1]  # experiment-evelyn-migration/
STEP = "Exception was thrown by Evelyn NSS step csv-schema-producer: "
RUN_ID = "11111111-2222-3333-4444-555555555555"
START = "2026-10-19T07:15:00.123Z"
TRANSACTIONS, ALERTS, HITS = "EvMigTransaction-entity", "EvMigAlertAnalytics-entity", "EvMigHitAnalytics-entity"


def new_uuid() -> str:
    return str(uuid.uuid4())


def screened(**fields) -> ScreenedData:
    """An alert like csv-task writes it (placeholder names only)."""
    return ScreenedData(**{
        "uuid": new_uuid(), "id": "A-1", "category": "Sanctions", "entityType": EntityType.INDIVIDUAL,
        "name": NameEntity(fullName="Alice Wonderland"), "clientId": "5", "goldDecision": "1", **fields,
    })


def hit(**fields) -> WleData:
    return WleData(**{
        "uuid": new_uuid(), "id": "H-1", "category": "Sanctions", "entityType": EntityType.INDIVIDUAL,
        "name": NameEntity(fullName="Alyce Wonderland"), "goldDecision": "1", **fields,
    })


def inputs(screened_data: ScreenedData, wle_list=(), **overrides) -> dict:
    """The dict a Flow node sends. `rest_request` is left out, as the CSV flow leaves it."""
    return {
        "screened_data": screened_data.model_dump(mode="json"),
        "wle_list": [wle.model_dump(mode="json") for wle in wle_list],
        "request_id": "alice.csv", "bp_run_id": RUN_ID, "bp_start_time": START, "provider_id": "CSV",
        **overrides,
    }


def run(screened_data: ScreenedData, wle_list=(), **overrides) -> main.ProducerOut:
    return main.main(main.ProducerIn.model_validate(inputs(screened_data, wle_list, **overrides)))


def run_raw(overrides: dict) -> main.ProducerOut:
    """A valid input with `overrides` laid over it, as raw JSON values (for inputs that are not models)."""
    return main.main(main.ProducerIn.model_validate({**inputs(screened(), [hit()]), **overrides}))


# ---- the Java tests ----------------------------------------------------------------------------------------------


def test_should_start_transaction(entities):
    # ports CsvSchemaProducerProcessorTest.java:52 shouldStartTransaction
    transaction_id = new_uuid()
    request_id = new_uuid()
    screened_data = ScreenedData(name=NameEntity(fullName="John Doe"), uuid=transaction_id)
    wle_data = [WleData(name=NameEntity(fullName="John notSureDoe"))]

    # Java mocks the two services and verifies their calls; here the real ones run on the fake Data Fabric, and a
    # spy (autospec, side_effect = the real method) records what main() called them with.
    real_start, real_init = TransactionService.start_new_transaction, AnalyticsService.init_full_analytics
    with mock.patch.object(TransactionService, "start_new_transaction", autospec=True, side_effect=real_start) as start, \
            mock.patch.object(AnalyticsService, "init_full_analytics", autospec=True, side_effect=real_init) as init:
        # Java also sends `_sys_ext_record_id` ("123", REST_REQUEST_ID); this step ignores it
        result = run(screened_data, wle_data, request_id=request_id, _sys_ext_record_id="123")

    # verify(transactionServiceMock).startNewTransaction(clientId, uuid, requestId): the 3-argument form (claim 15)
    start.assert_called_once_with(mock.ANY, screened_data.clientId, transaction_id, request_id)
    # verify(analyticsServiceMock).initFullAnalytics(transactionMock, screenedData, wleData)
    init.assert_called_once()
    _, transaction, analytics_screened_data, analytics_wle_data = init.call_args.args
    assert transaction.TransactionUuid == transaction_id
    assert analytics_screened_data == screened_data
    assert analytics_wle_data == wle_data

    # the four assertions on the output row
    assert result.transaction_id == transaction_id
    assert ScreenedData.model_validate(result.screened_data) == screened_data
    assert [WleData.model_validate(wle) for wle in result.wle_list] == wle_data
    assert result.request_id == request_id
    # beyond Java: the real services wrote the rows
    assert [row["TransactionUuid"] for row in entities.rows[TRANSACTIONS]] == [transaction_id]


def test_should_persist_gold_value_for_alert_and_hit_for_analytics(entities):
    # ports CsvSchemaProducerProcessorIT.java:138 shouldPersistGoldValueForAlertAndHitForAnalytics
    alert_gold_decisions = ["0", "1", "2", "3", ""]
    hit_gold_decisions = ["1", "0", "2", "3", ""]  # the hit of alert i is "i + 1"
    for i in range(5):
        alert = screened(id=str(i), entityType=EntityType.ORGANIZATION, name=NameEntity(fullName="Wonderland Bank"),
                         goldDecision=alert_gold_decisions[i])
        wle = hit(id=str(i + 1), entityType=EntityType.ORGANIZATION, name=NameEntity(fullName="Wonderland Bank"),
                  goldDecision=hit_gold_decisions[i])
        run(alert, [wle], request_id=new_uuid(), bp_run_id=new_uuid())  # a new run id each time, as withBpExecutionUuid(random)

    alerts = entities.rows[ALERTS]
    assert len(alerts) == 5
    # Collectors.toMap fails on a duplicate key in Java; a dict would hide one, so the size of the result is compared too
    assert {row["AlertId"]: row["GoldDecision"] for row in alerts} == {"0": "0", "1": "1", "2": "2", "3": "3", "4": ""}
    hits = entities.rows[HITS]
    assert len(hits) == 5
    assert {row["WleId"]: row["GoldDecision"] for row in hits} == {"1": "1", "2": "0", "3": "2", "4": "3", "5": ""}


# ---- what the rows hold (docs/mapping.md section 8) --------------------------------------------------------------


def test_the_three_data_fabric_rows_hold_the_values_of_mapping_section_8(entities, monkeypatch):
    # own test: mapping 8.1-8.3, DEC-5
    monkeypatch.setenv("UIPATH_FOLDER_KEY", "folder-key-1")
    original = new_uuid()
    alert = screened(originalTransaction=original)
    hits = [hit(id="H-1"), hit(id="H-2", entityType=EntityType.LOCATION, name=NameEntity(fullName="Gill Bates"), goldDecision="0")]
    before = datetime.now(UTC) - timedelta(seconds=1)

    run(alert, hits, request_id="alice.csv")

    (transaction,) = entities.rows[TRANSACTIONS]
    assert {field: transaction[field] for field in transaction if field != "Id" and field != "StartTime"} == {
        "TransactionUuid": alert.uuid,
        "EndTime": None,
        "Status": "NEW",
        "StartBpUuid": RUN_ID,  # bp_run_id
        "BpStartTime": START,
        "ErrorMessage": None,
        "ErrorStep": None,
        "DwVariation": "folder-key-1",  # env UIPATH_FOLDER_KEY
        "DwVersion": version("evmig-nss"),  # the wheel's version (no literal: it changes with every library release)
        "ModelVersion": "nss-classification-model-v5.3.0",
        "ExtRecordId": "alice.csv",  # request_id
        "ClientId": "5",
        "OriginalTransactionUuid": None,  # the 3-argument startNewTransaction passes none, although the alert has one
    }
    assert before <= parse_utc(transaction["StartTime"]) <= datetime.now(UTC) + timedelta(seconds=1)

    (alert_row,) = entities.rows[ALERTS]
    assert {field: alert_row[field] for field in alert_row if field not in ("Id", "AlertUuid")} == {
        "TransactionUuid": alert.uuid, "AlertId": "A-1", "AlertCategory": "Sanctions", "AlertEntityType": "INDIVIDUAL",
        "AlertDwDecision": None, "AlertDwExplanation": None, "AlertMtDecision": None, "AlertMtExplanation": None,
        "WorkerFullName": None, "WorkerId": None, "HtmlReportLink": None, "CsvReportLink": None,
        "AutoQC": False, "Ticker": False, "GoldDecision": "1", "MtReviewStart": None, "MtReviewComplete": None,
        "ClientId": "5", "OriginalTransactionUuid": original,  # the alert row does carry it (mapping 8.2)
    }
    assert alert_row["AlertUuid"] != alert.uuid  # its own new uuid

    assert [{field: row[field] for field in ("TransactionUuid", "WleId", "WleCategory", "WleEntityType", "GoldDecision")}
            for row in entities.rows[HITS]] == [
        {"TransactionUuid": alert.uuid, "WleId": "H-1", "WleCategory": "Sanctions", "WleEntityType": "INDIVIDUAL", "GoldDecision": "1"},
        {"TransactionUuid": alert.uuid, "WleId": "H-2", "WleCategory": "Sanctions", "WleEntityType": "LOCATION", "GoldDecision": "0"},
    ]


def test_dw_variation_is_empty_text_without_a_folder_key(entities):
    # own test: DEC-5, Q4 (Evelyn's own fallback, J:utils/ExecutionUtils.java:62)
    run(screened(), [])
    assert entities.rows[TRANSACTIONS][0]["DwVariation"] == ""


def test_the_start_time_is_written_in_utc_whatever_offset_the_input_has(entities):
    # own test: the library's DATETIME_WITH_TZ rule (D-5); 09:15 at +02:00 is 07:15 UTC
    run(screened(), [], bp_start_time="2026-10-19T09:15:00.123+02:00")
    assert entities.rows[TRANSACTIONS][0]["BpStartTime"] == START


# ---- reruns, identical hit ids, an empty hit list ----------------------------------------------------------------


def test_a_rerun_overwrites_the_transaction_and_completes_the_hits_without_duplicates(entities):
    # own test: D-7, Q6, DEC-6 steps 1-3
    alert = screened()
    hits = [hit(id="H-1"), hit(id="H-2")]
    run(alert, hits)

    # Something moved the transaction on, and the last hit row is missing, as after a step that failed half way.
    entities.rows[TRANSACTIONS][0].update(Status="ERROR", ErrorMessage="boom", ErrorStep="csv-schema-producer", EndTime="2026-10-19T08:00:00.000Z")
    del entities.rows[HITS][-1]

    run(alert, hits, request_id="bob.csv", bp_run_id="second-run")

    (transaction,) = entities.rows[TRANSACTIONS]  # overwritten, not duplicated (Evelyn's JPA merge)
    assert (transaction["Status"], transaction["ErrorMessage"], transaction["ErrorStep"], transaction["EndTime"]) == ("NEW", None, None, None)
    assert (transaction["ExtRecordId"], transaction["StartBpUuid"]) == ("bob.csv", "second-run")
    assert len(entities.rows[ALERTS]) == 1  # written once, as Evelyn
    assert sorted(row["WleId"] for row in entities.rows[HITS]) == ["H-1", "H-2"]  # completed, not duplicated (Evelyn would duplicate)

    run(alert, hits)  # a third time changes nothing in the counts
    assert [len(entities.rows[key]) for key in (TRANSACTIONS, ALERTS, HITS)] == [1, 1, 2]


def test_identical_hit_ids_in_one_record_give_two_hit_rows(entities):
    # own test: mapping 8.3, IT:e2e/CsvProviderTest.java:233 "CSV: Identical hit ids"
    alert = screened()
    run(alert, [hit(id="H-1"), hit(id="H-1")])
    assert [row["WleId"] for row in entities.rows[HITS]] == ["H-1", "H-1"]

    # The rerun counts hit ids (a multiset): one H-1 is stored, so a list of two H-1 and one H-2 adds one H-1 and the H-2.
    run(alert, [hit(id="H-1"), hit(id="H-1"), hit(id="H-1"), hit(id="H-2")])
    assert sorted(row["WleId"] for row in entities.rows[HITS]) == ["H-1", "H-1", "H-1", "H-2"]


def test_an_empty_wle_list_is_allowed_and_gives_a_transaction_and_an_alert_row_only(entities):
    # own test: J:service/AnalyticsService.java:65 handles an empty list
    result = run(screened(), [])
    assert (result.wle_list, result.wle_count) == ([], 0)
    assert [len(entities.rows[key]) for key in (TRANSACTIONS, ALERTS, HITS)] == [1, 1, 0]


# ---- the output (claim 17) and the optional inputs ---------------------------------------------------------------


def test_the_output_has_the_six_fields_of_claim_17_as_plain_json(entities):
    # own test: J:task/csv/CsvSchemaProducerProcessor.java:56-61
    alert = screened()
    output = run(alert, [hit(id="H-1"), hit(id="H-2"), hit(id="H-3")]).model_dump()
    assert list(output) == ["transaction_id", "screened_data", "wle_list", "request_id", "wle_count", "is_internal_request"]
    assert output["transaction_id"] == alert.uuid
    assert (output["request_id"], output["wle_count"], output["is_internal_request"]) == ("alice.csv", 3, True)
    assert json.loads(json.dumps(output)) == output  # nothing but JSON values
    assert output["screened_data"]["clientId"] == "5"  # the Java field names, as Gson writes them (D-8)
    assert output["screened_data"]["name"] == {"fullName": "Alice Wonderland", **{k: None for k in ("firstName", "lastName", "middleName", "derived", "source")}}
    assert [wle["id"] for wle in output["wle_list"]] == ["H-1", "H-2", "H-3"]


@pytest.mark.parametrize("rest_request, expected", [
    pytest.param(None, True, id="null"),
    pytest.param("", True, id="empty-text"),
    pytest.param({}, True, id="empty-object"),
    pytest.param('{"id": 1}', False, id="text"),
    pytest.param({"id": 1}, False, id="object"),
])
def test_is_internal_request_is_true_unless_a_rest_request_came_with_the_record(entities, rest_request, expected):
    # own test: J:task/csv/CsvSchemaProducerProcessor.java:49 (containsKey); a Flow node sends null, "" or {} for an unset input
    assert run(screened(), [], rest_request=rest_request).is_internal_request is expected


def test_is_internal_request_is_true_when_the_key_is_absent(entities):
    # own test: the CSV flow never sets rest_request
    assert "rest_request" not in inputs(screened())
    assert main.main(main.ProducerIn.model_validate(inputs(screened()))).is_internal_request is True


@pytest.mark.parametrize("given", [{"request_id": None}, {"request_id": ""}, {}], ids=["null", "empty-text", "absent"])
def test_request_id_is_empty_text_when_absent(entities, given):
    # own test: J:task/csv/CsvSchemaProducerProcessor.java:48 .orElse(StringUtils.EMPTY)
    raw = inputs(screened(), [hit()])
    del raw["request_id"]
    raw.update(given)
    result = main.main(main.ProducerIn.model_validate(raw))
    assert result.request_id == ""
    assert entities.rows[TRANSACTIONS][0]["ExtRecordId"] == ""


def test_the_input_contract_for_the_flow():
    # own test: the Flow node of the main flow is wired to these names (docs/mapping.md section 10)
    fields = main.ProducerIn.model_fields
    assert set(fields) == {"screened_data", "wle_list", "bp_run_id", "bp_start_time", "request_id", "rest_request", "provider_id"}
    assert {name for name, field in fields.items() if field.is_required()} == {"screened_data", "wle_list", "bp_run_id", "bp_start_time"}


# ---- failures: Evelyn's step text, and nothing written -----------------------------------------------------------


@pytest.mark.parametrize("bp_run_id", ["", "   ", None], ids=["empty", "blank", "null"])
def test_a_blank_bp_run_id_fails_with_the_step_text(entities, bp_run_id):
    # own test: DEC-5, Q14
    with pytest.raises(NSSProcessingException) as error:
        run(screened(), [hit()], bp_run_id=bp_run_id)
    assert str(error.value).startswith(STEP + "bp_run_id is empty")
    assert entities.calls == []  # not a single Data Fabric call


@pytest.mark.parametrize("overrides, message", [
    pytest.param({"screened_data": None}, "Required input 'screened_data' is missing or empty", id="screened_data-null"),
    pytest.param({"screened_data": {}}, "Required input 'screened_data' is missing or empty", id="screened_data-empty"),
    pytest.param({"wle_list": None}, "Required input 'wle_list' is missing", id="wle_list-null"),
    pytest.param({"bp_start_time": None}, "bp_start_time is empty", id="bp_start_time-null"),
    pytest.param({"bp_start_time": ""}, "bp_start_time is empty", id="bp_start_time-empty"),
    pytest.param({"bp_start_time": "   "}, "bp_start_time is empty", id="bp_start_time-blank"),
    pytest.param({"bp_start_time": "yesterday"}, "Invalid isoformat string", id="bp_start_time-not-a-time"),
    pytest.param({"screened_data": {"id": "A-1"}}, "1 validation error for Transaction", id="screened_data-without-uuid"),
    pytest.param({"screened_data": {"uuid": "not-a-uuid"}}, "1 validation error for ScreenedData", id="screened_data-bad-uuid"),
], )
def test_a_missing_or_malformed_input_fails_with_the_step_text_before_anything_is_written(entities, overrides, message):
    # own test: Q14. Java: a missing value is a NullPointerException, a bad JSON a JsonSyntaxException, inside the step.
    with pytest.raises(NSSProcessingException) as error:
        run_raw(overrides)
    assert str(error.value).startswith(STEP + message)
    assert entities.calls == []


def test_a_wle_with_an_unknown_entity_type_fails_with_the_step_text(entities):
    # own test: Gson rejects a value that is not in the enum; so does the model
    with pytest.raises(NSSProcessingException) as error:
        run_raw({"wle_list": [{"id": "H-1", "entityType": "COMPANY"}]})
    assert str(error.value).startswith(STEP + "1 validation error for WleData")
    assert entities.calls == []


def test_a_refused_alert_row_fails_with_the_step_text_and_a_rerun_completes_the_rows(entities):
    # own test: D-6. DEC-6: "A failure after step 1 leaves a NEW transaction ... a rerun completes the rows"
    entities.reject = lambda key, row: "Insert data failed. Test refusal" if key == ALERTS else None
    alert, hits = screened(), [hit(id="H-1")]
    with pytest.raises(NSSProcessingException) as error:
        run(alert, hits)
    assert str(error.value) == STEP + "Insert data failed. Test refusal"
    assert [(row["Status"], len(entities.rows[ALERTS]), len(entities.rows[HITS])) for row in entities.rows[TRANSACTIONS]] == [("NEW", 0, 0)]

    entities.reject = None
    run(alert, hits)
    assert [len(entities.rows[key]) for key in (TRANSACTIONS, ALERTS, HITS)] == [1, 1, 1]


# ---- the vendored wheel (DEC-2, DEC-9) ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _vendored_wheel() -> Path:
    (wheel,) = (HERE / "wheels").glob("evmig_nss-*.whl")  # exactly one
    return wheel


def test_the_vendored_wheel_is_the_librarys_current_wheel():
    # own test: DEC-2. A library change that was not re-vendored (scripts/vendor_wheel.sh) fails here, not on the tenant.
    built = REPO / "evmig-nss" / "dist" / _vendored_wheel().name
    assert built.exists(), f"{built} is not built: the library moved on, vendor it again"
    assert _sha256(_vendored_wheel()) == _sha256(built)


def test_uv_lock_pins_the_vendored_wheel_and_uipath_2_14_27():
    # own test: DEC-2 (the tenant installs from uv.lock, which holds the wheel's sha256) and DEC-9
    packages = {package["name"]: package for package in tomllib.loads((HERE / "uv.lock").read_text())["package"]}
    wheel = _vendored_wheel()
    assert packages["evmig-nss"]["source"] == {"path": f"wheels/{wheel.name}"}
    assert packages["evmig-nss"]["wheels"][0]["hash"] == "sha256:" + _sha256(wheel)
    assert packages["uipath"]["version"] == "2.14.27"
