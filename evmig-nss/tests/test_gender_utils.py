# Ports GenderUtilsTest (names-screening-schema .../nss/GenderUtilsTest.java), the methods the CSV path calls.
import pytest

from evmig_nss.core.constants import InputAttribute
from evmig_nss.schema import gender_utils
from evmig_nss.schema.exceptions import InvalidInputDataException
from evmig_nss.schema.models import Gender


def test_from_string():  # ports GenderUtilsTest.java:13 fromString
    assert gender_utils.from_string(InputAttribute("male", None)) == Gender.MALE


def test_from_string_null():  # ports GenderUtilsTest.java:23 fromString_null
    assert gender_utils.from_string(InputAttribute(None, None)) is None


def test_from_string_not_supported():  # ports GenderUtilsTest.java:32 fromString_NotSupported
    with pytest.raises(InvalidInputDataException) as raised:
        gender_utils.from_string(InputAttribute("test", None))
    assert raised.value.message is None


def test_from_string_when_client_column_present():  # ports GenderUtilsTest.java:39 fromStringWhenClientColumnPresent
    assert gender_utils.from_string(InputAttribute("male", "client_column")) == Gender.MALE


def test_from_string_null_when_client_column_present():  # ports GenderUtilsTest.java:49 fromString_nullWhenClientColumnPresent
    assert gender_utils.from_string(InputAttribute(None, "client_column")) is None


def test_from_string_not_supported_when_client_column_present():  # ports GenderUtilsTest.java:58 fromString_NotSupportedWhenClientColumnPresent
    with pytest.raises(InvalidInputDataException) as raised:
        gender_utils.from_string(InputAttribute("test", "client_column"))
    assert raised.value.message == "client_column"


@pytest.mark.parametrize(
    "text, expected",
    [("M", Gender.MALE), ("f", Gender.FEMALE), (" Female ", Gender.FEMALE), ("OTHER", Gender.OTHER), ("other", Gender.OTHER), ("  ", None)],
)
def test_from_string_own_cases(text, expected):  # own: the M/F short forms and OTHER (S:GenderUtils.java:18-20)
    assert gender_utils.from_string(InputAttribute(text, "c")) == expected
