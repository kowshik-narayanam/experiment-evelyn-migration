# Ports TransactionServiceTest (names-screening-jnw .../nss/service/TransactionServiceTest.java), the startNewTransaction tests
# that reach the CSV path, and tests the upsert and the insert race of docs/decisions.md DEC-6 step 1.
import logging
from datetime import UTC, datetime
from importlib.metadata import version

import pytest

from evmig_nss.core.data_fabric_row import format_utc
from evmig_nss.core.repository import TransactionRepository
from evmig_nss.core.transaction import Transaction
from evmig_nss.service.transaction_service import RunContext, TransactionService
from evmig_nss.testing import FakeEntities

TX = "EvMigTransaction-entity"
RUN_ID = "6b3f0c1e-0d8a-4f6e-9a55-2f6a3c0f1b11"
RUN_START = datetime(2026, 10, 19, 7, 15, 0, 500000, tzinfo=UTC)
FIXED_NOW = datetime(2026, 10, 19, 7, 16, 0, tzinfo=UTC)


def service(entities, variation="123"):
    return TransactionService(TransactionRepository(entities), RunContext(RUN_ID, RUN_START, variation), clock=lambda: FIXED_NOW)


def test_should_start_transaction_with_uuid():  # ports TransactionServiceTest.java:98 shouldStartTransactionWithUuid
    entities = FakeEntities()
    uuid = "0b9a6b7e-3c1d-4b5a-8f24-5d1e7a9c0001"
    original_transaction_uuid = "0b9a6b7e-3c1d-4b5a-8f24-5d1e7a9c0002"

    returned = service(entities).start_new_transaction("1", uuid, "recordId", original_transaction_uuid)

    (row,) = entities.rows[TX]
    assert row["OriginalTransactionUuid"] == original_transaction_uuid
    assert row["StartBpUuid"] == RUN_ID  # Java: bpRunUuid
    assert row["BpStartTime"] == format_utc(RUN_START) == "2026-10-19T07:15:00.500Z"
    assert row["DwVariation"] == "123"
    assert row["StartTime"] == format_utc(FIXED_NOW)  # Java only asserts "not null"
    assert row["Status"] == "NEW"
    assert row["DwVersion"] == version("evmig-nss")  # Java mocks "3.2.0"; here the library's own version (DEC-5)
    assert row["ModelVersion"] == "nss-classification-model-v5.3.0"
    assert (row["TransactionUuid"], row["ClientId"], row["ExtRecordId"]) == (uuid, "1", "recordId")
    assert returned.TransactionUuid == uuid


def _assert_variation_is_empty_text_without_a_folder_key(monkeypatch):
    # Java's variation is "" when the task context is missing; here that is an unset UIPATH_FOLDER_KEY.
    monkeypatch.delenv("UIPATH_FOLDER_KEY", raising=False)
    entities = FakeEntities()
    context = RunContext.from_inputs(RUN_ID, format_utc(RUN_START))
    TransactionService(TransactionRepository(entities), context).start_new_transaction("1", "u1", "recordId")
    (row,) = entities.rows[TX]
    assert row["DwVariation"] == ""  # empty text, not null


def test_should_skip_variation_when_i_task_context_holder_is_null(monkeypatch):
    # ports TransactionServiceTest.java:122 shouldSkipVariationWhenITaskContextHolderIsNull
    _assert_variation_is_empty_text_without_a_folder_key(monkeypatch)


def test_should_skip_variation_when_task_input_context_is_null(monkeypatch):
    # ports TransactionServiceTest.java:134 shouldSkipVariationWhenTaskInputContextIsNull (the same case in Java too)
    _assert_variation_is_empty_text_without_a_folder_key(monkeypatch)


# ---- own tests ----


def test_the_variation_is_the_jobs_folder_key(monkeypatch):
    monkeypatch.setenv("UIPATH_FOLDER_KEY", "folder-key-1")
    assert RunContext.from_inputs(RUN_ID, "2026-10-19T07:15:00.500Z").dw_variation == "folder-key-1"


def test_the_run_context_reads_the_monitors_start_time_text_as_utc():
    assert RunContext.from_inputs(RUN_ID, "2026-10-19T07:15:00.500Z").bp_start_time == RUN_START


@pytest.mark.parametrize("run_id", ["", "  ", None])
def test_an_empty_run_id_is_refused(run_id):
    with pytest.raises(ValueError, match="bp_run_id is empty"):
        RunContext(run_id, RUN_START)


def test_the_three_argument_form_has_no_original_transaction_and_costs_one_find_and_one_insert():
    entities = FakeEntities()
    service(entities).start_new_transaction("7", "u1", "alice.csv")
    (row,) = entities.rows[TX]
    assert row["OriginalTransactionUuid"] is None and row["ClientId"] == "7" and row["ExtRecordId"] == "alice.csv"
    assert row["EndTime"] is None and row["ErrorMessage"] is None and row["ErrorStep"] is None
    assert entities.calls == ["retrieve_by_name", "retrieve_records", "insert_record"]


def test_a_second_call_with_the_same_uuid_overwrites_the_row_back_to_new():
    entities = FakeEntities()
    first = service(entities)
    first.start_new_transaction("1", "u1", "first.csv")
    row = entities.rows[TX][0]
    row.update({"Status": "ERROR", "EndTime": "2026-10-19T08:00:00.000Z", "ErrorMessage": "failed", "ErrorStep": "model"})  # a later step failed it

    TransactionService(TransactionRepository(entities), RunContext("other-run", RUN_START, "v"), clock=lambda: FIXED_NOW).start_new_transaction("1", "u1", "second.csv")

    (after,) = entities.rows[TX]
    assert after["Id"] == row["Id"]
    assert (after["Status"], after["EndTime"], after["ErrorMessage"], after["ErrorStep"]) == ("NEW", None, None, None)
    assert (after["ExtRecordId"], after["StartBpUuid"], after["DwVariation"]) == ("second.csv", "other-run", "v")


def test_when_another_producer_wins_the_insert_the_loser_logs_and_returns_its_own_unsaved_row(caplog):
    entities = FakeEntities()

    def other_producer_wins(key, row):
        entities.before_insert = None
        entities.rows[key].append({"Id": "winner", **Transaction(TransactionUuid="u1", ExtRecordId="winner.csv", Status="NEW").to_record()})

    entities.before_insert = other_producer_wins
    with caplog.at_level(logging.WARNING):
        returned = service(entities).start_new_transaction("1", "u1", "loser.csv")

    assert caplog.messages == ["transaction 'u1' already exist"]  # J:service/TransactionService.java:76
    assert returned.TransactionUuid == "u1" and returned.ExtRecordId == "loser.csv"
    assert [row["ExtRecordId"] for row in entities.rows[TX]] == ["winner.csv"]  # the stored row is the winner's


def test_any_other_failure_of_the_write_is_raised():
    entities = FakeEntities()
    entities.reject = lambda key, row: "Data Fabric is down"
    with pytest.raises(RuntimeError, match="Data Fabric is down"):
        service(entities).start_new_transaction("1", "u1", "a.csv")
