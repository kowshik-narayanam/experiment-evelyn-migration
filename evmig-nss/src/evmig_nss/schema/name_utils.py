"""Ports NameUtils (S:NameUtils.java:33), the methods the CSV path calls.

Skipped: isAnyNamePresent, getFullName, getAliasesForFactiva, getNameEntityList, getOriginalNameString,
generateNameString, generateNameFromComponents, getAliasesFromFactivaMap, getAliasesFromList (used by other inputs,
reports and the model, not by the CSV path).
"""
from evmig_nss.core.constants import (
    HIT_FIRST_NAME,
    HIT_LAST_NAME,
    HIT_MATCHED_NAME,
    HIT_MIDDLE_NAME,
    INPUT,
    INPUT_FIRST_NAME,
    INPUT_FULL_NAME,
    INPUT_LAST_NAME,
    INPUT_MIDDLE_NAME,
    NAME_POSTFIX,
    AttributeType,
    InputAttribute,
)
from evmig_nss.core.strings import equals_ignore_case, get_string_value, is_blank, is_not_blank
from evmig_nss.schema.exceptions import InvalidInputDataException
from evmig_nss.schema.models import NameEntity

_INPUT_NON_ALIASES = [INPUT_FULL_NAME, INPUT_FIRST_NAME, INPUT_LAST_NAME, INPUT_MIDDLE_NAME]
_WLE_NON_ALIASES = [HIT_MATCHED_NAME, HIT_FIRST_NAME, HIT_LAST_NAME, HIT_MIDDLE_NAME]


def validate_name_presence(
    primary_name: NameEntity | None, aliases: list[NameEntity] | None, attribute_type: AttributeType
) -> tuple[NameEntity | None, list[NameEntity] | None]:
    """S:NameUtils.java:38. Raises if neither the primary name nor any alias has any text."""
    all_aliases_blank = aliases is None or all(_is_name_effectively_blank(alias) for alias in aliases)
    if _is_name_effectively_blank(primary_name) and all_aliases_blank:
        raise InvalidInputDataException(f"missing {attribute_type.prefix} names")
    return primary_name, aliases


def _is_name_effectively_blank(name: NameEntity | None) -> bool:
    if name is None:
        return True
    return all(is_blank(part) for part in (name.fullName, name.firstName, name.lastName, name.middleName))


def check_for_any_name_and_extract(attributes: dict[str, InputAttribute], attribute_type: AttributeType) -> NameEntity:
    """S:NameUtils.java:64. The primary name: `input_full_name` or `hit_matched_name`, plus first, last, middle."""
    name = NameEntity()
    if attribute_type == AttributeType.INPUT:
        name.fullName = get_string_value(attributes, _attribute_resolver(attribute_type, "full_name"), None)
    else:
        name.fullName = get_string_value(attributes, _attribute_resolver(attribute_type, "matched_name"), None)
    name.firstName = get_string_value(attributes, _attribute_resolver(attribute_type, "first_name"), None)
    name.lastName = get_string_value(attributes, _attribute_resolver(attribute_type, "last_name"), None)
    name.middleName = get_string_value(attributes, _attribute_resolver(attribute_type, "middle_name"), None)
    return name


def _attribute_resolver(attribute_type: AttributeType, attribute_name: str) -> str:
    return f"{attribute_type.prefix}_{attribute_name}"


def get_aliases_from_map(attributes: dict[str, InputAttribute], prefix: str, primary_name: NameEntity) -> list[NameEntity]:
    """S:NameUtils.java:163. Every other non-blank `<prefix>..._name` column is an alias; repeats and the primary name are dropped."""
    return get_unique_aliases(primary_name, _get_aliases(attributes, prefix))


def _get_aliases(attributes: dict[str, InputAttribute], prefix: str) -> list[NameEntity]:
    non_aliases = _INPUT_NON_ALIASES if prefix == INPUT else _WLE_NON_ALIASES
    return [
        NameEntity(fullName=attribute.value)
        for key, attribute in attributes.items()
        if key.startswith(prefix) and key.endswith(NAME_POSTFIX) and key not in non_aliases and is_not_blank(attribute.value)
    ]


def get_unique_aliases(primary_name: NameEntity, aliases: list[NameEntity]) -> list[NameEntity]:
    """S:NameUtils.java:182. First alias of each full name (case-sensitive), minus any equal to the primary name by equalsIgnoreCase.

    Java groups into a HashMap, so its order is arbitrary (D-8); here it is the order of first appearance.
    Nulls, as in Java (OpenJDK 21.0.12.1): an alias without a full name is a NullPointerException ("element cannot be mapped
    to a null key", from Collectors.groupingBy, S:NameUtils.java:184-187); a primary name without one is no error, because
    equalsIgnoreCase(null) is false, so every alias stays. Neither happens on the CSV path: _get_aliases only builds aliases from non-blank text.
    """
    first_by_full_name: dict[str, NameEntity] = {}
    for alias in aliases:
        if alias.fullName is None:
            raise TypeError("element cannot be mapped to a null key")
        first_by_full_name.setdefault(alias.fullName, alias)
    primary = primary_name.fullName
    return [alias for alias in first_by_full_name.values() if not equals_ignore_case(alias.fullName, primary)]
