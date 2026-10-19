"""Ports GenderUtils.fromString (S:GenderUtils.java:11). Skipped: fromAPI (the REST request mapping)."""
from evmig_nss.core.constants import InputAttribute
from evmig_nss.core.strings import is_blank, java_trim
from evmig_nss.schema.exceptions import InvalidInputDataException
from evmig_nss.schema.models import Gender


def from_string(gender_str: InputAttribute) -> Gender | None:
    """Blank -> None; M/MALE, F/FEMALE, OTHER (any case); anything else raises with the client column as message."""
    if is_blank(gender_str.value):
        return None
    value = java_trim(gender_str.value.upper())
    if value in ("MALE", "M"):
        return Gender.MALE
    if value in ("FEMALE", "F"):
        return Gender.FEMALE
    try:
        return Gender(value)  # Gender.fromValue: MALE, FEMALE and OTHER only
    except ValueError:
        raise InvalidInputDataException(gender_str.client_column) from None
