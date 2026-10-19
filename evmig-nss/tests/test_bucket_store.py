# Ports S3DownloadServiceTest (names-screening-core .../core/service/S3DownloadServiceTest.java) over FakeBuckets.
# Java mocks S3 and its keys are relative to the bucket ("data/a.csv"); here a key is the whole path ("doc-upload/data/a.csv").
import logging

import httpx
import pytest
from uipath.platform.errors import EnrichedException

from evmig_nss.core.bucket_store import BucketStore
from evmig_nss.core.errors import InvalidPathException
from evmig_nss.testing import FakeBuckets, sdk_http_error


def store_with(files, **fake_options):
    fake = FakeBuckets(files, **fake_options)
    return BucketStore(fake), fake


def test_should_validate_that_file_exists():  # ports S3DownloadServiceTest.java:49 shouldValidateThatFileExists
    store, _ = store_with({"doc-upload/input_file.csv": "x"})
    store.validate_file_exists("doc-upload/input_file.csv")  # no error


def test_should_get_single_csv_data_file():  # ports S3DownloadServiceTest.java:61 shouldGetSingleCsvDataFile
    path_to_csv_file = "doc-upload/data/input_file.csv"
    store, _ = store_with({path_to_csv_file: "x"})
    assert store.get_csv_files_list(path_to_csv_file) == [path_to_csv_file]


def test_should_get_all_csv_data_files_in_folder():  # ports S3DownloadServiceTest.java:77 shouldGetAllCsvDataFilesInFolder
    store, _ = store_with({  # listed out of order on purpose
        "doc-upload/data/input_file_2.csv": "x", "doc-upload/data/input_file_1.txt": "x", "doc-upload/data/input_file_1.csv": "x",
    })  # fmt: skip
    assert store.get_csv_files_list("doc-upload/data/") == ["doc-upload/data/input_file_1.csv", "doc-upload/data/input_file_2.csv"]


def test_should_request_all_keys_when_listing_folder_so_listing_is_not_capped_at_first_page():
    # ports S3DownloadServiceTest.java:97. Java checks the request asks for all keys; here that is following the token.
    # It also pins DEC-7: the prefix sent has no trailing "/" (FakeBuckets refuses one, as Orchestrator does).
    files = {f"doc-upload/data/file_{n}.csv": "x" for n in range(5)}
    store, fake = store_with(files, page_size=2)
    assert store.get_csv_files_list("doc-upload/data/") == sorted(files)
    assert fake.calls == [("list_files", "doc-upload/data", None), ("list_files", "doc-upload/data", "2"), ("list_files", "doc-upload/data", "4")]


def test_should_throw_exception_when_no_bucket_name():  # ports S3DownloadServiceTest.java:116 shouldThrowExceptionWhenNoBucketName
    store, _ = store_with({})
    with pytest.raises(InvalidPathException) as raised:
        store.read_csv_text("input_file.csv")
    assert str(raised.value) == "Missing bucket name: input_file.csv"


def test_should_throw_exception_when_no_source():  # ports S3DownloadServiceTest.java:124 shouldThrowExceptionWhenNoSource
    store, _ = store_with({"doc-upload/other.csv": "x"})  # the bucket exists
    with pytest.raises(InvalidPathException) as raised:
        store.validate_file_exists("doc-upload/")
    assert str(raised.value) == "Path to file or folder isn't correct: doc-upload/"


def test_should_throw_exception_when_file_does_not_exist():  # ports S3DownloadServiceTest.java:138 shouldThrowExceptionWhenFileDoesNotExist
    store, _ = store_with({"doc-upload/other.csv": "x"})
    with pytest.raises(InvalidPathException) as raised:
        store.validate_file_exists("doc-upload/file_not_exist.csv")
    assert "Please provide correct path to file: doc-upload/file_not_exist.csv" in str(raised.value)


def test_should_throw_exception_when_bucket_does_not_exist():  # ports S3DownloadServiceTest.java:153 shouldThrowExceptionWhenBucketDoesNotExist
    store, _ = store_with({"other-bucket/file_not_exist.csv": "x"})
    with pytest.raises(InvalidPathException) as raised:
        store.validate_file_exists("doc-upload/file_not_exist.csv")
    assert "Bucket with such name doesn't exist on S3: doc-upload" in str(raised.value)


def test_should_throw_exception_when_no_csv_data_files_in_folder():  # ports S3DownloadServiceTest.java:167 shouldThrowExceptionWhenNoCsvDataFilesInFolder
    store, _ = store_with({"doc-upload/data/input_file_1.txt": "x", "doc-upload/data/input_file_2.txt": "x"})
    with pytest.raises(InvalidPathException) as raised:
        store.get_csv_files_list("doc-upload/data/")
    assert "There are no csv files in doc-upload/data/. Please provide correct path to csv data." in str(raised.value)


# ---- own tests: the behaviours of docs/mapping.md claims 4-5 and DEC-7 that the nine Java tests leave out ----


def test_the_full_error_is_reason_colon_input():
    store, _ = store_with({})
    with pytest.raises(InvalidPathException) as raised:
        store.get_csv_files_list("doc-upload/data/")
    assert str(raised.value) == "There are no csv files in doc-upload/data/. Please provide correct path to csv data.: doc-upload/data/"
    assert raised.value.input == "doc-upload/data/"


def test_a_data_path_ending_csv_is_one_file_that_must_exist_and_gets_the_same_checks_as_the_format_file():
    store, _ = store_with({"doc-upload/data/a.csv": "x"})
    assert store.get_csv_files_list("doc-upload/data/a.csv") == ["doc-upload/data/a.csv"]
    with pytest.raises(InvalidPathException, match="Please provide correct path to file: doc-upload/data/b.csv"):
        store.get_csv_files_list("doc-upload/data/b.csv")
    with pytest.raises(InvalidPathException, match="Bucket with such name doesn't exist on S3: nope"):
        store.get_csv_files_list("nope/b.csv")


def test_a_folder_lists_every_depth_only_lower_case_csv_and_does_not_exclude_the_format_file():
    store, _ = store_with({
        "doc-upload/csv/nss_input_format.csv": "x", "doc-upload/csv/data/one.csv": "x", "doc-upload/csv/data/deeper/two.csv": "x",
        "doc-upload/csv/data/upper.CSV": "x", "doc-upload/csv/data/notes.txt": "x", "doc-upload/csv/data/three.csv.bak": "x",
    })  # fmt: skip
    assert store.get_csv_files_list("doc-upload/csv/") == [
        "doc-upload/csv/data/deeper/two.csv",
        "doc-upload/csv/data/one.csv",
        "doc-upload/csv/nss_input_format.csv",
    ]


def test_a_prefix_matches_like_an_s3_prefix_but_the_bucket_segment_is_exact():
    store, _ = store_with({"doc-upload/data/a.csv": "x", "doc-upload/data2/b.csv": "x", "doc-upload2/data/c.csv": "x"})
    # no trailing "/": S3 treats the prefix as raw text, so data2/ matches too (Java does the same)
    assert store.get_csv_files_list("doc-upload/data") == ["doc-upload/data/a.csv", "doc-upload/data2/b.csv"]
    # the bucket is not a text prefix: doc-upload2 is another bucket
    assert store.get_csv_files_list("doc-upload/") == ["doc-upload/data/a.csv", "doc-upload/data2/b.csv"]


def test_a_leading_slash_in_the_listing_is_removed_and_a_big_listing_is_sorted():
    store, _ = store_with({f"b/k{n}.csv": "x" for n in (3, 1, 2)}, leading_slash=True, page_size=2)
    assert store.list_keys("b/") == ["b/k1.csv", "b/k2.csv", "b/k3.csv"]


def test_the_bucket_must_have_a_key_under_its_folder_to_exist():
    store, _ = store_with({"doc-upload/a.csv": "x", "doc-uploads/b.csv": "x"})
    assert store.is_bucket_exists("doc-upload/x.csv")
    assert not store.is_bucket_exists("doc/x.csv")


def test_the_bucket_check_stops_at_the_first_page_that_has_a_match():
    files = {f"doc-upload/file_{n}.csv": "x" for n in range(6)}
    store, fake = store_with(files, page_size=2)
    assert store.is_bucket_exists("doc-upload/x.csv")
    assert fake.calls == [("list_files", "doc-upload", None)]  # 6 keys in 3 pages; the first page already has a match


def test_the_bucket_check_follows_the_pages_until_a_match_or_the_end():
    # The listing's prefix is "doc-upload" (no "/"), so it also returns the doc-uploads/ keys; only the last key is in the bucket.
    files = {f"doc-uploads/file_{n}.csv": "x" for n in range(4)} | {"doc-upload/late.csv": "x"}
    store, fake = store_with(files, page_size=2)
    assert store.is_bucket_exists("doc-upload/x.csv")
    assert [call[2] for call in fake.calls] == [None, "2", "4"]  # pages 1 and 2 have no key under doc-upload/, page 3 has
    other, other_fake = store_with({f"doc-uploads/file_{n}.csv": "x" for n in range(4)}, page_size=2)
    assert not other.is_bucket_exists("doc-upload/x.csv")
    assert [call[2] for call in other_fake.calls] == [None, "2"]  # no match anywhere: every page is read


def test_read_csv_text_removes_a_utf8_bom_and_decodes_utf8():
    store, _ = store_with({"b/with_bom.csv": b"\xef\xbb\xbfinput_id,name\n1,Z\xc3\xb6e\n", "b/plain.csv": "input_id\n1\n"})
    assert store.read_csv_text("b/with_bom.csv") == "input_id,name\n1,Zöe\n"
    assert store.read_csv_text("b/plain.csv") == "input_id\n1\n"


def test_an_empty_file_fails_with_evelyns_text_but_a_file_with_only_a_bom_is_not_empty():
    store, _ = store_with({"b/empty.csv": b"", "b/bom_only.csv": b"\xef\xbb\xbf"})
    with pytest.raises(ValueError, match="^File b/empty.csv is empty$"):
        store.read_csv_text("b/empty.csv")
    assert store.read_csv_text("b/bom_only.csv") == ""  # Java checks the length before it removes the BOM


def test_a_file_of_only_whitespace_is_not_empty():
    store, _ = store_with({"b/blank.csv": "  \n"})
    assert store.read_csv_text("b/blank.csv") == "  \n"  # Java checks the byte length, not the text


def test_a_missing_file_raises_before_any_download_with_s3_download_services_text():
    # The SDK's own download would not fail (see test_http_buckets.py): the store checks the key in a listing first.
    # Text: the reason of S3DownloadService.java:46 in the `<reason>: <input>` format of InvalidPathException.
    store, fake = store_with({"b/other.csv": "x"})
    with pytest.raises(FileNotFoundError, match="^Please provide correct path to file: b/not_there.csv$"):
        store.read_csv_text("b/not_there.csv")
    assert fake.calls == [("list_files", "b/not_there.csv", None)]  # no download


@pytest.mark.parametrize("method", ["read_bytes", "read_text"])
def test_read_bytes_and_read_text_of_a_missing_key_raise_and_a_key_that_only_starts_the_same_does_not_count(method):
    store, fake = store_with({"b/a.csv.bak": "x"})  # the listing finds it for the prefix "b/a.csv", but it is another key
    with pytest.raises(FileNotFoundError, match="b/a.csv$"):
        getattr(store, method)("b/a.csv")
    assert not any(call[0] == "download" for call in fake.calls)


def test_read_csv_text_of_a_missing_file_fails_and_of_an_existing_one_lists_then_downloads():
    store, fake = store_with({"b/a.csv": "input_id\n1\n"})
    assert store.read_csv_text("b/a.csv") == "input_id\n1\n"
    assert fake.calls == [("list_files", "b/a.csv", None), ("download", "b/a.csv")]


def test_read_text_for_a_config_file_uses_the_key_as_it_is():
    store, fake = store_with({"config/configuration_payload.json": '{"a": 1}'})
    assert store.read_text("config/configuration_payload.json") == '{"a": 1}'
    assert fake.calls == [("list_files", "config/configuration_payload.json", None), ("download", "config/configuration_payload.json")]


def test_the_store_asks_for_its_own_bucket_by_name():
    fake = FakeBuckets({"b/a.csv": "x"}, name="OtherBucket")
    with pytest.raises(LookupError, match="Bucket with name 'EvMigFiles' not found"):
        BucketStore(fake).list_keys("b/")
    assert BucketStore(fake, "OtherBucket").list_keys("b/") == ["b/a.csv"]


# ---- the listing failure Evelyn swallows (S3DownloadService.java:78-89 `catch (SdkClientException e)`) ----

NO_CSV_FILES = "There are no csv files in doc-upload/data/. Please provide correct path to csv data."


@pytest.mark.parametrize(
    "error",
    [
        sdk_http_error(403),  # access denied
        sdk_http_error(400),  # a bad prefix
        sdk_http_error(500),
        httpx.ConnectError("no route to Orchestrator"),  # transport
        httpx.ReadTimeout("slow"),
        LookupError("Bucket with name 'EvMigFiles' not found"),  # the SDK's answer for a missing bucket
    ],
    ids=["403", "400", "500", "connect error", "timeout", "bucket not found"],
)
def test_an_sdk_error_while_listing_is_swallowed_into_no_csv_files(error, caplog):
    store, fake = store_with({"doc-upload/data/a.csv": "x"})
    fake.fail_listing_with = error
    with caplog.at_level(logging.WARNING), pytest.raises(InvalidPathException) as raised:
        store.get_csv_files_list("doc-upload/data/")
    assert NO_CSV_FILES in str(raised.value)
    assert "treated as no csv files" in caplog.text  # the failure is not lost: it is logged


def test_the_wrong_bucket_name_is_the_sdks_lookup_error_and_so_also_ends_in_no_csv_files():
    fake = FakeBuckets({"doc-upload/data/a.csv": "x"}, name="OtherBucket")
    with pytest.raises(InvalidPathException) as raised:
        BucketStore(fake).get_csv_files_list("doc-upload/data/")  # the store asks for EvMigFiles
    assert NO_CSV_FILES in str(raised.value)


@pytest.mark.parametrize(
    "error",
    [
        ValueError("HTTP 400: Orchestrator refuses a ListFiles prefix that ends in '/'"),  # what the fake raises for a trailing "/"
        KeyError("full_path"),  # a LookupError subclass, but a bug
        IndexError("list index out of range"),
        RuntimeError("a programming error"),
    ],
    ids=["trailing-slash refusal", "KeyError", "IndexError", "RuntimeError"],
)
def test_an_error_that_is_not_the_sdks_propagates_from_the_listing(error):
    store, fake = store_with({"doc-upload/data/a.csv": "x"})
    fake.fail_listing_with = error
    with pytest.raises(type(error)):
        store.get_csv_files_list("doc-upload/data/")


def test_the_fakes_own_trailing_slash_refusal_is_not_swallowed():
    fake = FakeBuckets({"doc-upload/data/a.csv": "x"})
    with pytest.raises(ValueError, match="HTTP 400"):
        fake.list_files(name="EvMigFiles", prefix="doc-upload/data/")  # the store never sends it; if it did, it would surface here


def test_the_single_file_branch_is_outside_the_try_so_its_sdk_error_propagates():
    store, fake = store_with({"doc-upload/data/a.csv": "x"})
    fake.fail_listing_with = sdk_http_error(403)
    with pytest.raises(EnrichedException):
        store.get_csv_files_list("doc-upload/data/a.csv")  # validate_file_exists lists too, as in Java it checks S3
