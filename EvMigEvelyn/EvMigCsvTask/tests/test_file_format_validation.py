"""The four format-file checks. Java has no test of its own for them (CsvDataServiceTest reaches them through mapFileFormat:
see test_csv_data_service.py); these pin each rule, with the texts from the Java classes."""
import pytest

from file_format_validation import (
    data_size_validation,
    hit_matched_name_validator,
    input_full_name_validator,
    input_id_validator,
    validate_format,
)

GOOD = {"id": "input_id", "name": "input_full_name", "matched": "hit_matched_name"}


def test_a_mapping_with_the_three_required_columns_has_no_errors():
    assert validate_format(GOOD) == []


def test_an_empty_mapping_fails_all_four_checks_in_order():
    assert validate_format({}) == [
        "Format file is empty",
        "Format file should contain input_full_name mapping",
        "Format file should contain input_id mapping",
        "Format file should contain hit_matched_name mapping",
    ]


@pytest.mark.parametrize(
    "mapping, expected",
    [
        ({}, "Format file is empty"),
        ({"": "input_id", "  ": "hit_id"}, "Format file should contain mandatory client columns"),
        ({"id": " ", "name": ""}, "Format file should contain mandatory NSS columns"),
        ({"": "", "id": "input_id"}, None),  # one usable column is enough: allMatch needs every one blank
    ],
)
def test_data_size_validation(mapping, expected):  # DataSizeValidation.java:16
    assert data_size_validation(mapping) == expected


@pytest.mark.parametrize(
    "check, nss_name",
    [(input_full_name_validator, "input_full_name"), (input_id_validator, "input_id"), (hit_matched_name_validator, "hit_matched_name")],
)
def test_a_required_nss_name_is_a_substring_check(check, nss_name):
    assert check({"c": f"{nss_name}_extra"}) is None  # a substring counts: `input_id_rn_extdata` maps input_id
    assert check({"c": "something_else"}) == f"Format file should contain {nss_name} mapping"
    assert check({}) == f"Format file should contain {nss_name} mapping"


def test_the_check_is_case_sensitive_because_the_format_file_was_lower_cased_before():
    assert input_id_validator({"c": "INPUT_ID"}) == "Format file should contain input_id mapping"
