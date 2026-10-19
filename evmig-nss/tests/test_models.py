# Own tests: the pydantic models against the Gson behaviour of the generated Java classes (docs/mapping.md section 9).
import json

import pytest
from pydantic import ValidationError

from evmig_nss.schema.models import (
    DateEntity,
    DetailedDate,
    EntityType,
    Gender,
    Location,
    LocationEntity,
    NameEntity,
    ScreenedData,
    WleData,
)

SCREENED_KEYS = [
    "uuid", "id", "clientId", "category", "entityType", "gender", "name", "dates", "locations", "aliases",
    "identifiers", "additionalData", "goldDecision", "addToOngoingMonitor", "originalTransaction",
]  # fmt: skip
WLE_KEYS = ["uuid", "id", "category", "entityType", "gender", "name", "dates", "locations", "aliases", "identifiers", "additionalData", "goldDecision"]


def test_screened_data_has_the_15_java_field_names_and_the_generated_defaults():
    dumped = ScreenedData().model_dump()
    assert list(dumped) == SCREENED_KEYS
    assert dumped == {
        "uuid": None, "id": None, "clientId": "1", "category": None, "entityType": None, "gender": None, "name": None,
        "dates": [], "locations": [], "aliases": [], "identifiers": {}, "additionalData": {}, "goldDecision": None,
        "addToOngoingMonitor": False, "originalTransaction": None,
    }  # fmt: skip


def test_wle_data_has_the_12_java_field_names():
    assert list(WleData().model_dump()) == WLE_KEYS
    assert "clientId" not in WleData().model_dump()


def test_nested_types_have_the_yaml_fields():
    assert list(NameEntity().model_dump()) == ["fullName", "firstName", "lastName", "middleName", "derived", "source"]
    assert list(DetailedDate().model_dump()) == ["type", "full", "year", "month", "day"]
    assert list(DateEntity().model_dump()) == ["original", "derived", "source"]
    assert list(Location().model_dump()) == ["type", "country", "state", "city", "street", "address", "latitude", "longitude"]
    assert LocationEntity().model_dump() == {"original": None, "enriched": [], "source": None}


@pytest.mark.parametrize("mode", ["python", "json"])
def test_enums_dump_as_plain_strings_in_both_modes(mode):
    screened = ScreenedData(entityType=EntityType.INDIVIDUAL, gender=Gender.OTHER)
    dumped = screened.model_dump(mode=mode)
    assert dumped["entityType"] == "INDIVIDUAL" and type(dumped["entityType"]) is str
    assert dumped["gender"] == "OTHER" and type(dumped["gender"]) is str
    json.dumps(dumped)  # nothing but JSON types


def test_enum_assigned_later_is_stored_as_a_plain_string_too():
    screened = ScreenedData()
    screened.entityType = EntityType.LOCATION
    assert type(screened.model_dump()["entityType"]) is str
    assert screened.entityType == EntityType.LOCATION


def test_model_validate_reads_what_model_dump_wrote_and_ignores_unknown_keys():
    screened = ScreenedData(
        uuid="9F1C3B2A-1111-4222-8333-444455556666", id="A1", name=NameEntity(fullName="Alice Wonderland"),
        dates=[DateEntity(original=DetailedDate(full="2019", year="2019")), None],
        entityType=EntityType.ORGANIZATION, identifiers={"lei": "X"},
    )  # fmt: skip
    wire = json.loads(json.dumps(screened.model_dump(mode="json")))
    assert ScreenedData.model_validate({**wire, "somethingNew": 1}) == screened
    assert screened.uuid == "9f1c3b2a-1111-4222-8333-444455556666"  # Gson writes a UUID back in lower case


def test_a_key_absent_keeps_the_default_and_a_key_null_sets_none():
    assert ScreenedData.model_validate({}).clientId == "1"
    parsed = ScreenedData.model_validate({"clientId": None, "aliases": None, "addToOngoingMonitor": None})
    assert parsed.clientId is None and parsed.aliases is None and parsed.addToOngoingMonitor is None


def test_snake_case_keys_are_not_read_no_aliases():
    # The main BP's own schema copy spells clientId as client_id; this port reads Java's names only (docs/mapping.md section 9).
    parsed = ScreenedData.model_validate({"client_id": "7", "additional_data": {"a": "b"}})
    assert parsed.clientId == "1" and parsed.additionalData == {}


def test_a_uuid_field_refuses_a_non_uuid():
    with pytest.raises(ValidationError):
        ScreenedData(uuid="not-a-uuid")


def test_an_unknown_enum_name_is_refused():
    with pytest.raises(ValidationError):
        WleData(entityType="PERSON")


def test_the_models_describe_themselves_as_json_schema_with_the_java_names():
    # `uipath init` builds the function's input and output schema from models that contain these.
    schema = ScreenedData.model_json_schema()
    assert list(schema["properties"]) == SCREENED_KEYS
    assert list(WleData.model_json_schema()["properties"]) == WLE_KEYS
