"""Ports LocationUtils (S:LocationUtils.java:19), the methods the CSV path calls.

Skipped: locationToString, originalLocationToString, toString(Location), toManualTaskString (reports and manual
tasks) and getLocationEntities(List<Address>) (the REST request mapping).
"""
from evmig_nss.core.constants import ADDRESS_FIELD, InputAttribute
from evmig_nss.core.strings import is_not_blank
from evmig_nss.schema.models import Location, LocationEntity


def is_not_empty(location: Location) -> bool:
    """S:LocationUtils.java:71. At least one of street, city, state, country, address is non-empty (type does not count)."""
    return any(part for part in (location.street, location.city, location.state, location.country, location.address))


def get_location_entities(attributes: dict[str, InputAttribute], prefix: str) -> list[LocationEntity]:
    """S:LocationUtils.java:80. `<prefix>_address_<n>_<part>` columns -> one LocationEntity per distinct <n>.

    Not reproduced: a key such as `input_address__` makes Java's split("_")[0] fail with an index error;
    here the index is "".
    """
    start = prefix + ADDRESS_FIELD
    indexes = []  # distinct, in order of first appearance (Java: Stream.distinct())
    for key, attribute in attributes.items():
        if key.startswith(start) and is_not_blank(attribute.value):
            index = key.replace(start, "").split("_")[0]
            if index not in indexes:
                indexes.append(index)

    def part(location_prefix: str, suffix: str) -> str | None:
        attribute = attributes.get(location_prefix + suffix)
        return None if attribute is None else attribute.value

    entities = []
    for index in indexes:
        location_prefix = start + index
        entities.append(
            LocationEntity(
                original=Location(
                    type=part(location_prefix, "_type"),
                    country=part(location_prefix, "_country"),
                    state=part(location_prefix, "_state"),
                    city=part(location_prefix, "_city"),
                    street=part(location_prefix, "_street"),
                    address=part(location_prefix, "_full"),
                )
            )
        )
    return entities


def validate_location_wle(location_entities: list[LocationEntity] | None) -> bool:
    """S:LocationUtils.java:135. A location WLE needs at least one location with something in it."""
    return location_entities is not None and any(is_not_empty(entity.original) for entity in location_entities)
