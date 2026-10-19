"""Ports EntityTypeUtils (S:EntityTypeUtils.java:18), the methods the CSV path calls.

Skipped: fromString(String, AttributeType) and fromAPI (used by other inputs, not by the CSV path).
"""
from evmig_nss.core.constants import AttributeType, InputAttribute
from evmig_nss.core.strings import equals_ignore_case, is_blank
from evmig_nss.schema.exceptions import InvalidInputDataException
from evmig_nss.schema.models import EntityType

# S:EntityTypeUtils.java:48-61. Java maps to the display text of ReadableEntityType ("Securities") for some entries
# and to the name for others, then upper-cases the result before EntityType.fromValue; so the end result is
# always the upper-case name, which is what these maps hold.
_INPUT_TYPE_MAP = {
    "INDIVIDUAL": EntityType.INDIVIDUAL,
    "ORGANIZATION": EntityType.ORGANIZATION,
    "ORGANISATION": EntityType.ORGANIZATION,
    "SECURITIES": EntityType.SECURITIES,
}
_HIT_TYPE_MAP = {**_INPUT_TYPE_MAP, "LOCATION": EntityType.LOCATION}


def from_string(type_str: InputAttribute | None, parameter_type: AttributeType) -> EntityType | None:
    """S:EntityTypeUtils.java:19. Blank -> None; an unknown type raises with the client column as message.

    A screened record (INPUT) cannot be a LOCATION, a hit (HIT) can.
    """
    if type_str is None or is_blank(type_str.value):
        return None
    type_value = _convert_tr_entity(type_str.value)
    conversion_map = _INPUT_TYPE_MAP if parameter_type == AttributeType.INPUT else _HIT_TYPE_MAP
    entity_type = conversion_map.get(type_value.upper())
    if entity_type is None:
        raise InvalidInputDataException(type_str.client_column)
    return entity_type


def _convert_tr_entity(type_str: str) -> str:
    # S:EntityTypeUtils.java:76: Thomson Reuters calls an organisation "ENTITY".
    return EntityType.ORGANIZATION.value if equals_ignore_case(type_str, "ENTITY") else type_str


def to_string(entity_type: EntityType | str | None) -> str | None:
    """S:EntityTypeUtils.java:88. The enum's name, or None."""
    return None if entity_type is None else EntityType(entity_type).name
