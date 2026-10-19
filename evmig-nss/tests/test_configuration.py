# Own tests of core/configuration.py. Evelyn has no unit test for the toolkit's reader, so the expected values are
# what the real jnw-toolkit-configuration 3.0.0.87 jar returned (jsonpath 2.10, Jackson 2.21.5) for each document
# on 2026-10-19.
import logging
import re

import pytest

from evmig_nss.core import configuration
from evmig_nss.core.bucket_store import BucketStore
from evmig_nss.core.configuration import Configuration, IllegalStateException, load_configuration
from evmig_nss.testing import FakeBuckets


def cfg(text):
    return Configuration.from_text(text)


MISSING = "Configuration does not contain property 'a.b'"


@pytest.mark.parametrize(
    "json_value, expected",
    [
        ("true", True), ("false", False),
        ('"true"', True), ('"True"', True), ('"TRUE"', True), ('"false"', False), ('"False"', False), ('"FALSE"', False),
        ('" true "', True), ('"false "', False), ('"\\tfalse"', False),  # Jackson trims
        ("1", True), ("0", False), ("2", True), ("-1", True), ("4294967296", True), ("99999999999999999999", True),
    ],
)  # fmt: skip
def test_boolean_values_the_toolkit_accepts(json_value, expected):
    assert cfg('{"a": {"b": %s}}' % json_value).get_required_boolean("a.b") is expected


@pytest.mark.parametrize("json_value", ['""', "null", '" "', '"null"'])
def test_boolean_empty_null_and_missing_are_reported_as_missing(json_value):
    with pytest.raises(IllegalStateException, match=MISSING):
        cfg('{"a": {"b": %s}}' % json_value).get_required_boolean("a.b")


@pytest.mark.parametrize("text", ["{}", '{"a": {}}', "", "not json", "[1, 2]"])
def test_boolean_missing_key_or_unreadable_document(text):
    with pytest.raises(IllegalStateException, match=MISSING):
        cfg(text).get_required_boolean("a.b")


@pytest.mark.parametrize(
    "json_value, reason",
    [
        ('"1"', 'String "1": only "true" or "false" recognized'), ('"0"', 'String "0"'), ('"yes"', 'String "yes"'),
        ('"tRuE"', 'String "tRuE"'), ('"T"', 'String "T"'), ('"on"', 'String "on"'), ('"NULL"', 'String "NULL"'),
        ("1.0", "Floating-point value"), ("0.0", "Floating-point value"), ("1e0", "Floating-point value"),
        ("[true]", "Array value"), ("{}", "Object value"),
    ],
)  # fmt: skip
def test_boolean_values_the_toolkit_refuses(json_value, reason):
    expected = "Cannot deserialize value of type `java.lang.Boolean` from " + reason
    with pytest.raises(IllegalStateException, match=re.escape(expected)):
        cfg('{"a": {"b": %s}}' % json_value).get_required_boolean("a.b")


@pytest.mark.parametrize(
    "text, expected",
    [
        ('{"a": {"b": "x"}}', "x"),
        ('{"a": {"b": 5}}', "5"),
        ('{"a": {"b": 1.5}}', "1.5"),
        ('{"a": {"b": true}}', "true"),
        ('{"a": {"b": false}}', "false"),
        ('{"a": {"b": ""}}', ""),  # an empty string is a value for the String reader
        ('{"a.b": "flat"}', "flat"),
        ('{"a": {"b": "nested"}, "a.b": "flat"}', "nested"),  # nested first
        ('{"a": null, "a.b": "flat"}', "flat"),  # then the flat key
        ('{"a": "str", "a.b": "flat"}', "flat"),
        ('{"a": {"b": null}, "a.b": "flat"}', "flat"),
    ],
)
def test_required_property_as_text(text, expected):
    assert cfg(text).get_required_property("a.b") == expected


@pytest.mark.parametrize("text", ['{"a": {"b": null}}', '{"a": {}}', "{}", "", "   ", "not json"])
def test_required_property_missing_message(text):
    with pytest.raises(IllegalStateException) as raised:
        cfg(text).get_required_property("a.b")
    assert str(raised.value) == "Configuration does not contain property 'a.b'"


def test_a_key_without_a_dot_is_a_plain_key_and_the_flat_fallback_needs_a_dot():
    assert cfg('{"x": "v"}').get_required_property("x") == "v"
    assert cfg('{"a": {"x": "v"}}').get_property("x") is None


def test_get_property_is_none_for_missing_and_null():
    assert cfg("{}").get_property("a.b") is None
    assert cfg('{"a": {"b": null}}').get_property("a.b") is None


def test_the_five_keys_of_the_csv_path_in_a_nested_document():
    document = """{
      "provider": {"FORMAT_FILE_LOCATION": "doc-upload/csv/nss_input_format.csv", "CSV_DATA_FILE_LOCATION": "doc-upload/csv/data/"},
      "configuration": {"proceed_with_error_data": true, "keep_input_file_name_for_qc_report": "false"},
      "model": {"thresholds": {"location_wle_enable": false}}
    }"""
    config = cfg(document)
    assert config.get_required_property(configuration.FORMAT_FILE_LOCATION_PATH) == "doc-upload/csv/nss_input_format.csv"
    assert config.get_required_property(configuration.DATA_FILE_LOCATION_PATH) == "doc-upload/csv/data/"
    assert config.get_required_boolean(configuration.PROCEED_WITH_ERROR_DATA_PATH) is True
    assert config.get_required_boolean(configuration.KEEP_INPUT_FILE_NAME_FOR_QC_REPORT_PATH) is False
    assert config.get_required_boolean(configuration.ENABLE_LOCATION_WLE_PATH) is False


def test_the_key_strings_are_the_ones_of_the_java_enums():
    assert configuration.FORMAT_FILE_LOCATION_PATH == "provider.FORMAT_FILE_LOCATION"
    assert configuration.DATA_FILE_LOCATION_PATH == "provider.CSV_DATA_FILE_LOCATION"
    assert configuration.PROCEED_WITH_ERROR_DATA_PATH == "configuration.proceed_with_error_data"
    assert configuration.KEEP_INPUT_FILE_NAME_FOR_QC_REPORT_PATH == "configuration.keep_input_file_name_for_qc_report"
    assert configuration.ENABLE_LOCATION_WLE_PATH == "model.thresholds.location_wle_enable"


def test_invalid_json_is_read_as_empty_like_java_but_with_a_warning(caplog):
    with caplog.at_level(logging.WARNING):
        config = cfg("{not json")
    assert config.get_property("a") is None
    assert "not valid JSON" in caplog.text


# ---- the loader ----


def fake_store(text=None):
    files = {} if text is None else {configuration.CONFIG_FILE_KEY: text}
    fake = FakeBuckets(files)
    return BucketStore(fake), fake


def test_the_loader_reads_the_file_once_per_process_and_the_reset_forgets_it():
    store, fake = fake_store('{"a": {"b": "1"}}')
    assert load_configuration(store).get_required_property("a.b") == "1"
    assert load_configuration(store) is load_configuration(store)
    one_read = [("list_files", "config/configuration_payload.json", None), ("download", "config/configuration_payload.json")]
    assert fake.calls == one_read  # the store looks the key up in a listing, then downloads it
    configuration.reset_configuration_cache()
    load_configuration(store)
    assert fake.calls == one_read * 2


def test_a_missing_file_fails_the_job_and_is_not_read_as_an_empty_configuration():
    # The real SDK would hand the storage's XML error body to Configuration.from_text, which reads unreadable JSON as
    # empty (above); BucketStore.read_bytes refuses a key that is not in the listing, so the job fails instead.
    store, fake = fake_store(None)
    with pytest.raises(FileNotFoundError, match="^Please provide correct path to file: config/configuration_payload.json$"):
        load_configuration(store)
    assert [call[0] for call in fake.calls] == ["list_files"]  # never downloaded


def test_an_empty_file_gives_an_empty_configuration_and_every_key_is_then_missing():
    store, _ = fake_store("")
    with pytest.raises(IllegalStateException, match="Configuration does not contain property"):
        load_configuration(store).get_required_property(configuration.FORMAT_FILE_LOCATION_PATH)
