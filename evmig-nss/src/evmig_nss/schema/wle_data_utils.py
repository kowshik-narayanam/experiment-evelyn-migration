"""Ports WleDataUtils.transformFromMap (S:WleDataUtils.java:53), the overload CsvDataService calls.

Skipped: the two transformFromMap(Map<String,String>, ...) overloads, transformFromRequest and
transformFromFactivaMap (other inputs, not the CSV path).
"""
import logging
import uuid

from evmig_nss.core.constants import (
    HIT,
    HIT_CATEGORY,
    HIT_ENTITY_TYPE,
    HIT_GENDER,
    HIT_GOLD_RESOLUTION,
    HIT_ID,
    HIT_RECORD_TYPE,
    AttributeType,
    InputAttribute,
)
from evmig_nss.core.strings import get_string_value
from evmig_nss.schema import additional_data_utils, date_utils, entity_type_utils, gender_utils, location_utils, name_utils
from evmig_nss.schema.error_utils import parse_field_and_record_error
from evmig_nss.schema.models import EntityType, WleData


def transform_from_map(
    attributes: dict[str, InputAttribute],
    is_location_wle_enabled: bool,
    line_number: int | None,
    errors: dict[str, list[int | None]],
    logger: logging.Logger,
) -> WleData | None:
    """One CSV row (keys are NSS column names) -> WleData, or None for a LOCATION hit that is not used.

    Errors are recorded as in ScreenedDataUtils.transform_from_map. A LOCATION hit comes back with its
    locations only (no identifiers or additional data), and only when `is_location_wle_enabled` and it has a location.
    """
    name = name_utils.check_for_any_name_and_extract(attributes, AttributeType.HIT)
    aliases_from_map = name_utils.get_aliases_from_map(attributes, HIT, name)

    name_and_aliases = parse_field_and_record_error(
        lambda: name_utils.validate_name_presence(name, aliases_from_map, AttributeType.HIT), "Name", line_number, errors
    )

    entity_type_value = attributes.get(HIT_RECORD_TYPE)
    if entity_type_value is None:
        entity_type_value = attributes.get(HIT_ENTITY_TYPE)
    entity_type = None
    if entity_type_value is not None:
        entity_type = parse_field_and_record_error(
            lambda: entity_type_utils.from_string(entity_type_value, AttributeType.HIT), "Entity type", line_number, errors
        )

    gender_value = attributes.get(HIT_GENDER)
    gender = None
    if gender_value is not None:
        gender = parse_field_and_record_error(lambda: gender_utils.from_string(gender_value), "Gender", line_number, errors)

    wle_data = WleData(
        uuid=str(uuid.uuid4()),
        id=get_string_value(attributes, HIT_ID, str(uuid.uuid4())),
        category=get_string_value(attributes, HIT_CATEGORY, None),
        goldDecision=get_string_value(attributes, HIT_GOLD_RESOLUTION, None),
        name=name_and_aliases[0] if name_and_aliases else None,
        entityType=entity_type,
        gender=gender,
        aliases=name_and_aliases[1] if name_and_aliases else None,
        dates=date_utils.get_date_entities(attributes, HIT, line_number, errors),
        locations=location_utils.get_location_entities(attributes, HIT),
    )

    if entity_type == EntityType.LOCATION:
        return _handle_location_wle(is_location_wle_enabled, wle_data, logger)

    wle_data.identifiers = additional_data_utils.get_identifiers(attributes, HIT)
    wle_data.additionalData = additional_data_utils.get_additional_data(attributes, HIT)
    return wle_data


def _handle_location_wle(is_location_wle_enabled: bool, wle_data: WleData, logger: logging.Logger) -> WleData | None:
    """S:WleDataUtils.java:106. Log texts are Evelyn's, with %s where slf4j has {}."""
    if is_location_wle_enabled:
        logger.info("Parsing WLE %s of type Location. Other pieces of information were ignored", wle_data.id)
        if not location_utils.validate_location_wle(wle_data.locations):
            logger.info("Wle %s of type Location didn't contain any location data.", wle_data.id)
            return None
        return wle_data
    logger.info("Wle %s of type Location ignored as Location Wle matching is disabled.", wle_data.id)
    return None
