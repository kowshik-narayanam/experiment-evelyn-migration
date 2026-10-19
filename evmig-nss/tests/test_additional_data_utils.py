# Ports AdditionalDataUtilsTest (names-screening-schema .../nss/AdditionalDataUtilsTest.java).
from evmig_nss.core.constants import EXT_DATA_POSTFIX, INPUT, INPUT_ATTR_CASE_SYSTEM_ID
from evmig_nss.schema import additional_data_utils
from helpers import attrs


def test_should_filter_out_additional_data_based_on_prefixes():  # ports AdditionalDataUtilsTest.java:20 shouldFilterOutAdditionalDataBasedOnPrefixes
    additional_data = attrs({
        "input_Important_data" + EXT_DATA_POSTFIX: "important_data", INPUT_ATTR_CASE_SYSTEM_ID: "case_id",
        "other_data1": "other_data1", "other_data2": "other_data2", "other_data3": "other_data3",
    }, "some_column")  # fmt: skip
    result = additional_data_utils.get_additional_data(additional_data, INPUT, INPUT_ATTR_CASE_SYSTEM_ID)
    assert result == {"important_data": "important_data", "case_system_id": "case_id"}  # ATTR_CASE_SYSTEM_ID = "case_system_id"


def test_should_extract_identifiers_without_pre_or_postfixes():  # ports AdditionalDataUtilsTest.java:40 shouldExtractIdentifiersWithoutPreOrPostfixes
    identifiers = attrs({"any_prefix_one_identifier": "123", "any_prefix_two_identifier": "456", "any_prefix_one": "9999"}, "some_column")
    assert additional_data_utils.get_identifiers(identifiers, "any_prefix") == {"one": "123", "two": "456"}


# ---- own tests ----


def test_blank_values_are_left_out_and_keys_are_lower_cased_in_row_order():
    cells = attrs({"hit_B_identifier": "2", "hit_a_identifier": "  ", "hit_1_extdata": "x", "hit_Z_extdata": "z", "hit": "root"})
    assert additional_data_utils.get_identifiers(cells, "hit") == {"b": "2"}
    assert list(additional_data_utils.get_additional_data(cells, "hit").items()) == [("1", "x"), ("z", "z"), ("hit", "root")]


def test_a_column_named_like_a_prefix_is_found_the_way_java_equals_ignore_case_does():
    # AdditionalDataUtils.matchesAdditionalDataConditions (S:AdditionalDataUtils.java:43): key.equalsIgnoreCase(prefix).
    # Confirmed on OpenJDK 21.0.12.1 (2026-10-19): "\u0131nput".equalsIgnoreCase("input") and "INPUT".equalsIgnoreCase("input")
    # are true (U+0131 dotless i upper-cases to I); str.lower() keeps U+0131 apart from i.
    for key in ["\u0131nput", "INPUT", "Input"]:
        assert list(additional_data_utils.get_additional_data(attrs({key: "root"}), INPUT)) == [key.lower()]
    assert additional_data_utils.get_additional_data(attrs({"inputs": "no"}), INPUT) == {}


def test_a_prefix_inside_the_key_is_removed_everywhere_like_java_replace():
    assert additional_data_utils.get_ext_data_id("input_x_input_y_extdata", "input") == "x_y"
