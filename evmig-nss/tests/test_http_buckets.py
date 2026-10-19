# Own test: BucketStore over the REAL uipath SDK `BucketsService`, with the HTTP calls answered by httpx.MockTransport.
# It pins why BucketStore.read_bytes looks the key up in a listing before it downloads:
# buckets.download writes the body of the read URI without checking the status
# (uipath/platform/orchestrator/_buckets_service.py:452-455, uipath 2.14).
# It reaches into two SDK internals, `_client` (the Orchestrator calls) and `custom_client` (the storage call); if a uipath
# upgrade renames them this file fails at once, which is the point of keeping it.
import httpx
import pytest
from uipath.platform.common._config import UiPathApiConfig
from uipath.platform.common._execution_context import UiPathExecutionContext
from uipath.platform.orchestrator._buckets_service import BucketsService

from evmig_nss.core import configuration
from evmig_nss.core.bucket_store import BucketStore
from evmig_nss.testing import MISSING_BLOB_BODY

BLOBS = {"config/configuration_payload.json": b'{"provider": {"FORMAT_FILE_LOCATION": "d/f.csv"}}', "d/a.csv": b"input_id\n1\n"}


class Tenant:
    """Orchestrator (buckets, ListFiles, GetReadUri) and the blob storage behind it, as MockTransport handlers."""

    def __init__(self, blobs):
        self.blobs = dict(blobs)
        self.orchestrator_calls: list[str] = []
        self.storage_calls: list[str] = []

    def orchestrator(self, request: httpx.Request) -> httpx.Response:
        path, query = request.url.path, dict(request.url.params)
        self.orchestrator_calls.append(path.split("orchestrator_")[-1].split("?")[0])
        if path.endswith("/odata/Buckets"):
            bucket = {"Name": "EvMigFiles", "Id": 7, "Identifier": "bucket-key", "StorageProvider": None, "StorageContainer": None}
            return httpx.Response(200, json={"value": [bucket]})
        if "ListFiles" in path:
            items = [{"fullPath": "/" + k, "size": len(v), "isDirectory": False} for k, v in self.blobs.items() if k.startswith(query.get("prefix", ""))]
            return httpx.Response(200, json={"items": items, "continuationToken": None})
        if "GetReadUri" in path:
            # Inference: Orchestrator answers with a pre-signed URI without checking that the blob exists.
            return httpx.Response(200, json={"Uri": "https://blob.example/" + query["path"], "RequiresAuth": False, "Headers": {"Keys": [], "Values": []}})
        return httpx.Response(404, json={})

    def storage(self, request: httpx.Request) -> httpx.Response:
        key = request.url.path.lstrip("/")
        self.storage_calls.append(key)
        if key in self.blobs:
            return httpx.Response(200, content=self.blobs[key])
        return httpx.Response(404, content=MISSING_BLOB_BODY)  # Inference: the body depends on the storage


def real_buckets(tenant: Tenant) -> BucketsService:
    service = BucketsService(UiPathApiConfig(base_url="https://cloud.uipath.com/org/tenant", secret="not-a-secret"), UiPathExecutionContext())
    service._client = httpx.Client(transport=httpx.MockTransport(tenant.orchestrator), base_url="https://cloud.uipath.com")
    service.custom_client = httpx.Client(transport=httpx.MockTransport(tenant.storage))
    return service


def test_the_sdks_own_download_of_a_missing_blob_returns_the_error_body_without_raising(tmp_path):
    tenant = Tenant(BLOBS)
    target = tmp_path / "blob"
    real_buckets(tenant).download(name="EvMigFiles", blob_file_path="d/missing.csv", destination_path=str(target))  # no exception
    assert target.read_bytes() == MISSING_BLOB_BODY


def test_the_store_reads_an_existing_file_through_the_real_sdk():
    tenant = Tenant(BLOBS)
    store = BucketStore(real_buckets(tenant))
    assert store.read_bytes("d/a.csv") == b"input_id\n1\n"
    assert store.list_keys("d/") == ["d/a.csv"]


def test_the_store_raises_for_a_missing_file_and_never_asks_for_its_read_uri():
    tenant = Tenant(BLOBS)
    store = BucketStore(real_buckets(tenant))
    with pytest.raises(FileNotFoundError, match="^Please provide correct path to file: d/missing.csv$"):
        store.read_bytes("d/missing.csv")
    with pytest.raises(FileNotFoundError):
        store.read_csv_text("d/missing.csv")
    assert tenant.storage_calls == []
    assert not any("GetReadUri" in call for call in tenant.orchestrator_calls)


def test_a_missing_configuration_file_fails_the_job_through_the_real_sdk():
    tenant = Tenant({"d/a.csv": b"input_id\n1\n"})  # no config/configuration_payload.json
    with pytest.raises(FileNotFoundError, match="config/configuration_payload.json"):
        configuration.load_configuration(BucketStore(real_buckets(tenant)))
