"""In-memory stand-ins for `sdk.buckets` and `sdk.entities`, shipped in the wheel.

The three functions' tests reuse them, and so does a local run without a tenant (core/sdk.py): one implementation.
Neither fake logs in or touches the network. They are strict where that catches a regression, not everywhere the real
services are: FakeBuckets refuses a list prefix ending in "/" and pages its answers, and, like the SDK, writes an error
body instead of raising when a file is missing (MISSING_BLOB_BODY). FakeEntities refuses a duplicate Uuid, a page larger
than Data Fabric's 1,000 and an unknown field. The last one is STRICTER than the tenant, which drops an unknown field
silently (owner's review, 2026-10-19), so a misnamed field would pass on the tenant and be lost; the fake's refusal
only helps for fields the models send. What guards the names is tests/test_entity_files.py, which compares each row
model's fields with EvMigEvelyn/entities/*.create.json.
"""
import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import httpx
from uipath.platform.common.paging import PagedResult
from uipath.platform.entities.entities import (
    EntityRecord,
    EntityRecordsBatchResponse,
    FailureRecord,
    QueryFilterOperator,
    RetrieveEntityRecordsResponse,
)
from uipath.platform.errors import EnrichedException
from uipath.platform.orchestrator.buckets import BucketFile

from evmig_nss.core.analytics import ALERT_ENTITY_NAME, HIT_ENTITY_NAME, AlertAnalytics, HitAnalytics
from evmig_nss.core.constants import BUCKET_NAME
from evmig_nss.core.transaction import ENTITY_NAME as TRANSACTION_ENTITY_NAME
from evmig_nss.core.transaction import Transaction

# What a missing blob downloads as: the storage's XML error body. Inference: the exact body depends on the storage
# behind the bucket (Azure Blob's BlobNotFound shown here); the SDK's own download writes whatever body it gets.
MISSING_BLOB_BODY = (
    b'<?xml version="1.0" encoding="utf-8"?><Error><Code>BlobNotFound</Code>'
    b"<Message>The specified blob does not exist.</Message></Error>"
)

# The three entities and their field names (docs/mapping.md section 8).
ENTITY_FIELDS = {
    TRANSACTION_ENTITY_NAME: set(Transaction.model_fields),
    ALERT_ENTITY_NAME: set(AlertAnalytics.model_fields),
    HIT_ENTITY_NAME: set(HitAnalytics.model_fields),
}


def sdk_http_error(status_code: int = 403, url: str = "https://cloud.uipath.com/org/tenant/orchestrator_/odata/Buckets") -> EnrichedException:
    """The error the real SDK raises for an HTTP error status, to put in FakeBuckets.fail_listing_with."""
    request = httpx.Request("GET", url)
    response = httpx.Response(status_code, request=request, content=b"denied")
    return EnrichedException(httpx.HTTPStatusError(f"HTTP {status_code}", request=request, response=response))


class FakeBuckets:
    """Stands in for sdk.buckets: list_files and download of one bucket.

    Files come from `files` ({key: text or bytes}, keys are whole paths such as "doc-upload/csv/a.csv") or, when `root`
    is given, from the files under that folder (the key is the path relative to it). Listing order is the insertion
    order, not sorted, so the store's own sorting is tested.
    Set `fail_listing_with` to an exception (sdk_http_error(), httpx.ConnectError(...), ...) and list_files raises it.
    """

    def __init__(
        self,
        files: dict[str, str | bytes] | None = None,
        *,
        name: str = BUCKET_NAME,
        root: str | Path | None = None,
        page_size: int = 500,
        leading_slash: bool = False,
    ):
        self.name = name
        self.files = dict(files or {})
        self.root = None if root is None else Path(root)
        self.page_size = page_size
        self.leading_slash = leading_slash  # staging returns "/a/b.csv", other tenants "a/b.csv"
        self.fail_listing_with: Exception | None = None
        self.calls: list[tuple] = []

    def _keys(self) -> list[str]:
        if self.root is None:
            return list(self.files)
        return [path.relative_to(self.root).as_posix() for path in self.root.rglob("*") if path.is_file()]

    def _check_bucket(self, name):
        if name != self.name:
            raise LookupError(f"Bucket with name '{name}' not found")  # the text and type of the SDK's buckets.retrieve

    def list_files(self, *, name=None, key=None, prefix="", take_hint=500, continuation_token=None, folder_key=None, folder_path=None):
        self.calls.append(("list_files", prefix, continuation_token))
        if self.fail_listing_with is not None:
            raise self.fail_listing_with
        self._check_bucket(name)
        if prefix.endswith("/"):
            raise ValueError("HTTP 400: Orchestrator refuses a ListFiles prefix that ends in '/'")
        matching = [key for key in self._keys() if key.startswith(prefix)]
        start = int(continuation_token or 0)
        page = matching[start : start + self.page_size]
        token = str(start + self.page_size) if start + self.page_size < len(matching) else None
        items = [
            BucketFile(fullPath=("/" if self.leading_slash else "") + key, size=0, isDirectory=False) for key in page
        ]
        return PagedResult(items=items, continuation_token=token, has_more=token is not None)

    def download(self, *, name=None, key=None, blob_file_path, destination_path, folder_key=None, folder_path=None):
        """Writes the file to `destination_path`. For a missing key it behaves like the real SDK: it does not raise, it
        writes an error body (MISSING_BLOB_BODY) as the file. buckets.download fetches the read URI and writes `.content`
        without checking the status (uipath/platform/orchestrator/_buckets_service.py:452-455). Inference: the exact body
        depends on the storage; BucketStore.read_bytes checks the key in a listing so it never relies on it."""
        self.calls.append(("download", blob_file_path))
        self._check_bucket(name)
        if self.root is not None:
            path = self.root / blob_file_path
            content = path.read_bytes() if path.is_file() else MISSING_BLOB_BODY
        else:
            content = self.files.get(blob_file_path, MISSING_BLOB_BODY)
        Path(destination_path).write_bytes(content.encode("utf-8") if isinstance(content, str) else content)


class FakeEntities:
    """Stands in for sdk.entities: the three EvMig entities, the calls the store makes, Data Fabric's refusals.

    `rows` is {entity key: [row dicts]}. With `path`, the rows are loaded from that JSON file at start and written back
    after every write, so separate processes (the three functions of a local run) share them.
    Test hooks: `before_insert(key, row)` runs before every insert (a test can write a competing row there to stage
    a race), `reject(key, row)` returns an error text to refuse a row, or None.
    """

    def __init__(self, path: str | Path | None = None, page_limit: int = 1000):
        self.path = None if path is None else Path(path)
        self.page_limit = page_limit  # Data Fabric answers at most 1,000 rows per query
        self.rows: dict[str, list[dict]] = {f"{name}-entity": [] for name in ENTITY_FIELDS}
        self.calls: list[str] = []
        self.before_insert: Callable[[str, dict], None] | None = None
        self.reject: Callable[[str, dict], str | None] | None = None
        if self.path is not None and self.path.exists():
            self.rows = json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self):
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.rows, indent=2), encoding="utf-8")

    def _name(self, key: str) -> str:
        return key.removesuffix("-entity")

    def retrieve_by_name(self, name, folder_key=None):
        self.calls.append("retrieve_by_name")
        if name not in ENTITY_FIELDS:
            raise ValueError(f"Entity '{name}' does not exist")
        return SimpleNamespace(id=f"{name}-entity")

    def _new_id(self) -> str:
        return f"00000000-0000-0000-0000-{sum(len(rows) for rows in self.rows.values()) + 1:012d}"

    def _refusal(self, key: str, data: dict) -> str | None:
        unknown = set(data) - ENTITY_FIELDS[self._name(key)] - {"Id"}
        if unknown:
            return f"Field not found: {sorted(unknown)}"
        if self.reject is not None and (error := self.reject(key, data)):
            return error
        if any(row["Uuid"] == data.get("Uuid") for row in self.rows[key]):
            return "Insert data failed. Value uniqueness violation. Error Number: 2627"
        return None

    def _insert(self, key: str, data: dict) -> EntityRecord | str:
        if self.before_insert is not None:
            self.before_insert(key, data)
        error = self._refusal(key, data)
        if error:
            return error
        row = {"Id": self._new_id(), **{field: None for field in ENTITY_FIELDS[self._name(key)]}, **data}
        self.rows[key].append(row)
        return EntityRecord(**row)

    def insert_record(self, entity_key, data, expansion_level=None):
        self.calls.append("insert_record")
        result = self._insert(entity_key, dict(data))
        if isinstance(result, str):
            raise RuntimeError(result)
        self._save()
        return result

    def insert_records(self, entity_key, records, schema=None, expansion_level=None, fail_on_first=None):
        self.calls.append("insert_records")
        ok, failed = [], []
        for data in records:
            result = self._insert(entity_key, dict(data))
            if isinstance(result, str):
                failed.append(FailureRecord(error=result, record=dict(data)))
            else:
                ok.append(result)
        self._save()
        return EntityRecordsBatchResponse(successRecords=ok, failureRecords=failed)

    def update_record(self, entity_key, record_id, data, expansion_level=None):
        self.calls.append("update_record")
        unknown = set(data) - ENTITY_FIELDS[self._name(entity_key)]
        if unknown:
            raise RuntimeError(f"Field not found: {sorted(unknown)}")
        for row in self.rows[entity_key]:
            if row["Id"] == record_id:
                row.update(data)  # an explicit None is stored: it clears the field
                self._save()
                return EntityRecord(**row)
        raise RuntimeError(f"Record {record_id} does not exist")

    def retrieve_records(self, entity_key, filter_group=None, start=None, limit=None, **unused):
        self.calls.append("retrieve_records")
        start = start or 0
        limit = self.page_limit if limit is None else limit
        if limit > self.page_limit:
            raise ValueError(f"A query returns at most {self.page_limit} records, not {limit}")
        rows = self.rows[entity_key]
        if filter_group:
            for query_filter in filter_group.query_filters:
                assert query_filter.operator == QueryFilterOperator.Equals, "the fake knows only '='"
                rows = [row for row in rows if row.get(query_filter.field_name) == query_filter.value]
        page = rows[start : start + limit]
        return RetrieveEntityRecordsResponse(
            items=[EntityRecord(**row) for row in page], totalCount=len(rows), hasNextPage=start + len(page) < len(rows)
        )


def local_sdk(bucket_dir: str | Path, datafabric_file: str | Path | None = None) -> SimpleNamespace:
    """An SDK-shaped object for a run without a tenant: buckets from a folder, Data Fabric rows in a JSON file (or in memory)."""
    return SimpleNamespace(buckets=FakeBuckets(root=bucket_dir), entities=FakeEntities(path=datafabric_file))
