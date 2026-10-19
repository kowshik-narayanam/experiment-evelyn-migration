"""Ports AdditionalDataUtils (S:AdditionalDataUtils.java:19), the methods the CSV path calls.

Skipped: filterBlank (S:AdditionalDataUtils.java:71), used only by the REST request mapping.
Java builds a HashMap; the dicts here keep the order of the row (D-8).
"""
from evmig_nss.core.constants import EXT_DATA_POSTFIX, IDENTIFIERS_POSTFIX, InputAttribute
from evmig_nss.core.strings import equals_ignore_case, is_not_blank


def get_identifiers(identifiers: dict[str, InputAttribute], prefix: str) -> dict[str, str]:
    """S:AdditionalDataUtils.java:21. `<prefix>_<id>_identifier` columns -> {<id>: value}."""
    result = {}
    for key, attribute in identifiers.items():
        if is_not_blank(attribute.value) and key.startswith(prefix) and key.endswith(IDENTIFIERS_POSTFIX):
            result[_extract_identifiers(key, prefix).lower()] = attribute.value
    return result


def get_additional_data(attributes: dict[str, InputAttribute], *prefixes: str) -> dict[str, str]:
    """S:AdditionalDataUtils.java:30. `<prefix>_<id>_extdata` columns, and a column named exactly a prefix."""
    result = {}
    for key, attribute in attributes.items():
        if is_not_blank(attribute.value) and _matches_additional_data_conditions(key, prefixes):
            result[get_ext_data_id(key, *prefixes).lower()] = attribute.value
    return result


def _matches_additional_data_conditions(key: str, prefixes: tuple[str, ...]) -> bool:
    return any(equals_ignore_case(key, prefix) or (key.startswith(prefix) and key.endswith(EXT_DATA_POSTFIX)) for prefix in prefixes)


def _extract_identifiers(identifiers_key: str, *prefixes: str) -> str:
    # str.replace replaces every occurrence, as Java's String.replace does.
    for prefix in prefixes:
        if identifiers_key.startswith(prefix):
            identifiers_key = identifiers_key.replace(prefix + "_", "")
        identifiers_key = identifiers_key.replace(IDENTIFIERS_POSTFIX, "")
    return identifiers_key


def get_ext_data_id(ext_data_key: str, *prefixes: str) -> str:
    """S:AdditionalDataUtils.java:61."""
    for prefix in prefixes:
        if ext_data_key.startswith(prefix):
            ext_data_key = ext_data_key.replace(prefix + "_", "")
        ext_data_key = ext_data_key.replace(EXT_DATA_POSTFIX, "")
    return ext_data_key
