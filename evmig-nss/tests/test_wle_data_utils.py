# Ports WleDataUtilsTest (names-screening-schema .../nss/WleDataUtilsTest.java), the map tests.
import logging
import uuid

import pytest

from evmig_nss.core.constants import (
    HIT_CATEGORY,
    HIT_FIRST_NAME,
    HIT_GENDER,
    HIT_GOLD_RESOLUTION,
    HIT_ID,
    HIT_LAST_NAME,
    HIT_MATCHED_NAME,
    HIT_MIDDLE_NAME,
    HIT_RECORD_TYPE,
)
from evmig_nss.schema import wle_data_utils
from evmig_nss.schema.models import DateEntity, DetailedDate, EntityType, Gender, Location, LocationEntity, NameEntity, WleData
from helpers import attrs

logger = logging.getLogger("test")


def transform(cells, enabled, errors=None, line=None):
    # Java's tests call the Map<String,String> overload, which wraps each value in an InputAttribute and calls this one
    # with no line number (S:WleDataUtils.java:33-41). That overload is not ported.
    return wle_data_utils.transform_from_map(attrs(cells, client_column=""), enabled, line, {} if errors is None else errors, logger)


@pytest.mark.parametrize("is_location_wle_enabled", [True, False])
def test_should_map_to_wle_data(is_location_wle_enabled):  # ports WleDataUtilsTest.java:65 shouldMapToWleData
    hit = {
        HIT_ID: "64ce60bb-c082-4a4e-865f-118e5312c6a3", HIT_CATEGORY: "Category", HIT_RECORD_TYPE: EntityType.INDIVIDUAL.value,
        HIT_GENDER: Gender.FEMALE.value, HIT_MATCHED_NAME: "John Doe", HIT_FIRST_NAME: "John", HIT_LAST_NAME: "Doe",
        HIT_MIDDLE_NAME: "Middle", "hit_alias_name": "alias", "hit_date_full_1": "2019", "hit_address_1_full": "address",
        "hit_1_extdata": "ext data", HIT_GOLD_RESOLUTION: "1", "hit_one_identifier": "123",
    }  # fmt: skip

    wle_data = transform(hit, is_location_wle_enabled)

    assert wle_data == WleData(
        uuid=wle_data.uuid,
        id="64ce60bb-c082-4a4e-865f-118e5312c6a3",
        name=NameEntity(fullName="John Doe", firstName="John", lastName="Doe", middleName="Middle"),
        gender=Gender.FEMALE,
        category="Category",
        entityType=EntityType.INDIVIDUAL,
        aliases=[NameEntity(fullName="alias")],
        locations=[LocationEntity(original=Location(address="address"))],
        identifiers={"one": "123"},
        additionalData={"1": "ext data"},
        goldDecision="1",
        dates=[DateEntity(original=DetailedDate(full="2019", year="2019"))],
    )


def test_should_create_hit_id_when_missing_in_map():  # ports WleDataUtilsTest.java:99 shouldCreateHitIdWhenMissingInMap
    wle_data = transform({HIT_ID: ""}, False)
    assert uuid.UUID(wle_data.id)  # a random UUID text, never empty


def test_should_remove_duplicate_aliases_from_map():  # ports WleDataUtilsTest.java:163 shouldRemoveDuplicateAliasesFromMap
    hit_id = str(uuid.uuid4())
    cells = {HIT_ID: hit_id, "hit_matched_name": "John Doe", "hit_alias_name": "Alias name", "hit_alias2_name": "Alias name", "hit_alias3_name": "John Doe"}
    actual = transform(cells, False)
    assert actual == WleData(uuid=actual.uuid, id=hit_id, name=NameEntity(fullName="John Doe"), dates=[], locations=[], aliases=[NameEntity(fullName="Alias name")])


@pytest.mark.parametrize("is_location_wle_enabled", [True, False])
def test_should_handle_location_wle_from_map(is_location_wle_enabled):  # ports WleDataUtilsTest.java:223 shouldHandleLocationWleFromMap
    hit = {
        HIT_ID: "64ce60bb-c082-4a4e-865f-118e5312c6a3", HIT_CATEGORY: "Category", HIT_RECORD_TYPE: EntityType.LOCATION.value,
        HIT_GENDER: Gender.FEMALE.value, HIT_MATCHED_NAME: "John Doe", HIT_FIRST_NAME: "John", HIT_LAST_NAME: "Doe",
        HIT_MIDDLE_NAME: "Middle", "hit_alias_name": "alias", "hit_date_full_1": "2019", "hit_address_1_full": "address",
        "hit_1_extdata": "ext data", HIT_GOLD_RESOLUTION: "1", "hit_one_identifier": "123",
    }  # fmt: skip

    wle_data = transform(hit, is_location_wle_enabled)

    if is_location_wle_enabled:
        # Java compares recursively but ignores dates, name, gender, goldDecision and aliases (WleDataUtilsTest.java:253-260);
        # what is left, and asserted here, is id, category, entityType, locations, identifiers and additionalData.
        assert wle_data.id == "64ce60bb-c082-4a4e-865f-118e5312c6a3"
        assert wle_data.category == "Category"
        assert wle_data.entityType == EntityType.LOCATION
        assert wle_data.locations == [LocationEntity(original=Location(address="address"))]
        assert wle_data.identifiers == {} and wle_data.additionalData == {}  # a location WLE keeps neither
    else:
        assert wle_data is None


# ---- own tests ----


def test_location_wle_logs_evelyns_texts(caplog):
    caplog.set_level(logging.INFO, logger="test")
    with_address = {HIT_ID: "L1", HIT_RECORD_TYPE: "Location", "hit_address_1_country": "PL"}
    assert transform(with_address, True).id == "L1"
    assert caplog.messages == ["Parsing WLE L1 of type Location. Other pieces of information were ignored"]

    caplog.clear()
    assert transform({HIT_ID: "L2", HIT_RECORD_TYPE: "Location"}, True) is None  # enabled, but nothing to match on
    assert caplog.messages == [
        "Parsing WLE L2 of type Location. Other pieces of information were ignored",
        "Wle L2 of type Location didn't contain any location data.",
    ]

    caplog.clear()
    assert transform(with_address, False) is None
    assert caplog.messages == ["Wle L1 of type Location ignored as Location Wle matching is disabled."]


def test_a_hit_may_be_a_location_but_a_screened_alert_may_not():
    assert transform({HIT_ID: "L1", HIT_RECORD_TYPE: "LOCATION", "hit_address_1_full": "x"}, True).entityType == EntityType.LOCATION


def test_a_bad_hit_row_records_errors_with_its_line_and_still_returns_a_wle():
    errors = {}
    wle = transform({HIT_ID: "H1", HIT_RECORD_TYPE: "alien", "hit_date_1": "13/45/2020"}, True, errors, line=6)
    assert list(errors) == [
        "Name parsing error in column (missing hit names)",
        "Entity type parsing error in column",  # the column text is empty here, so no brackets
        "Date parsing error in column (Failed to parse date: 13/45/2020)",  # no column text: the reason is shown
    ]
    assert all(lines == [6] for lines in errors.values())
    assert wle.id == "H1" and wle.name is None and wle.aliases is None and wle.entityType is None and wle.dates == [None]
