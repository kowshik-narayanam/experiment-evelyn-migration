# Ports EntityTypeUtilsTest (names-screening-schema .../nss/EntityTypeUtilsTest.java), the methods the CSV path calls.
import pytest

from evmig_nss.core.constants import AttributeType, InputAttribute
from evmig_nss.schema import entity_type_utils
from evmig_nss.schema.exceptions import InvalidInputDataException
from evmig_nss.schema.models import EntityType


def test_from_string_with_client_column_present():  # ports EntityTypeUtilsTest.java:48 fromStringWithClientColumnPresent
    assert entity_type_utils.from_string(InputAttribute("individual", "client_column"), AttributeType.INPUT) == EntityType.INDIVIDUAL


def test_from_string_null_with_client_column_present():  # ports EntityTypeUtilsTest.java:60 fromString_nullWithClientColumnPresent
    assert entity_type_utils.from_string(InputAttribute(None, "client_column"), AttributeType.INPUT) is None


def test_from_string_not_supported_with_client_column_present():  # ports EntityTypeUtilsTest.java:72 fromString_NotSupportedWithClientColumnPresent
    with pytest.raises(InvalidInputDataException) as raised:
        entity_type_utils.from_string(InputAttribute("location", "client_column"), AttributeType.INPUT)
    assert raised.value.message == "client_column"


# ---- own tests: the conversions behind the three above (Java EntityTypeUtils.java:48-78) ----


@pytest.mark.parametrize(
    "text, parameter_type, expected",
    [
        ("Individual", AttributeType.INPUT, EntityType.INDIVIDUAL),
        ("ORGANISATION", AttributeType.INPUT, EntityType.ORGANIZATION),
        ("organization", AttributeType.HIT, EntityType.ORGANIZATION),
        ("Entity", AttributeType.INPUT, EntityType.ORGANIZATION),  # Thomson Reuters' word
        ("securities", AttributeType.INPUT, EntityType.SECURITIES),
        ("Location", AttributeType.HIT, EntityType.LOCATION),  # only a hit can be a location
        ("  individual  ", AttributeType.INPUT, EntityType.INDIVIDUAL),
        ("   ", AttributeType.HIT, None),
    ],
)
def test_from_string_conversions(text, parameter_type, expected):
    assert entity_type_utils.from_string(InputAttribute(text, "c"), parameter_type) == expected


@pytest.mark.parametrize("text", ["ENT\u0130TY", "ent\u0131ty", "EntitY", "entity"], ids=["dotted capital I", "dotless i", "mixed case", "lower case"])
def test_the_thomson_reuters_word_entity_is_matched_the_way_java_equals_ignore_case_does(text):
    # EntityTypeUtils.convertTrEntity (S:EntityTypeUtils.java:77): typeStr.equalsIgnoreCase("ENTITY"). U+0130 and U+0131 equal
    # I ignoring case in Java, so "ENTİTY" is ORGANIZATION; with str.lower() it was an unknown type (InvalidInputDataException).
    # Confirmed on OpenJDK 21.0.12.1 (2026-10-19): "ENT\u0130TY".equalsIgnoreCase("ENTITY") and "ent\u0131ty".equalsIgnoreCase("ENTITY") are true.
    assert entity_type_utils.from_string(InputAttribute(text, "c"), AttributeType.INPUT) == EntityType.ORGANIZATION
    assert entity_type_utils.from_string(InputAttribute(text, "c"), AttributeType.HIT) == EntityType.ORGANIZATION


def test_a_word_that_only_looks_like_entity_is_an_unknown_type():
    with pytest.raises(InvalidInputDataException):
        entity_type_utils.from_string(InputAttribute("ENTITIES", "type_column"), AttributeType.INPUT)


def test_from_string_none_attribute_is_none():
    assert entity_type_utils.from_string(None, AttributeType.INPUT) is None


def test_from_string_unknown_type_raises_with_the_client_column_or_none():
    with pytest.raises(InvalidInputDataException) as raised:
        entity_type_utils.from_string(InputAttribute("person", None), AttributeType.HIT)
    assert raised.value.message is None and str(raised.value) == ""


def test_to_string_is_the_enum_name_or_none():  # no Java test: J:service/AnalyticsService.java:56 calls EntityTypeUtils.toString
    assert entity_type_utils.to_string(EntityType.SECURITIES) == "SECURITIES"
    assert entity_type_utils.to_string("ORGANIZATION") == "ORGANIZATION"
    assert entity_type_utils.to_string(None) is None
