"""Ports ErrorUtils (S:ErrorUtils.java:12)."""
from collections.abc import Callable
from typing import TypeVar

from evmig_nss.core.strings import is_blank
from evmig_nss.schema.exceptions import InvalidInputDataException

T = TypeVar("T")


def parse_field_and_record_error(
    parser: Callable[[], T], field_name: str, line_number: int | None, errors: dict[str, list[int | None]]
) -> T | None:
    """Run `parser`; if it raises InvalidInputDataException, record the line under an error text and return None.

    `errors` is filled in place: error text -> the line numbers (None when there is no line number) it happened on.
    Java passes a Supplier<T> (`() -> parse(...)`); here it is a zero-argument lambda, called inside the try block.
    """
    try:
        return parser()
    except InvalidInputDataException as e:
        _record_error(errors, field_name, e.message, line_number)
        return None


def _record_error(errors: dict[str, list[int | None]], field_name: str, message: str | None, line_number: int | None):
    # S:ErrorUtils.java:23-41: both overloads build the same text; the line is None when no number was given.
    message_part = "" if is_blank(message) else f" ({message})"
    error_message = f"{field_name} parsing error in column{message_part}"
    errors.setdefault(error_message, []).append(line_number)
