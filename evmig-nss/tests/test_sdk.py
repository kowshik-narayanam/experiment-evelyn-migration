# Own tests of core/sdk.py: the one switch between the real SDK and a local run without a tenant.
import sys
import types
from types import SimpleNamespace

from evmig_nss.core import sdk
from evmig_nss.core.bucket_store import BucketStore
from evmig_nss.core.repository import TransactionRepository
from evmig_nss.core.transaction import Transaction
from evmig_nss.testing import FakeBuckets, FakeEntities


def fake_uipath_module(monkeypatch):
    """Put a stand-in for `uipath.platform` in place, so the test can see UiPath() being created without a login."""
    created = []

    class UiPath:
        def __init__(self):
            created.append(self)

    module = types.ModuleType("uipath.platform")
    module.UiPath = UiPath
    monkeypatch.setitem(sys.modules, "uipath.platform", module)
    return created


def test_without_the_environment_the_real_client_is_created_on_first_use_only_and_once(monkeypatch):
    created = fake_uipath_module(monkeypatch)
    assert created == []  # nothing at import time or before the first call
    first = sdk.get_sdk()
    assert sdk.get_sdk() is first and len(created) == 1


def test_a_test_replaces_the_sdk_with_set_sdk_and_clears_it_with_none(monkeypatch):
    created = fake_uipath_module(monkeypatch)
    mine = SimpleNamespace(buckets=FakeBuckets(), entities=FakeEntities())
    sdk.set_sdk(mine)
    assert sdk.get_sdk() is mine and created == []  # UiPath() is never created
    sdk.set_sdk(None)
    assert sdk.get_sdk() is created[0]


def test_with_a_local_bucket_dir_the_sdk_is_local_and_uipath_is_never_imported(monkeypatch, tmp_path):
    created = fake_uipath_module(monkeypatch)
    monkeypatch.setenv(sdk.LOCAL_BUCKET_DIR_ENV, str(tmp_path))
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "configuration_payload.json").write_text('{"a": 1}', encoding="utf-8")

    local = sdk.get_sdk()

    assert created == [] and sdk.get_sdk() is local
    assert BucketStore(local.buckets).read_text("config/configuration_payload.json") == '{"a": 1}'  # the store's own code path
    assert local.entities.path is None  # no file named: rows stay in memory


def test_rows_written_in_one_process_are_read_in_the_next_through_the_named_file(monkeypatch, tmp_path):
    monkeypatch.setenv(sdk.LOCAL_BUCKET_DIR_ENV, str(tmp_path))
    monkeypatch.setenv(sdk.LOCAL_DATAFABRIC_FILE_ENV, str(tmp_path / "out" / "datafabric.json"))

    TransactionRepository(sdk.get_sdk().entities).save(Transaction(TransactionUuid="t1", ExtRecordId="a.csv"))

    sdk.set_sdk(None)  # "a new process": the SDK is created again from the environment
    found = TransactionRepository(sdk.get_sdk().entities).find_by_uuid("t1")
    assert found["ExtRecordId"] == "a.csv"
