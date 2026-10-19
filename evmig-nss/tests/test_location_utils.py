# Ports LocationUtilsTest (names-screening-schema .../nss/LocationUtilsTest.java), the methods the CSV path calls.
from evmig_nss.schema import location_utils
from evmig_nss.schema.models import Location, LocationEntity
from helpers import attrs, unordered_equal


def test_get_locations():  # ports LocationUtilsTest.java:51 getLocations
    cells = {
        "input_address_1_country": "USA", "input_address_1_state": "Alaska",
        "input_address_2_country": "CA", "input_address_2_city": "Vancouver",
        "input_address_3_full": "IR, Dublin, Grafton Street", "input_address_4_street": "12345 Main avenue",
    }  # fmt: skip
    actual = location_utils.get_location_entities(attrs(cells), "input")
    expected = [
        Location(country="USA", state="Alaska"),
        Location(country="CA", city="Vancouver"),
        Location(address="IR, Dublin, Grafton Street"),
        Location(street="12345 Main avenue"),
    ]
    assert len(actual) == 4
    assert unordered_equal([e.original for e in actual], expected)


# ---- own tests ----


def test_locations_are_grouped_by_index_and_keep_the_row_order():
    cells = {"input_address_2_city": "Dallas", "input_address_1_city": "Austin", "input_address_2_state": "TX", "input_address_1_type": "home"}
    actual = location_utils.get_location_entities(attrs(cells), "input")
    assert [e.original for e in actual] == [Location(city="Dallas", state="TX"), Location(type="home", city="Austin")]


def test_an_index_counts_only_when_one_of_its_cells_is_not_blank_and_a_blank_sibling_cell_is_kept_as_empty_text():
    cells = {"hit_address_1_country": "  ", "hit_address_2_country": "PL", "hit_address_2_city": " ", "input_address_3_country": "NO"}
    actual = location_utils.get_location_entities(attrs(cells), "hit")
    assert [e.original for e in actual] == [Location(country="PL", city="")]  # city: the cell exists but is blank -> ""; index 1 and the input_ column are out


def test_validate_location_wle_needs_a_location_with_street_city_state_country_or_address():
    with_type_only = [LocationEntity(original=Location(type="home"))]
    with_city = [LocationEntity(original=Location(type="home")), LocationEntity(original=Location(city="Dallas"))]
    assert location_utils.validate_location_wle(with_city)
    assert not location_utils.validate_location_wle(with_type_only)  # type alone does not count
    assert not location_utils.validate_location_wle([])
    assert not location_utils.validate_location_wle(None)
