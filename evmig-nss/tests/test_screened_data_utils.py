# Ports ScreenedDataUtilsTest (names-screening-schema .../nss/ScreenedDataUtilsTest.java), the map tests.
import uuid

from evmig_nss.core.constants import INPUT_ID
from evmig_nss.schema import screened_data_utils
from evmig_nss.schema.models import (
    DateEntity,
    DetailedDate,
    EntityType,
    Gender,
    Location,
    LocationEntity,
    NameEntity,
    ScreenedData,
)
from helpers import attrs, unordered_equal


def test_should_transform_map_to_screened_data():  # ports ScreenedDataUtilsTest.java:25 shouldTransformMapToScreenedData
    cells = {
        "input_id": "123", "client_id": "321", "input_category": "category", "input_record_type": "INDIVIDUAL", "input_gender": "MALE",
        "input_full_name": "full name", "input_first_name": "first", "input_last_name": "last", "input_middle_name": "middle",
        "input_alias_name": "alias name", "input_date_type_1": "DOB", "input_date_1": "2/25/2025", "input_date_type_2": "SOME TYPE",
        "input_date_2": "1/2/2025", "input_some_additional_extdata": "ext_data", "input_case_system_id": "case_system_id",
        "input_some_identifier": "some_value", "input_address_1_type": "type", "input_address_1_country": "PL",
        "input_address_1_state": "Wonderland", "input_address_1_city": "KRK", "input_address_1_full": "Wonderland Street",
        "alert_gold_resolution": "1",
    }  # fmt: skip
    errors = {}

    actual = screened_data_utils.transform_from_map(attrs(cells), 1, errors)

    expected_dates = [
        DateEntity(original=DetailedDate(type="SOME TYPE", day="02", month="01", year="2025", full="01/02/2025")),
        DateEntity(original=DetailedDate(type="DOB", day="25", month="02", year="2025", full="02/25/2025")),
    ]
    expected = ScreenedData(
        uuid=actual.uuid,
        id="123",
        clientId="321",
        name=NameEntity(fullName="full name", firstName="first", lastName="last", middleName="middle"),
        locations=[LocationEntity(original=Location(city="KRK", address="Wonderland Street", country="PL", state="Wonderland", type="type"))],
        additionalData={"some_additional": "ext_data", "case_system_id": "case_system_id"},
        identifiers={"some": "some_value"},
        aliases=[NameEntity(fullName="alias name")],
        entityType=EntityType.INDIVIDUAL,
        gender=Gender.MALE,
        category="category",
        goldDecision="1",
        dates=actual.dates,  # compared below without order (Java's HashMap order, D-8)
    )
    assert actual == expected
    assert unordered_equal(actual.dates, expected_dates)
    assert errors == {}
    assert uuid.UUID(actual.uuid).version == 4


def test_should_remove_duplicate_aliases_from_map():  # ports ScreenedDataUtilsTest.java:207 shouldRemoveDuplicateAliasesFromMap
    input_id = str(uuid.uuid4())
    cells = {
        INPUT_ID: input_id, "input_full_name": "John Doe", "input_alias_name": "Alias name",
        "input_alias2_name": "Alias name", "input_alias3_name": "John Doe",
    }  # fmt: skip
    actual = screened_data_utils.transform_from_map(attrs(cells), 1, {})
    expected = ScreenedData(uuid=actual.uuid, id=input_id, name=NameEntity(fullName="John Doe"), dates=[], locations=[], aliases=[NameEntity(fullName="Alias name")])
    assert actual == expected


# ---- own tests: the parts of ScreenedDataUtils.transformFromMap no Java unit test pins ----


def test_defaults_when_the_row_has_only_a_name():
    actual = screened_data_utils.transform_from_map(attrs({"input_full_name": "Alice Wonderland"}), 1, {})
    assert actual.clientId == "1" and actual.addToOngoingMonitor is False and actual.originalTransaction is None
    assert actual.category is None and actual.goldDecision is None and actual.entityType is None and actual.gender is None
    assert uuid.UUID(actual.id)  # no input_id: a random one
    assert uuid.UUID(actual.uuid) != uuid.UUID(actual.id)


def test_a_blank_input_id_and_a_blank_client_id_fall_back_like_a_missing_one():
    cells = {"input_full_name": "Alice Wonderland", "input_id": "   ", "client_id": " "}
    actual = screened_data_utils.transform_from_map(attrs(cells), 1, {})
    assert uuid.UUID(actual.id) and actual.clientId == "1"


def test_input_record_type_wins_over_input_entity_type_but_a_blank_one_does_not_fall_through():
    both = {"input_full_name": "A", "input_record_type": "ORGANIZATION", "input_entity_type": "INDIVIDUAL"}
    assert screened_data_utils.transform_from_map(attrs(both), 1, {}).entityType == EntityType.ORGANIZATION
    blank_first = {"input_full_name": "A", "input_record_type": " ", "input_entity_type": "INDIVIDUAL"}
    assert screened_data_utils.transform_from_map(attrs(blank_first), 1, {}).entityType is None  # Optional.ofNullable sees a present, blank cell
    only_entity_type = {"input_full_name": "A", "input_entity_type": "securities"}
    assert screened_data_utils.transform_from_map(attrs(only_entity_type), 1, {}).entityType == EntityType.SECURITIES


def test_a_row_with_no_name_records_a_name_error_and_leaves_name_and_aliases_empty():
    errors = {}
    actual = screened_data_utils.transform_from_map(attrs({"input_id": "1"}), 4, errors)
    assert errors == {"Name parsing error in column (missing input names)": [4]}
    assert actual.name is None and actual.aliases is None  # Java sets null, not an empty list


def test_bad_cells_are_recorded_in_order_name_entity_type_gender_date_and_the_rest_is_still_parsed():
    cells = {
        "input_id": "9", "input_record_type": "person", "input_gender": "x", "input_date_1": "99/99/2020", "input_category": "kept",
    }  # fmt: skip
    errors = {}
    actual = screened_data_utils.transform_from_map(attrs(cells, client_column="the_column"), 2, errors)
    assert list(errors.items()) == [
        ("Name parsing error in column (missing input names)", [2]),
        ("Entity type parsing error in column (the_column)", [2]),
        ("Gender parsing error in column (the_column)", [2]),
        ("Date parsing error in column (the_column)", [2]),
    ]
    assert actual.entityType is None and actual.gender is None and actual.dates == [None]
    assert actual.id == "9" and actual.category == "kept"
