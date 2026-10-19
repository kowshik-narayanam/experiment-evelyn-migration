# Ports NameUtilsTest (names-screening-schema .../nss/NameUtilsTest.java), the methods the CSV path calls.
import pytest

from evmig_nss.core.constants import AttributeType
from evmig_nss.schema import name_utils
from evmig_nss.schema.exceptions import InvalidInputDataException
from evmig_nss.schema.models import NameEntity
from helpers import attrs


def test_get_aliases_input():  # ports NameUtilsTest.java:18 getAliases_input
    cells = {
        "input_full_name": "full name", "input_second_name": "full name", "input_first_name": "first name",
        "input_last_name": "last name", "input_alias_name": "alias", "input_alias2_name": "", "input_alias3_name": None,
        "input_address_1_country": "Vancouver",
    }  # fmt: skip
    actual = name_utils.get_aliases_from_map(attrs(cells), "input", NameEntity(fullName="full name"))
    assert [a.fullName for a in actual] == ["alias"]  # input_second_name repeats the primary name, blank ones are no alias


def test_get_aliases_input_wle():  # ports NameUtilsTest.java:41 getAliases_input_wle
    cells = {
        "hit_matched_name": "full name", "hit_second_name": "full name", "hit_first_name": "first name",
        "hit_last_name": "last name", "hit_alias_name": "alias", "hit_alias2_name": "", "hit_alias3_name": None,
        "hit_address_1_country": "Vancouver",
    }  # fmt: skip
    actual = name_utils.get_aliases_from_map(attrs(cells), "hit", NameEntity(fullName="full name"))
    assert [a.fullName for a in actual] == ["alias"]


# ---- own tests ----


def test_unique_aliases_keep_the_first_of_each_full_name_in_row_order_and_drop_the_primary_name_ignoring_case():
    # Java builds a HashMap here, so its order is arbitrary (D-8); the port keeps the order of first appearance.
    aliases = [NameEntity(fullName=n) for n in ["Bravo", "alice wonderland", "Alpha", "Bravo", "ALICE WONDERLAND", "Alpha "]]
    actual = name_utils.get_unique_aliases(NameEntity(fullName="Alice Wonderland"), aliases)
    assert [a.fullName for a in actual] == ["Bravo", "Alpha", "Alpha "]  # grouping is case-sensitive, the primary-name test is not


def test_unique_aliases_with_a_primary_name_that_has_no_full_name_drop_nothing():
    actual = name_utils.get_unique_aliases(NameEntity(firstName="John"), [NameEntity(fullName="John Doe")])
    assert [a.fullName for a in actual] == ["John Doe"]


# The next tests use spelling variants of one placeholder name that Java's equalsIgnoreCase treats as equal and
# `a.lower() == b.lower()` does not. Confirmed on OpenJDK 21.0.12.1 (2026-10-19) by running the stream of
# NameUtils.getUniqueAliases (S:NameUtils.java:182-193) on the same names; see tests/test_strings.py for the characters.


def test_unique_aliases_drop_the_spelling_variants_that_java_calls_equal_to_the_primary_name():
    primary = NameEntity(fullName="Gill Bates")
    variants = ["GILL BATE\u017f", "G\u0130LL BATES", "G\u0131ll Bates", "GILL BATES", "gill bates"]  # long s, dotted I, dotless i, upper, lower
    not_equal = ["Gill Bates ", "Gill Bate", "Gil Bates"]
    actual = name_utils.get_unique_aliases(primary, [NameEntity(fullName=n) for n in [*variants, *not_equal]])
    assert [a.fullName for a in actual] == not_equal


def test_unique_aliases_drop_a_greek_alias_whose_sigmas_differ_only_in_case_or_in_final_form():
    primary = NameEntity(fullName="\u0393\u03ba\u03b9\u03bb \u039c\u03c0\u03b5\u03b9\u03c4\u03c3")  # "Γκιλ Μπειτσ", plain sigma at the end
    final_sigma = "\u0393\u03ba\u03b9\u03bb \u039c\u03c0\u03b5\u03b9\u03c4\u03c2"  # "Γκιλ Μπειτς", final sigma
    capitals = "\u0393\u039a\u0399\u039b \u039c\u03a0\u0395\u0399\u03a4\u03a3"  # "ΓΚΙΛ ΜΠΕΙΤΣ", capital sigma (str.lower() turns it into a final sigma)
    other = "\u0393\u03ba\u03b9\u03bb"  # "Γκιλ"
    actual = name_utils.get_unique_aliases(primary, [NameEntity(fullName=n) for n in [final_sigma, capitals, other]])
    assert [a.fullName for a in actual] == [other]
    # and the other way round: a final sigma in the primary name
    actual = name_utils.get_unique_aliases(NameEntity(fullName=final_sigma), [NameEntity(fullName=n) for n in [primary.fullName, other]])
    assert [a.fullName for a in actual] == [other]


def test_get_aliases_from_map_drops_an_alias_spelt_like_the_primary_name_with_a_long_s():
    cells = attrs({"input_full_name": "Gill Bates", "input_alias_1_name": "GILL BATE\u017f", "input_alias_2_name": "John Doe"})
    actual = name_utils.get_aliases_from_map(cells, "input", name_utils.check_for_any_name_and_extract(cells, AttributeType.INPUT))
    assert [a.fullName for a in actual] == ["John Doe"]


def test_unique_aliases_of_a_primary_name_without_full_name_keep_every_alias_as_java_does():
    # Java (OpenJDK 21.0.12.1): "x".equalsIgnoreCase(null) is false, no NullPointerException (S:NameUtils.java:191).
    actual = name_utils.get_unique_aliases(NameEntity(), [NameEntity(fullName="Gill Bates"), NameEntity(fullName="GILL BATES")])
    assert [a.fullName for a in actual] == ["Gill Bates", "GILL BATES"]


@pytest.mark.parametrize("primary", [NameEntity(fullName="Gill Bates"), NameEntity()], ids=["primary named", "primary without full name"])
def test_unique_aliases_with_an_alias_without_full_name_fail_like_javas_group_by(primary):
    # Java (OpenJDK 21.0.12.1): Collectors.groupingBy throws NullPointerException "element cannot be mapped to a null key"
    # (S:NameUtils.java:184-187), before the filter, whatever the primary name is. Not reachable from a CSV row:
    # _get_aliases only makes aliases from non-blank text.
    with pytest.raises(TypeError, match="element cannot be mapped to a null key"):
        name_utils.get_unique_aliases(primary, [NameEntity(fullName="John Doe"), NameEntity()])


def test_check_for_any_name_reads_input_full_name_or_hit_matched_name():
    cells = attrs({"input_full_name": " John Doe ", "input_first_name": "John", "hit_matched_name": "Gill Bates", "input_middle_name": " "})
    assert name_utils.check_for_any_name_and_extract(cells, AttributeType.INPUT) == NameEntity(fullName="John Doe", firstName="John")
    assert name_utils.check_for_any_name_and_extract(cells, AttributeType.HIT) == NameEntity(fullName="Gill Bates")


def test_validate_name_presence_accepts_any_one_name_part_or_any_alias():
    aliases = [NameEntity(fullName=" ")]
    assert name_utils.validate_name_presence(NameEntity(middleName="M"), aliases, AttributeType.INPUT)[0].middleName == "M"
    assert name_utils.validate_name_presence(NameEntity(), [NameEntity(fullName="A")], AttributeType.HIT)[1][0].fullName == "A"


@pytest.mark.parametrize("attribute_type, text", [(AttributeType.INPUT, "missing input names"), (AttributeType.HIT, "missing hit names")])
@pytest.mark.parametrize("aliases", [None, [], [NameEntity(fullName="  ")]])
def test_validate_name_presence_raises_when_nothing_is_named(attribute_type, text, aliases):
    with pytest.raises(InvalidInputDataException) as raised:
        name_utils.validate_name_presence(NameEntity(fullName=" "), aliases, attribute_type)
    assert raised.value.message == text
