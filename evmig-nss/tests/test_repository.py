# Own tests of core/repository.py (the Spring Data repositories of Evelyn, over Data Fabric, DEC-6) with FakeEntities.
import pytest

from evmig_nss.core.analytics import ALERT_ENTITY_NAME, AlertAnalytics, HitAnalytics
from evmig_nss.core.repository import (
    AlertAnalyticsRepository,
    DataFabricError,
    DataIntegrityViolationError,
    HitAnalyticsRepository,
    TransactionRepository,
)
from evmig_nss.core.transaction import Transaction, TransactionStatus
from evmig_nss.testing import FakeEntities

TX = "EvMigTransaction-entity"
HIT = "EvMigHitAnalytics-entity"


def hit_row(transaction_uuid, wle_id):
    return HitAnalytics(TransactionUuid=transaction_uuid, WleId=wle_id).to_record()


def test_the_entity_is_found_by_name_once_per_store_and_each_entity_has_its_own_key():
    entities = FakeEntities()
    transactions = TransactionRepository(entities)
    alerts = AlertAnalyticsRepository(entities)
    transactions.find_by_uuid("u1")
    transactions.find_by_uuid("u2")
    alerts.find_by_transaction_uuid("u1")
    assert entities.calls == ["retrieve_by_name", "retrieve_records", "retrieve_records", "retrieve_by_name", "retrieve_records"]
    assert transactions.key == TX and alerts.key == "EvMigAlertAnalytics-entity"
    assert alerts.entity_name == ALERT_ENTITY_NAME


def test_a_find_returns_only_the_rows_that_match_the_field_and_every_page_of_them():
    entities = FakeEntities(page_limit=2)
    hits = HitAnalyticsRepository(entities, page_size=2)
    for n in range(5):
        hits.insert(hit_row("t1", f"W{n}"))
    hits.insert(hit_row("t2", "other"))
    entities.calls.clear()

    found = hits.find_by_transaction_uuid("t1")

    assert [row["WleId"] for row in found] == ["W0", "W1", "W2", "W3", "W4"]
    assert all("Id" in row for row in found)
    assert entities.calls == ["retrieve_records"] * 3  # 2 + 2 + 1 rows; the key was already known


def test_a_find_with_no_match_is_an_empty_list_after_one_call():
    entities = FakeEntities()
    assert HitAnalyticsRepository(entities).find_by_transaction_uuid("nobody") == []
    assert entities.calls == ["retrieve_by_name", "retrieve_records"]


def test_a_page_larger_than_data_fabric_allows_is_what_the_fake_refuses():
    with pytest.raises(ValueError, match="at most 2 records"):
        HitAnalyticsRepository(FakeEntities(page_limit=2), page_size=3).find_by_transaction_uuid("t")


def test_insert_batch_is_one_call_and_returns_the_rows_with_their_ids():
    entities = FakeEntities()
    hits = HitAnalyticsRepository(entities)
    rows = hits.insert_batch([hit_row("t1", "A"), hit_row("t1", "B")])
    assert [row["WleId"] for row in rows] == ["A", "B"] and all(row["Id"] for row in rows)
    assert entities.calls == ["retrieve_by_name", "insert_records"]


def test_one_refused_row_of_a_batch_raises_with_the_reason_and_the_other_rows_stay_written():
    entities = FakeEntities()
    entities.reject = lambda key, row: "boom" if row["WleId"] == "BAD" else None
    hits = HitAnalyticsRepository(entities)
    with pytest.raises(DataFabricError, match=r"EvMigHitAnalytics: 1 of 3 rows were refused: boom"):
        hits.insert_batch([hit_row("t1", "A"), hit_row("t1", "BAD"), hit_row("t1", "C")])
    assert [row["WleId"] for row in entities.rows[HIT]] == ["A", "C"]  # no rollback (D-6)


def test_a_batch_that_writes_fewer_rows_than_were_sent_without_reporting_a_refusal_raises():
    # The SDK answers with success and failure lists; a row in neither would be lost silently (not an assert: python -O strips those).
    entities = FakeEntities()
    real_insert_records = entities.insert_records

    def drops_a_row(entity_key, records, **options):
        response = real_insert_records(entity_key, records[:-1], **options)
        return response  # one row never reached Data Fabric and is not in failure_records

    entities.insert_records = drops_a_row
    hits = HitAnalyticsRepository(entities)
    with pytest.raises(DataFabricError, match=r"EvMigHitAnalytics: 3 rows were sent, 2 were written and none was reported refused"):
        hits.insert_batch([hit_row("t1", "A"), hit_row("t1", "B"), hit_row("t1", "C")])


def test_a_duplicate_uuid_in_a_batch_is_a_refused_row_too():
    entities = FakeEntities()
    hits = HitAnalyticsRepository(entities)
    row = hit_row("t1", "A")
    hits.insert_batch([row])
    with pytest.raises(DataFabricError, match="Value uniqueness violation"):
        hits.insert_batch([row])


def test_save_inserts_a_new_transaction_after_one_find():
    entities = FakeEntities()
    transactions = TransactionRepository(entities)
    transactions.save(Transaction(TransactionUuid="t1", Status=TransactionStatus.NEW, ClientId="9"))
    assert entities.calls == ["retrieve_by_name", "retrieve_records", "insert_record"]
    (row,) = entities.rows[TX]
    assert row["TransactionUuid"] == "t1" and row["Status"] == "NEW" and row["ClientId"] == "9"


def test_save_of_a_known_uuid_updates_every_field_and_sends_absent_values_as_explicit_nulls():
    entities = FakeEntities()
    transactions = TransactionRepository(entities)
    transactions.save(Transaction(TransactionUuid="t1", Status=TransactionStatus.COMPLETED, ErrorMessage="old error", ErrorStep="csv-task", ExtRecordId="old.csv"))
    (before,) = entities.rows[TX]

    transactions.save(Transaction(TransactionUuid="t1", Status=TransactionStatus.NEW, ExtRecordId="new.csv"))

    (after,) = entities.rows[TX]  # still one row, same Id
    assert after["Id"] == before["Id"]
    assert after["Status"] == "NEW" and after["ExtRecordId"] == "new.csv"
    assert after["ErrorMessage"] is None and after["ErrorStep"] is None  # cleared by explicit null, not left as it was
    assert entities.calls[-2:] == ["retrieve_records", "update_record"]  # one find, one write


def test_an_insert_that_loses_a_race_is_a_data_integrity_violation_and_leaves_the_winners_row():
    entities = FakeEntities()
    transactions = TransactionRepository(entities)

    def other_producer_wins(key, row):  # runs after our find found nothing and before our insert
        entities.before_insert = None
        entities.rows[key].append({"Id": "winner", **Transaction(TransactionUuid="t1", ExtRecordId="winner.csv").to_record()})

    entities.before_insert = other_producer_wins
    with pytest.raises(DataIntegrityViolationError, match="transaction 't1' already exist"):
        transactions.save(Transaction(TransactionUuid="t1", ExtRecordId="loser.csv"))
    assert [row["ExtRecordId"] for row in entities.rows[TX]] == ["winner.csv"]


def test_an_insert_that_fails_for_another_reason_raises_as_it_is():
    entities = FakeEntities()
    entities.reject = lambda key, row: "Data Fabric is down"
    with pytest.raises(RuntimeError, match="Data Fabric is down"):
        TransactionRepository(entities).save(Transaction(TransactionUuid="t1"))
    assert entities.rows[TX] == []


def test_rows_use_the_data_fabric_field_names_and_the_fake_refuses_an_unknown_one():
    entities = FakeEntities()
    alerts = AlertAnalyticsRepository(entities)
    with pytest.raises(RuntimeError, match="Field not found: \\['alert_id'\\]"):
        alerts.insert({"AlertUuid": "a1", "alert_id": "snake case is not a Data Fabric name"})
    alerts.insert(AlertAnalytics(TransactionUuid="t1", AlertId="A1").to_record())
    assert entities.rows["EvMigAlertAnalytics-entity"][0]["AlertId"] == "A1"
