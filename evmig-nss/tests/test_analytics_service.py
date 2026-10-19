# Ports AnalyticsServiceTest (names-screening-jnw .../nss/service/AnalyticsServiceTest.java), the test that reaches the
# CSV path, and tests initFullAnalytics with docs/decisions.md DEC-6 steps 2 and 3. The other eleven Java tests are
# updateCsvReportLink (reports), not on this path.
import pytest

from evmig_nss.core.repository import AlertAnalyticsRepository, DataFabricError, HitAnalyticsRepository
from evmig_nss.core.transaction import Transaction
from evmig_nss.schema.models import EntityType, ScreenedData, WleData
from evmig_nss.service.analytics_service import AnalyticsService
from evmig_nss.testing import FakeEntities

ALERT = "EvMigAlertAnalytics-entity"
HIT = "EvMigHitAnalytics-entity"
TX_UUID = "11111111-2222-4333-8444-555555555555"


def make(entities=None):
    entities = entities or FakeEntities()
    return AnalyticsService(AlertAnalyticsRepository(entities), HitAnalyticsRepository(entities)), entities


def wle(wle_id, category=None, entity_type=None, gold=None):
    return WleData(id=wle_id, category=category, entityType=entity_type, goldDecision=gold)


def test_should_save_original_transaction_in_alert_analytics():  # ports AnalyticsServiceTest.java:58 shouldSaveOriginalTransactionInAlertAnalytics
    analytics, entities = make()
    transaction = Transaction(TransactionUuid=TX_UUID)
    original_transaction = "99999999-2222-4333-8444-555555555555"
    screened_data = ScreenedData(id="1", clientId="1", originalTransaction=original_transaction)

    analytics.init_alert_analytics(transaction, screened_data)

    (row,) = entities.rows[ALERT]
    assert row["TransactionUuid"] == TX_UUID
    assert row["OriginalTransactionUuid"] == original_transaction


# ---- own tests ----


def test_the_alert_row_takes_its_values_from_the_screened_data_and_leaves_the_rest_empty():
    analytics, entities = make()
    screened = ScreenedData(id="A-1", clientId="42", category="PEP", entityType=EntityType.ORGANIZATION, goldDecision="FP")
    analytics.init_alert_analytics(Transaction(TransactionUuid=TX_UUID), screened)
    (row,) = entities.rows[ALERT]
    assert row["TransactionUuid"] == TX_UUID
    assert (row["AlertId"], row["ClientId"], row["AlertCategory"], row["AlertEntityType"], row["GoldDecision"]) == ("A-1", "42", "PEP", "ORGANIZATION", "FP")
    assert row["OriginalTransactionUuid"] is None
    assert row["AutoQC"] is False and row["Ticker"] is False
    assert all(row[f] is None for f in ["AlertDwDecision", "AlertMtDecision", "WorkerId", "HtmlReportLink", "CsvReportLink", "MtReviewStart"])
    assert len(row["AlertUuid"]) == 36


def test_an_alert_without_entity_type_has_a_null_type():
    analytics, entities = make()
    analytics.init_alert_analytics(Transaction(TransactionUuid=TX_UUID), ScreenedData(id="A"))
    assert entities.rows[ALERT][0]["AlertEntityType"] is None


def test_the_alert_row_is_written_once_per_transaction():
    analytics, entities = make()
    transaction = Transaction(TransactionUuid=TX_UUID)
    analytics.init_alert_analytics(transaction, ScreenedData(id="A"))
    analytics.init_alert_analytics(transaction, ScreenedData(id="A changed"))
    analytics.init_alert_analytics(Transaction(TransactionUuid="another"), ScreenedData(id="B"))
    assert [(r["TransactionUuid"], r["AlertId"]) for r in entities.rows[ALERT]] == [(TX_UUID, "A"), ("another", "B")]


def test_hits_are_one_row_per_wle_in_one_batch_call():
    analytics, entities = make()
    analytics.init_hits_analytics(TX_UUID, [wle("W1", "Sanctions", EntityType.INDIVIDUAL, "TP"), wle("W2", None, EntityType.LOCATION), wle("W3")])
    rows = entities.rows[HIT]
    assert [r["WleId"] for r in rows] == ["W1", "W2", "W3"]
    assert [r["TransactionUuid"] for r in rows] == [TX_UUID] * 3
    assert (rows[0]["WleCategory"], rows[0]["WleEntityType"], rows[0]["GoldDecision"]) == ("Sanctions", "INDIVIDUAL", "TP")
    assert rows[1]["WleEntityType"] == "LOCATION" and rows[2]["WleEntityType"] is None
    assert rows[0]["NameMatchingScore"] is None and rows[0]["WleDwDecision"] is None
    assert len({r["HitUuid"] for r in rows}) == 3
    assert entities.calls.count("insert_records") == 1 and "insert_record" not in entities.calls


def test_no_wles_means_no_call_at_all():
    analytics, entities = make()
    analytics.init_hits_analytics(TX_UUID, None)
    analytics.init_hits_analytics(TX_UUID, [])
    assert entities.calls == []


def test_a_rerun_does_not_duplicate_hits_and_a_partly_stored_transaction_is_completed():
    analytics, entities = make()
    analytics.init_hits_analytics(TX_UUID, [wle("W1")])  # the first run got this far
    analytics.init_hits_analytics(TX_UUID, [wle("W1"), wle("W2")])  # the rerun has both
    analytics.init_hits_analytics(TX_UUID, [wle("W1"), wle("W2")])  # and again
    assert [r["WleId"] for r in entities.rows[HIT]] == ["W1", "W2"]


def test_identical_hit_ids_are_counted_as_a_multiset():
    # docs/mapping.md 8.3: a CSV may hold the same hit id twice, and Evelyn writes both rows.
    analytics, entities = make()
    analytics.init_hits_analytics(TX_UUID, [wle("H"), wle("H"), wle("X")])
    assert sorted(r["WleId"] for r in entities.rows[HIT]) == ["H", "H", "X"]
    analytics.init_hits_analytics(TX_UUID, [wle("H"), wle("H"), wle("X")])  # rerun: nothing new
    assert len(entities.rows[HIT]) == 3
    analytics.init_hits_analytics(TX_UUID, [wle("H"), wle("H"), wle("H"), wle("X")])  # a third H appears: only it is written
    assert sorted(r["WleId"] for r in entities.rows[HIT]) == ["H", "H", "H", "X"]


def test_hits_of_another_transaction_do_not_count():
    analytics, entities = make()
    analytics.init_hits_analytics("other-transaction", [wle("W1")])
    analytics.init_hits_analytics(TX_UUID, [wle("W1")])
    assert [(r["TransactionUuid"], r["WleId"]) for r in entities.rows[HIT]] == [("other-transaction", "W1"), (TX_UUID, "W1")]


def test_a_stored_hit_row_without_a_wle_id_does_not_break_the_rerun_check():
    analytics, entities = make()
    entities.rows[HIT].append({"Id": "00000000-0000-0000-0000-00000000000a", "HitUuid": "u1", "TransactionUuid": TX_UUID})  # no WleId key
    analytics.init_hits_analytics(TX_UUID, [wle("W1")])  # row["WleId"] would raise KeyError here
    assert [r.get("WleId") for r in entities.rows[HIT]] == [None, "W1"]


def test_a_refused_hit_row_raises():
    analytics, entities = make()
    entities.reject = lambda key, row: "refused" if row["WleId"] == "BAD" else None
    with pytest.raises(DataFabricError, match="1 of 2 rows were refused"):
        analytics.init_hits_analytics(TX_UUID, [wle("W1"), wle("BAD")])


def test_init_full_analytics_writes_the_alert_then_the_hits_and_costs_the_calls_of_decision_6():
    analytics, entities = make()
    analytics.init_full_analytics(Transaction(TransactionUuid=TX_UUID), ScreenedData(id="A"), [wle("W1"), wle("W2")])
    assert len(entities.rows[ALERT]) == 1 and len(entities.rows[HIT]) == 2
    assert entities.calls == [
        "retrieve_by_name", "retrieve_records", "insert_record",  # alert: lookup, find, insert
        "retrieve_by_name", "retrieve_records", "insert_records",  # hits: lookup, find, one batch
    ]  # fmt: skip


def test_init_full_analytics_with_no_wle_list_writes_only_the_alert():
    analytics, entities = make()
    analytics.init_full_analytics(Transaction(TransactionUuid=TX_UUID), ScreenedData(id="A"), None)
    assert len(entities.rows[ALERT]) == 1 and entities.rows[HIT] == []
