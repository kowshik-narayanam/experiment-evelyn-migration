"""Ports S3DownloadService (C:service/S3DownloadService.java:32) over one Orchestrator bucket (DEC-7, D-4).

Evelyn's S3 path `<bucket>/<key>` becomes the key of one bucket (EvMigFiles): the bucket segment stays in the key,
so a configuration value such as `doc-upload/name_sanctions_screening/csv/` is used as it is.

`buckets` is `sdk.buckets` (or a FakeBuckets); it is passed in, this module never logs in.

Three things the Orchestrator needs, found on other ports (DEC-7):
  - a list prefix that ends in "/" is answered with HTTP 400, so the prefix sent never ends in "/" and the
    keys are filtered here against the real prefix;
  - list_files returns one page, so the store follows the continuation token;
  - buckets.exists_file reports present files as missing, so existence is checked from a listing;
  - buckets.download does not check the HTTP status of the file it fetches (see read_bytes), so a missing file is
    looked for in a listing before it is downloaded.

Not reproduced (D-4): the three string-handling defects of S3DownloadService that show only with odd names
(C:service/S3DownloadService.java:85 `fullPath.replace(key, ...)`, :175 `split(bucketName + "/")[1]`, :100 the temp file name).
Skipped: CSV parsing (downloadS3Content returns commons-csv records; the text is returned here and EvMigCsvTask
parses it).
"""
import logging
import os
import re
import tempfile
from collections.abc import Iterator

import httpx
from uipath.platform.errors import EnrichedException

from evmig_nss.core.constants import BUCKET_NAME
from evmig_nss.core.errors import InvalidPathException
from evmig_nss.core.strings import is_not_blank

logger = logging.getLogger(__name__)

_CSV_EXTENSION = ".csv"
_BUCKET_AND_KEY = re.compile(r"([^/]*)/(.*)")  # C:service/S3DownloadService.java:35
_NO_SUCH_FILE = "Please provide correct path to file"  # C:service/S3DownloadService.java:46


class BucketStore:
    def __init__(self, buckets, bucket_name: str = BUCKET_NAME):
        self._buckets = buckets
        self._bucket_name = bucket_name

    # ---- keys and bytes ----

    def _iter_keys(self, prefix: str) -> Iterator[str]:
        """The file keys that start with `prefix`, page by page, in the order the listing gives them."""
        token = None
        while True:
            page = self._buckets.list_files(name=self._bucket_name, prefix=prefix.rstrip("/"), continuation_token=token)
            for item in page.items:
                key = item.full_path.removeprefix("/")  # staging drops or keeps the leading slash
                if not item.is_directory and key.startswith(prefix):
                    yield key
            token = page.continuation_token
            if not token:
                return

    def list_keys(self, prefix: str) -> list[str]:
        """Every file key that starts with `prefix`, at any depth, in lexicographic order."""
        return sorted(self._iter_keys(prefix))

    def read_bytes(self, key: str) -> bytes:
        """Download one file. The SDK can only write to a file, so a temp folder is used (S3DownloadService.downloadTempFile).

        A missing file raises FileNotFoundError here, before any download. The SDK would not: `buckets.download` fetches the
        read URI with `self.custom_client.get(...)` and writes `.content` without looking at the status
        (uipath/platform/orchestrator/_buckets_service.py:452-455, uipath 2.14), so for a missing blob the file it writes
        is the storage's XML error body. Unchecked, a missing config/configuration_payload.json would be read as an
        unreadable JSON, which Configuration.from_text turns into an empty configuration, instead of failing the step.
        Java's equivalent is S3DownloadService.validateFileExists (:41-46), which fails with "<reason>: <input>".
        """
        if key not in self._iter_keys(key):  # stops at the first match
            raise FileNotFoundError(str(InvalidPathException(key, _NO_SUCH_FILE)))
        with tempfile.TemporaryDirectory(prefix="evmig-") as folder:
            target = os.path.join(folder, "blob")
            self._buckets.download(name=self._bucket_name, blob_file_path=key, destination_path=target)
            with open(target, "rb") as file:
                data = file.read()
            logger.info("Downloaded %s to %s. File size %s", key, target, len(data))  # C:service/S3DownloadService.java:105
            return data

    def read_text(self, key: str) -> str:
        """A file's text as UTF-8 (a bad byte becomes U+FFFD, like Java's new String(bytes))."""
        return self.read_bytes(key).decode("utf-8", errors="replace")

    # ---- S3DownloadService ----

    def validate_file_exists(self, full_file_path: str) -> None:
        """C:service/S3DownloadService.java:41. Raises InvalidPathException unless the file `<bucket>/<key>` exists."""
        bucket_name = _extract_bucket_name(full_file_path)
        if self.is_bucket_exists(full_file_path):
            if not self.is_file_exists(full_file_path):
                raise InvalidPathException(full_file_path, _NO_SUCH_FILE)
        else:
            raise InvalidPathException(bucket_name, "Bucket with such name doesn't exist on S3")

    def is_file_exists(self, full_file_path: str) -> bool:
        """C:service/S3DownloadService.java:53."""
        _extract_bucket_name(full_file_path)
        _extract_key(full_file_path, False)  # raises when the key is blank
        return full_file_path in self.list_keys(full_file_path)

    def is_bucket_exists(self, full_file_path: str) -> bool:
        """C:service/S3DownloadService.java:60. A bucket "exists" when some key starts with `<bucket>/` (D-4)."""
        return any(True for _ in self._iter_keys(_extract_bucket_name(full_file_path) + "/"))  # stops at the first key

    def get_csv_files_list(self, full_path: str) -> list[str]:
        """C:service/S3DownloadService.java:66.

        A path ending in .csv is one file (it must exist). Otherwise every key under the path that ends in lower-case
        .csv, at any depth, sorted; the format file is not excluded.

        The listing is in Java's try block (S3DownloadService.java:78-89): `catch (SdkClientException e)` turns a failure
        into an empty list, so a missing bucket, access denied or a 400 all end in "There are no csv files in …".
        Inference: that catch covers every AWS SDK error, because AmazonServiceException extends SdkClientException in
        aws-java-sdk-core 1.12.792 (javap; the version in ~/.m2, the one deployed with Evelyn is unknown). Here the
        uipath SDK's own failures get the same treatment (see _is_sdk_failure); any other error propagates, as a
        programming error does in Java. The single-file branch is outside the try, so its errors propagate.
        """
        _extract_bucket_name(full_path)
        key = _extract_key(full_path, True)
        if key.endswith(_CSV_EXTENSION):
            self.validate_file_exists(full_path)
            return [full_path]
        try:
            csv_data_files = [found for found in self.list_keys(full_path) if found.endswith(_CSV_EXTENSION)]
        except Exception as e:
            if not _is_sdk_failure(e):
                raise
            logger.warning("Listing %s failed, treated as no csv files (Evelyn swallows it too): %s", full_path, e)  # the log is not Evelyn's
            csv_data_files = []
        if not csv_data_files:
            raise InvalidPathException(full_path, f"There are no csv files in {full_path}. Please provide correct path to csv data.")
        return csv_data_files

    def read_csv_text(self, full_path: str) -> str:
        """C:service/S3DownloadService.java:110 without the CSV parsing: the file's text, a UTF-8 BOM removed.

        A zero-byte file fails with "File <path> is empty" (a plain error in Java too, :120).
        """
        _extract_bucket_name(full_path)
        data = self.read_bytes(full_path)
        if len(data) == 0:
            raise ValueError(f"File {full_path} is empty")
        return data.removeprefix(b"\xef\xbb\xbf").decode("utf-8", errors="replace")


def _is_sdk_failure(error: Exception) -> bool:
    """What the uipath SDK raises when a call fails: an HTTP error status (EnrichedException, common/_base_service.py:226),
    a transport failure (httpx.HTTPError), or its LookupError "Bucket with name '…' not found" (orchestrator/_buckets_service.py:751).
    Exactly LookupError: its subclasses KeyError and IndexError are bugs, not the SDK's answer."""
    return isinstance(error, (EnrichedException, httpx.HTTPError)) or type(error) is LookupError


def _extract_bucket_name(full_path: str) -> str:
    match = _BUCKET_AND_KEY.search(full_path)
    if match is None:
        raise InvalidPathException(full_path, "Missing bucket name")  # C:service/S3DownloadService.java:156
    return match.group(1)


def _extract_key(full_path: str, is_empty_source_allowed: bool) -> str:
    match = _BUCKET_AND_KEY.search(full_path)
    if match is None or not (is_empty_source_allowed or is_not_blank(match.group(2))):
        raise InvalidPathException(full_path, "Path to file or folder isn't correct")  # C:service/S3DownloadService.java:165
    return match.group(2)
