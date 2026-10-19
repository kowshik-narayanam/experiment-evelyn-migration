# Own tests: the Java string rules the port relies on (String.trim, StringUtils.isBlank, String.equalsIgnoreCase).
import pytest

from evmig_nss.core.constants import InputAttribute
from evmig_nss.core.strings import equals_ignore_case, get_string_value, is_blank, java_trim


def test_java_trim_strips_control_characters_but_not_a_non_breaking_space():
    assert java_trim("\x00\x1f \t x \n") == "x"
    assert java_trim(" x ") == " x "  # trim() only strips up to U+0020


@pytest.mark.parametrize("text", [None, "", " ", "\t\n", " "])
def test_is_blank_true(text):
    assert is_blank(text)


@pytest.mark.parametrize("text", ["a", " a ", " ", "\u0085", " ", " "])
def test_is_blank_false_for_the_characters_java_does_not_call_whitespace(text):
    assert not is_blank(text)


def test_input_attribute_value_is_trimmed_and_none_stays_none():
    assert InputAttribute("  x\t", "c").value == "x"
    assert InputAttribute(None, "c").value is None
    assert InputAttribute("  x\t", "c").raw_value == "  x\t"


def test_get_string_value_default_for_absent_or_blank():
    cells = {"a": InputAttribute(" v ", "c"), "b": InputAttribute("   ", "c"), "n": InputAttribute(None, "c")}
    assert get_string_value(cells, "a", "dflt") == "v"
    assert get_string_value(cells, "b", "dflt") == "dflt"
    assert get_string_value(cells, "n", "dflt") == "dflt"
    assert get_string_value(cells, "missing", None) is None


# String.equalsIgnoreCase compares char by char with Character.toLowerCase(Character.toUpperCase(c)); str.lower() does not.
# Every expected value below was confirmed on OpenJDK 21.0.12.1 (java -version "21.0.12.1 2026-08-18", Homebrew) by calling
# a.equalsIgnoreCase(b) on the same strings (2026-10-19). The "lower() differs" column is str.lower() on this Python.
@pytest.mark.parametrize(
    "a, b, expected",
    [
        ("Gill Bates", "GILL BATES", True),
        ("Gill Bates", "gill bates", True),
        ("Gill Bates", "GILL BATE\u017f", True),  # U+017F long s: upper-cases to S (lower() differs)
        ("Gill Bates", "G\u0130LL BATES", True),  # U+0130 dotted capital I: Character.toLowerCase gives i (lower() gives i + U+0307)
        ("Gill Bates", "G\u0131ll Bates", True),  # U+0131 dotless i: upper-cases to I (lower() keeps it)
        ("\u03c3", "\u03c2", True),  # Greek sigma and final sigma (lower() keeps them apart)
        ("\u03a3", "\u03c2", True),  # capital sigma and final sigma
        ("\u03a3", "\u03c3", True),
        ("Stra\u00dfe", "STRASSE", False),  # ß does not expand to SS: the lengths differ
        ("Stra\u00dfe", "STRA\u1e9eE", True),  # ß and capital sharp S (U+1E9E)
        ("\u212a", "k", True),  # Kelvin sign
        ("\U00010400", "\U00010428", True),  # Deseret capital and small long I, outside the BMP
        ("Gill Bates", "Gill Bates ", False),  # no trimming
        ("Gill Bates", "Gill Bate", False),
        ("", "", True),
        ("a", None, False),  # Java: "a".equalsIgnoreCase(null) is false, not an error
        (None, None, True),  # not Java (a null receiver is a NullPointerException); the helper's own rule: null equals only null
        (None, "a", False),
    ],
)
def test_equals_ignore_case_is_javas_not_lower_case(a, b, expected):
    assert equals_ignore_case(a, b) is expected
    assert equals_ignore_case(b, a) is expected  # symmetric
