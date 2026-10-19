"""Ports ScreenedDataUtils.transformFromMap (S:ScreenedDataUtils.java:43), the overload CsvDataService calls.

Skipped: transformFromMap(Map<String,String>, errors) (S:ScreenedDataUtils.java:33), enrichWithEntityType and
transformFromRequest (the REST request mapping): not reachable from the CSV path.
"""
import uuid

from evmig_nss.core.constants import (
    ALERT_GOLD_RESOLUTION,
    CLIENT_ID,
    INPUT,
    INPUT_ATTR_CASE_SYSTEM_ID,
    INPUT_CATEGORY,
    INPUT_ENTITY_TYPE,
    INPUT_GENDER,
    INPUT_ID,
    INPUT_RECORD_TYPE,
    AttributeType,
    InputAttribute,
)
from evmig_nss.core.strings import get_string_value
from evmig_nss.schema import additional_data_utils, date_utils, entity_type_utils, gender_utils, location_utils, name_utils
from evmig_nss.schema.error_utils import parse_field_and_record_error
from evmig_nss.schema.models import ScreenedData

_DEFAULT_CLIENT_ID = "1"


def transform_from_map(attributes: dict[str, InputAttribute], line_number: int | None, errors: dict[str, list[int | None]]) -> ScreenedData:
    """One CSV row (keys are NSS column names) -> ScreenedData.

    A cell that cannot be read is recorded in `errors` (error text -> line numbers) and its field is left empty;
    the caller counts the errors to decide whether the alert is usable. The uuid is new on every call.
    The calls run in Java's order, so `errors` fills in the same order: name, entity type, gender, dates.
    """
    name = name_utils.check_for_any_name_and_extract(attributes, AttributeType.INPUT)
    aliases_from_map = name_utils.get_aliases_from_map(attributes, INPUT, name)

    name_and_aliases = parse_field_and_record_error(
        lambda: name_utils.validate_name_presence(name, aliases_from_map, AttributeType.INPUT), "Name", line_number, errors
    )

    # Optional.ofNullable(map.get(a)).orElse(map.get(b)): a column named input_record_type wins over input_entity_type.
    entity_type_value = attributes.get(INPUT_RECORD_TYPE)
    if entity_type_value is None:
        entity_type_value = attributes.get(INPUT_ENTITY_TYPE)
    entity_type = None
    if entity_type_value is not None:
        entity_type = parse_field_and_record_error(
            lambda: entity_type_utils.from_string(entity_type_value, AttributeType.INPUT), "Entity type", line_number, errors
        )

    gender_value = attributes.get(INPUT_GENDER)
    gender = None
    if gender_value is not None:
        gender = parse_field_and_record_error(lambda: gender_utils.from_string(gender_value), "Gender", line_number, errors)

    dates = date_utils.get_date_entities(attributes, INPUT, line_number, errors)
    return ScreenedData(
        uuid=str(uuid.uuid4()),
        id=get_string_value(attributes, INPUT_ID, str(uuid.uuid4())),
        clientId=get_string_value(attributes, CLIENT_ID, _DEFAULT_CLIENT_ID),
        category=get_string_value(attributes, INPUT_CATEGORY, None),
        goldDecision=get_string_value(attributes, ALERT_GOLD_RESOLUTION, None),
        name=name_and_aliases[0] if name_and_aliases else None,
        entityType=entity_type,
        gender=gender,
        aliases=name_and_aliases[1] if name_and_aliases else None,
        dates=dates,
        locations=location_utils.get_location_entities(attributes, INPUT),
        identifiers=additional_data_utils.get_identifiers(attributes, INPUT),
        additionalData=additional_data_utils.get_additional_data(attributes, INPUT, INPUT_ATTR_CASE_SYSTEM_ID),
    )
