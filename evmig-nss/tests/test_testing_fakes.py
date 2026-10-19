# Own tests of the fakes in evmig_nss/testing.py: they must be as strict as the services they stand in for.
import json

import pytest

from evmig_nss import testing
from evmig_nss.testing import MISSING_BLOB_BODY, FakeBuckets, FakeEntities, local_sdk

TX = "EvMigTransaction-entity"


def test_fake_buckets_refuses_a_prefix_ending_in_slash_like_orchestrator():
    with pytest.raises(ValueError, match="HTTP 400"):
        FakeBuckets({"b/a.csv": "x"}).list_files(name="EvMigFiles", prefix="b/")


def test_fake_buckets_pages_with_a_continuation_token_and_filters_by_raw_prefix():
    fake = FakeBuckets({"b/a1": "x", "b/a2": "x", "b/a3": "x", "b/other": "x"}, page_size=2)
    first = fake.list_files(name="EvMigFiles", prefix="b/a")
    assert [i.full_path for i in first.items] == ["b/a1", "b/a2"] and first.continuation_token == "2"
    second = fake.list_files(name="EvMigFiles", prefix="b/a", continuation_token=first.continuation_token)
    assert [i.full_path for i in second.items] == ["b/a3"] and second.continuation_token is None


def test_fake_buckets_serves_a_folder_with_the_relative_path_as_key(tmp_path):
    (tmp_path / "doc-upload" / "csv" / "data").mkdir(parents=True)
    (tmp_path / "doc-upload" / "csv" / "data" / "a.csv").write_text("input_id\n1\n", encoding="utf-8")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "configuration_payload.json").write_text("{}", encoding="utf-8")
    fake = FakeBuckets(root=tmp_path)
    listed = fake.list_files(name="EvMigFiles", prefix="doc-upload")
    assert [i.full_path for i in listed.items] == ["doc-upload/csv/data/a.csv"]
    target = tmp_path / "downloaded"
    fake.download(name="EvMigFiles", blob_file_path="doc-upload/csv/data/a.csv", destination_path=str(target))
    assert target.read_text(encoding="utf-8") == "input_id\n1\n"


@pytest.mark.parametrize("mode", ["files", "root"])
def test_fake_buckets_download_of_a_missing_key_writes_an_error_body_and_does_not_raise_like_the_sdk(mode, tmp_path):
    # The real buckets.download writes whatever the storage answers (uipath/platform/orchestrator/_buckets_service.py:452-455).
    # Pinned so that nothing relies on the fake raising: BucketStore.read_bytes checks the listing first.
    if mode == "files":
        fake = FakeBuckets({"b/a.csv": "x"})
    else:
        (tmp_path / "b").mkdir()
        (tmp_path / "b" / "a.csv").write_text("x", encoding="utf-8")
        fake = FakeBuckets(root=tmp_path)
    target = tmp_path / "downloaded"
    fake.download(name="EvMigFiles", blob_file_path="b/missing.csv", destination_path=str(target))  # no exception
    body = target.read_bytes()
    assert body == MISSING_BLOB_BODY and b"<Code>BlobNotFound</Code>" in body
    assert fake.calls == [("download", "b/missing.csv")]
    fake.download(name="EvMigFiles", blob_file_path="b/a.csv", destination_path=str(target))  # a present key still downloads
    assert target.read_bytes() == b"x"


def test_fake_entities_gives_every_row_an_id_and_refuses_a_duplicate_uuid_and_an_unknown_field_and_an_unknown_entity():
    entities = FakeEntities()
    key = str(entities.retrieve_by_name("EvMigTransaction").id)
    record = entities.insert_record(key, {"TransactionUuid": "t1"})
    assert record.id and entities.rows[TX][0]["EndTime"] is None  # every field exists, empty
    with pytest.raises(RuntimeError, match="Value uniqueness violation"):
        entities.insert_record(key, {"TransactionUuid": "t1"})
    with pytest.raises(RuntimeError, match="Field not found"):
        entities.insert_record(key, {"TransactionUuid": "t2", "NoSuchField": 1})
    with pytest.raises(ValueError, match="does not exist"):
        entities.retrieve_by_name("EvMigNope")


@pytest.mark.parametrize(("entity", "unique"), [("EvMigAlertAnalytics", "AlertUuid"), ("EvMigHitAnalytics", "HitUuid")])
def test_fake_entities_keep_each_entitys_own_uuid_field_unique(entity, unique):
    entities = FakeEntities()
    key = f"{entity}-entity"
    entities.insert_record(key, {unique: "u1", "TransactionUuid": "t1"})
    entities.insert_record(key, {unique: "u2", "TransactionUuid": "t1"})  # the link field may repeat
    with pytest.raises(RuntimeError, match="Value uniqueness violation"):
        entities.insert_record(key, {unique: "u1", "TransactionUuid": "t2"})


@pytest.mark.parametrize("name", ["Uuid", "UUID", "uuid"])
def test_fake_entities_refuse_a_field_named_uuid_as_the_tenant_does(name, monkeypatch):
    # owner's tenant run, 2026-10-19: `uip df entities create` with a field "Uuid" was refused by the server
    monkeypatch.setitem(testing.ENTITY_FIELDS, "EvMigTransaction", {name, "Status"})
    with pytest.raises(ValueError, match=f"^Field name for '{name}' is a reserved SQL word and cannot be used as an entity or field name.$"):
        FakeEntities()


def test_fake_entities_update_stores_an_explicit_null():
    entities = FakeEntities()
    record = entities.insert_record(TX, {"TransactionUuid": "t1", "ErrorMessage": "x"})
    entities.update_record(TX, record.id, {"ErrorMessage": None})
    assert entities.rows[TX][0]["ErrorMessage"] is None


def test_fake_entities_persist_to_a_json_file_after_every_write_and_a_second_process_sees_the_rows(tmp_path):
    file = tmp_path / "df" / "rows.json"
    first = FakeEntities(path=file)
    first.insert_record(TX, {"TransactionUuid": "t1", "ExtRecordId": "a.csv"})
    assert json.loads(file.read_text(encoding="utf-8"))[TX][0]["ExtRecordId"] == "a.csv"

    second = FakeEntities(path=file)  # the next function's process
    assert second.rows[TX][0]["TransactionUuid"] == "t1"
    record = second.insert_record(TX, {"TransactionUuid": "t2"})
    assert record.id != second.rows[TX][0]["Id"]
    assert [r["TransactionUuid"] for r in FakeEntities(path=file).rows[TX]] == ["t1", "t2"]


def test_fake_entities_without_a_file_stay_in_memory():
    entities = FakeEntities()
    entities.insert_record(TX, {"TransactionUuid": "t1"})
    assert FakeEntities().rows[TX] == []


def test_local_sdk_has_buckets_and_entities(tmp_path):
    sdk = local_sdk(tmp_path, tmp_path / "rows.json")
    assert isinstance(sdk.buckets, FakeBuckets) and sdk.buckets.root == tmp_path
    assert isinstance(sdk.entities, FakeEntities) and sdk.entities.path == tmp_path / "rows.json"
