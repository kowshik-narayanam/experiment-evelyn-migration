# Own tests of ErrorUtils (S:ErrorUtils.java:12); Evelyn has no test for it.
from evmig_nss.schema.error_utils import parse_field_and_record_error
from evmig_nss.schema.exceptions import InvalidInputDataException


def _raise(message):
    def parser():
        raise InvalidInputDataException(message)

    return parser


def test_a_result_is_returned_and_nothing_recorded():
    errors = {}
    assert parse_field_and_record_error(lambda: 5, "Name", 3, errors) == 5
    assert errors == {}


def test_an_invalid_input_is_recorded_under_the_error_text_with_every_line_it_happened_on():
    errors = {}
    assert parse_field_and_record_error(_raise("client_column"), "Gender", 3, errors) is None
    assert parse_field_and_record_error(_raise("client_column"), "Gender", 9, errors) is None
    assert parse_field_and_record_error(_raise(None), "Gender", 9, errors) is None  # no column: no brackets
    assert errors == {"Gender parsing error in column (client_column)": [3, 9], "Gender parsing error in column": [9]}


def test_a_missing_line_number_is_recorded_as_none():
    errors = {}
    parse_field_and_record_error(_raise(" "), "Name", None, errors)
    assert errors == {"Name parsing error in column": [None]}


def test_any_other_exception_is_not_caught():
    def parser():
        raise KeyError("boom")

    try:
        parse_field_and_record_error(parser, "Name", 1, {})
    except KeyError:
        return
    raise AssertionError("KeyError was swallowed")
