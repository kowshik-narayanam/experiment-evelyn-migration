"""Ports CsvDataServiceTest (18 methods; JT = names-screening-jnw/src/test/java/com/workfusion/dw/nss).

JT:task/csv/service/CsvDataServiceTest.java. Each test is named after its Java method and says where it is.
Java mocks the S3 service, the logger and the configuration (Mockito); here `service_serving` stubs the file read and the
logger is a real one that pytest's `caplog` records. `verify(loggerMock).error(message, exception)` becomes "one ERROR record
with this text, carrying a DataException".
"""
import logging

import pytest
from evmig_nss.schema.models import DateEntity, DetailedDate, Location, LocationEntity, NameEntity, ScreenedData, WleData

import csv_samples as samples
from helpers import LOGGER_NAME, error_lines, error_message, info_messages, make_configuration, service_serving, unordered_equal

PARSING_COMPLETED = "Parsing completed. %s out of %s alerts will proceed to NSS main Business Process."
STOPPING = "Stopping processing due to parsing errors."


@pytest.fixture(autouse=True)
def log_everything(caplog):
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)


def alerts_by_id(result):
    """The result as {alert id: (alert, hits)}: Java's tests look alerts up with e.getKey().getId()."""
    return {screened_data.id: (screened_data, wles) for screened_data, wles in result}


# ---- the format file ----


def test_mapFileFormat_correct():  # ports CsvDataServiceTest.java:77
    file_name = "csv/format-file/nss_correct_format.csv"
    service = service_serving({file_name: samples.NSS_CORRECT_FORMAT})

    actual = service.map_file_format(file_name)

    # Java asserts the size (9) and 7 of the entries; the two others are the date columns.
    assert actual == {
        "id": "input_id",
        "record_type": "input_record_type",
        "name": "input_full_name",
        "date": "input_date_1",
        "address": "input_address_1_country",
        "matched_name": "hit_matched_name",
        "other_name": "hit_primary_name",
        "matched_address": "hit_address_1_country",
        "matched_date": "hit_date_1",
    }


def test_mapFileFormat_incorrectFormatFile():  # ports CsvDataServiceTest.java:98
    file_name = "csv/format-file/nss_incorrect_format.csv"
    service = service_serving({file_name: samples.NSS_INCORRECT_FORMAT})

    with pytest.raises(Exception) as thrown:
        service.map_file_format(file_name)

    # Java: hasMessageContaining(...). The whole message is asserted here.
    assert str(thrown.value) == (
        "Errors found: ["
        "Format file should contain input_full_name mapping, "
        "Format file should contain input_id mapping, "
        "Format file should contain hit_matched_name mapping]"
    )


def test_mapFileFormat_emptyFile():  # ports CsvDataServiceTest.java:112
    file_name = "csv/empty.csv"
    service = service_serving({file_name: samples.EMPTY})

    with pytest.raises(Exception) as thrown:
        service.map_file_format(file_name)

    assert str(thrown.value) == (
        "Errors found: ["
        "Format file is empty, "
        "Format file should contain input_full_name mapping, "
        "Format file should contain input_id mapping, "
        "Format file should contain hit_matched_name mapping]"
    )


# ---- the data file: empty, or nothing usable ----


@pytest.mark.parametrize("file_name, text", [("csv/empty.csv", samples.EMPTY), ("csv/only_headers_file.csv", samples.ONLY_HEADERS_FILE)])
def test_mapDataFile_empty(file_name, text):  # ports CsvDataServiceTest.java:129
    service = service_serving({file_name: text})

    actual = service.map_data_file(file_name, {}, make_configuration())

    assert actual == []


def test_mapDataFile_Allerrors():  # ports CsvDataServiceTest.java:141
    # Java stubs nothing for "csv/data" (a folder), so the mock answers an empty list: no rows, no alerts.
    service = service_serving({})

    actual = service.map_data_file("csv/data", {}, make_configuration())

    assert actual == []


def test_mapDataFile_validateInputMerge():  # ports CsvDataServiceTest.java:153
    file_name = "csv/input-data-2-input-id-5-hits.csv"
    service = service_serving({file_name: samples.INPUT_DATA_2_INPUT_ID_5_HITS})
    format = {"id": "input_id", "name": "input_full_name", "matched_name": "hit_matched_name"}

    actual = service.map_data_file(file_name, format, make_configuration())

    # Rows 1, 3 and 4 are alert "1" and rows 2 and 5 are alert "2", although the rows are not next to each other.
    assert len(actual) == 2
    alerts = alerts_by_id(actual)
    assert len(alerts["1"][1]) == 3
    assert len(alerts["2"][1]) == 2


def test_shouldProceedWhenNameOrAliasPresent():  # ports CsvDataServiceTest.java:175
    file_name = "csv/combination-at-least-one-name-anywhere.csv"
    format = {
        "id": "input_id",
        "name": "input_full_name",
        "input_alias": "input_some_name",
        "input_first": "input_first_name",
        "input_middle": "input_middle_name",
        "input_last": "input_last_name",
        "hit_id": "hit_id",
        "matched_name": "hit_matched_name",
        "hit_first": "hit_first_name",
        "hit_middle": "hit_middle_name",
        "hit_last": "hit_last_name",
        "hit_alias": "hit_some_name",
    }
    service = service_serving({file_name: samples.COMBINATION_AT_LEAST_ONE_NAME_ANYWHERE})

    screened_data_list_map = service.map_data_file(file_name, format, make_configuration())

    assert len(screened_data_list_map) == 10


# ---- the data file: rows with errors ----


def test_shouldPrintLinesWithGeneralNamesMissingLines_onHitSide_processWithCorrectOff(caplog):  # ports CsvDataServiceTest.java:200
    file_name = "csv/input-data-no-input-and-hit-name.csv"
    format = {"id": "input_id", "name": "input_full_name", "first": "input_first_name", "matched_name": "hit_matched_name"}
    service = service_serving({file_name: samples.INPUT_DATA_NO_INPUT_AND_HIT_NAME})

    result = service.map_data_file(file_name, format, make_configuration(proceed_with_error_data=False))

    assert result == []
    assert error_message(caplog) == STOPPING
    name_errors = [line for line in error_lines(caplog) if line.startswith("Name parsing error")]
    assert sorted(name_errors) == sorted(
        [
            "Name parsing error in column (missing input names) on line(s): 1,4",
            "Name parsing error in column (missing hit names) on line(s): 2,4",
        ]
    )


def test_shouldPrintLinesWithGeneralNamesMissingLines_onHitSide_processWithCorrectOn(caplog):  # ports CsvDataServiceTest.java:230
    file_name = "csv/input-data-no-input-and-hit-name.csv"
    format = {"id": "input_id", "name": "input_full_name", "hit_id": "hit_id", "matched_name": "hit_matched_name"}
    service = service_serving({file_name: samples.INPUT_DATA_NO_INPUT_AND_HIT_NAME})

    result = service.map_data_file(file_name, format, make_configuration(proceed_with_error_data=True))

    assert len(result) == 1
    assert error_message(caplog) == "Parsing completed. 1 out of 4 alerts will proceed to NSS main Business Process."
    name_errors = [line for line in error_lines(caplog) if line.startswith("Name parsing error")]
    assert sorted(name_errors) == sorted(
        [
            "Name parsing error in column (missing input names) on line(s): 1,4",
            "Name parsing error in column (missing hit names) on line(s): 2,4",
        ]
    )


@pytest.mark.parametrize("proceed_with_error_data", [True, False])
def test_shouldProcessAllWhenNoErrors(proceed_with_error_data, caplog):  # ports CsvDataServiceTest.java:263
    file_name = "csv/input-data-2-input-id-5-hits.csv"
    format = {"id": "input_id", "name": "input_full_name", "matched_name": "hit_matched_name"}
    service = service_serving({file_name: samples.INPUT_DATA_2_INPUT_ID_5_HITS})

    result = service.map_data_file(file_name, format, make_configuration(proceed_with_error_data=proceed_with_error_data))

    # Java: verify(loggerMock).info("Parsing completed. {} out of {} ...", 2, 2)
    assert [m for m in info_messages(caplog) if m.startswith("Parsing completed")] == [PARSING_COMPLETED % (2, 2)]
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(result) == 2


@pytest.mark.parametrize(
    "proceed_with_error_data, expected_message",
    [
        (False, STOPPING),
        (True, "Parsing completed. 0 out of 3 alerts will proceed to NSS main Business Process."),
    ],
)
def test_shouldStopProcessingWhenAllRecordsHaveErrors(proceed_with_error_data, expected_message, caplog):  # ports CsvDataServiceTest.java:283
    file_name = "csv/input-all-names-missing.csv"
    format = {"id": "input_id", "name": "input_full_name", "matched_name": "hit_matched_name"}
    service = service_serving({file_name: samples.INPUT_ALL_NAMES_MISSING})

    result = service.map_data_file(file_name, format, make_configuration(proceed_with_error_data=proceed_with_error_data))

    assert result == []
    assert error_message(caplog) == expected_message
    name_errors = [line for line in error_lines(caplog) if line.startswith("Name parsing error")]
    assert name_errors == ["Name parsing error in column (missing hit names) on line(s): 1,2,3"]


def test_shouldProcessSomeRecordsWhenCombinationOfCorrectAndWrong(caplog):  # ports CsvDataServiceTest.java:317
    file_name = "csv/input-and-hit-data-combination-of-correct-and-wrong.csv"
    format = {"id": "input_id", "name": "input_full_name", "matched_name": "hit_matched_name"}
    service = service_serving({file_name: samples.INPUT_AND_HIT_DATA_COMBINATION_OF_CORRECT_AND_WRONG})

    result = service.map_data_file(file_name, format, make_configuration(proceed_with_error_data=True))

    assert error_message(caplog) == "Parsing completed. 5 out of 9 alerts will proceed to NSS main Business Process."
    assert len(result) == 5
    name_errors = [line for line in error_lines(caplog) if line.startswith("Name parsing error")]
    assert sorted(name_errors) == sorted(
        [
            "Name parsing error in column (missing input names) on line(s): 2,3",
            "Name parsing error in column (missing hit names) on line(s): 7,8",
        ]
    )


def test_shouldStopProcessingWhenCombinationOfCorrectAndWrong_whenProceedWithErrorDataFalse(caplog):  # ports CsvDataServiceTest.java:347
    file_name = "csv/input-and-hit-data-combination-of-correct-and-wrong.csv"
    format = {"id": "input_id", "name": "input_full_name", "matched_name": "hit_matched_name"}
    service = service_serving({file_name: samples.INPUT_AND_HIT_DATA_COMBINATION_OF_CORRECT_AND_WRONG})

    result = service.map_data_file(file_name, format, make_configuration(proceed_with_error_data=False))

    assert error_message(caplog) == STOPPING
    assert result == []
    name_errors = [line for line in error_lines(caplog) if line.startswith("Name parsing error")]
    assert sorted(name_errors) == sorted(
        [
            "Name parsing error in column (missing input names) on line(s): 2,3",
            "Name parsing error in column (missing hit names) on line(s): 7,8",
        ]
    )


def test_shouldCorrectlyMapMultipleHitsToOneScreenedData(caplog):  # ports CsvDataServiceTest.java:378
    file_name = "csv/multiple-hits-assigned-to-same-input.csv"
    format = {"id": "input_id", "name": "input_full_name", "matched_name": "hit_matched_name", "hit_id": "hit_id"}
    service = service_serving({file_name: samples.MULTIPLE_HITS_ASSIGNED_TO_SAME_INPUT})

    result = service.map_data_file(file_name, format, make_configuration(proceed_with_error_data=False))

    assert [m for m in info_messages(caplog) if m.startswith("Parsing completed")] == [PARSING_COMPLETED % (1, 1)]
    assert len(result) == 1
    assert [wle.id for wle in result[0][1]] == ["1", "2", "3", "4", "5"]  # not in Java's test: every hit was kept, in file order


# ---- the data file: every field ----


def full_format() -> dict[str, str]:
    """CsvDataServiceTest.fullFormat(), JT:...CsvDataServiceTest.java:548: client column -> NSS column."""
    format = {
        # input part
        "id": "input_id",
        "client_id": "client_id",
        "category": "input_category",
        "entity_type": "input_record_type",
        "gender": "input_gender",
        "name": "input_full_name",
        "first": "input_first_name",
        "middle": "input_middle_name",
        "last": "input_last_name",
        "date_1": "input_date_1",
        "date_type_1": "input_date_type_1",
        "date_2": "input_date_2",
        "date_type_2": "input_date_type_2",
        "address_1_type": "input_address_1_type",
        "address_1_country": "input_address_1_country",
        "address_1_state": "input_address_1_state",
        "address_1_city": "input_address_1_city",
        "address_1_full": "input_address_1_full",
        "aliases": "input_some_name",
        "identifiers": "input_identifier",
        "additional_data": "input_additional_info_extdata",
        "gold_decision": "alert_gold_resolution",
        # hit part
        "hit_id": "hit_id",
        "hit_category": "hit_category",
        "hit_entity_type": "hit_record_type",
        "hit_gender": "hit_gender",
        "hit_name": "hit_matched_name",
        "hit_first": "hit_first_name",
        "hit_middle": "hit_middle_name",
        "hit_last": "hit_last_name",
        "hit_date_1": "hit_date_1",
        "hit_date_type_1": "hit_date_type_1",
        "hit_date_2": "hit_date_2",
        "hit_date_type_2": "hit_date_type_2",
        "hit_address_1_type": "hit_address_1_type",
        "hit_address_1_country": "hit_address_1_country",
        "hit_address_1_state": "hit_address_1_state",
        "hit_address_1_city": "hit_address_1_city",
        "hit_address_1_full": "hit_address_1_full",
        "hit_aliases": "hit_some_name",
        "hit_identifiers": "hit_identifier",
        "hit_additional_data": "hit_additional_info_extdata",
        "hit_gold_decision": "hit_gold_resolution",
    }
    return format


def expected_data() -> tuple[ScreenedData, list[WleData]]:
    """CsvDataServiceTest.expectedData(), JT:...CsvDataServiceTest.java:428, with placeholder names."""
    dates = [
        DateEntity(original=DetailedDate(full="06/10/2140", day="10", month="06", year="2140", type="Death")),
        DateEntity(original=DetailedDate(full="06/10/1991", day="10", month="06", year="1991", type="DOB")),
    ]
    name = NameEntity(fullName="Alice Wonderland", firstName="Alice", middleName="Jane", lastName="Wonderland")
    screened_data = ScreenedData(
        id="11",
        clientId="111",
        category="ORGAN",
        entityType="INDIVIDUAL",
        gender="MALE",
        name=name,
        dates=dates,
        locations=[LocationEntity(original=Location(type="Home", country="USA", state="CS", city="California", address="Grove Street"))],
        aliases=[NameEntity(fullName="Ally Wonder")],
        identifiers={"identifier": "id = 1234 | PPSN = 54321000"},
        additionalData={"additional_info": "id = 1234 | Passport = 999"},
        goldDecision="1",
    )
    wle_data = WleData(
        id="12",
        category="ORGAN",
        entityType="INDIVIDUAL",
        gender="MALE",
        name=name,
        dates=dates,
        locations=[LocationEntity(original=Location(type="Home", country="USA", state="CS", city="California", address="Los Angeles"))],
        aliases=[NameEntity(fullName="Ally Wonder")],
        identifiers={"identifier": "id = 1234 | PPSN = 54321000"},
        additionalData={"additional_info": "id = 1234 | Passport = 999"},
        goldDecision="1",
    )
    return screened_data, [wle_data]


def test_shouldMapAllFieldsForScreenedAndWleData(caplog):  # ports CsvDataServiceTest.java:400
    file_name = "csv/all-records-correct.csv"
    service = service_serving({file_name: samples.ALL_RECORDS_CORRECT})

    result = service.map_data_file(file_name, full_format(), make_configuration())

    assert [m for m in info_messages(caplog) if m.startswith("Parsing completed")] == [PARSING_COMPLETED % (1, 1)]
    assert len(result) == 1
    (screened_data, wles), (expected_screened_data, expected_wles) = result[0], expected_data()
    # Java: usingRecursiveComparison().ignoringCollectionOrderInFields("dates", "identifiers").ignoringFields("additionalData", "uuid").
    # additionalData is compared here too. A uuid is generated, so it only has to be one.
    for actual, expected in [(screened_data, expected_screened_data), (wles[0], expected_wles[0])]:
        assert len(actual.uuid) == 36
        assert unordered_equal([d.model_dump() for d in actual.dates], [d.model_dump() for d in expected.dates])
        assert actual.model_dump(exclude={"uuid", "dates"}) == expected.model_dump(exclude={"uuid", "dates"})
    assert len(wles) == 1


def test_shouldLogErrorMessageWhenNoWLEsAvailableForProcessing(caplog):  # ports CsvDataServiceTest.java:474
    file_name = "csv/all-records-location-hit-type.csv"
    service = service_serving({file_name: samples.ALL_RECORDS_LOCATION_HIT_TYPE})

    result = service.map_data_file(file_name, full_format(), make_configuration())

    # Java: times(3) info "Wle {} of type Location ignored as Location Wle matching is disabled." for the ids 11, 12 and 13.
    ignored = sorted(m for m in info_messages(caplog) if m.startswith("Wle "))
    assert ignored == [f"Wle {i} of type Location ignored as Location Wle matching is disabled." for i in (11, 12, 13)]
    assert [m for m in info_messages(caplog) if m.startswith("Parsing completed")] == [PARSING_COMPLETED % (0, 3)]
    assert result == []


def test_shouldCorrectlyCountNumberOfRecordsWhenWleLocationsAreFilterOut(caplog):  # ports CsvDataServiceTest.java:491
    file_name = "csv/mixed-records-security-and-location-hit-type.csv"
    service = service_serving({file_name: samples.MIXED_RECORDS_SECURITY_AND_LOCATION_HIT_TYPE})

    result = service.map_data_file(file_name, full_format(), make_configuration())

    ignored = sorted(m for m in info_messages(caplog) if m.startswith("Wle "))
    assert ignored == [f"Wle {i} of type Location ignored as Location Wle matching is disabled." for i in (11, 12, 13)]
    assert [m for m in info_messages(caplog) if m.startswith("Parsing completed")] == [PARSING_COMPLETED % (4, 7)]
    assert len(result) == 4


@pytest.mark.parametrize(
    "proceed_with_correct_records, expected_message",
    [
        (True, "Parsing completed. 0 out of 5 alerts will proceed to NSS main Business Process."),
        (False, STOPPING),
    ],
)
def test_shouldAccumulateAllErrorsForScreenedAndWleData(proceed_with_correct_records, expected_message, caplog):  # ports CsvDataServiceTest.java:509
    file_name = "csv/all-records-failed.csv"
    service = service_serving({file_name: samples.ALL_RECORDS_FAILED})

    result = service.map_data_file(file_name, full_format(), make_configuration(proceed_with_error_data=proceed_with_correct_records))

    assert error_message(caplog) == expected_message
    assert result == []
    lines = [line for line in error_lines(caplog) if not line.startswith("--------------/ERRORS/-----------------") and line]
    assert sorted(lines) == sorted(
        [
            "Name parsing error in column (missing hit names) on line(s): 1,2,3,4,5",
            "Gender parsing error in column (hit_gender) on line(s): 1,2,3,4,5",
            "Entity type parsing error in column (hit_entity_type) on line(s): 1,2,3,4,5",
            "Entity type parsing error in column (entity_type) on line(s): 1,2,3,4,5",
            "Name parsing error in column (missing input names) on line(s): 1,2,3,4,5",
            "Gender parsing error in column (gender) on line(s): 1,2,3,4,5",
            "Date parsing error in column (hit_date_2) on line(s): 1,2,3,4,5",
            "Date parsing error in column (date_2) on line(s): 1,2,3,4,5",
            "Date parsing error in column (date_1) on line(s): 1,2,3,4,5",
            "Date parsing error in column (hit_date_1) on line(s): 1,2,3,4,5",
        ]
    )


# ---- not in the Java test class: rules of mapDataFile that the Java tests only touch in passing ----


def test_each_row_with_a_blank_input_id_is_its_own_alert(caplog):  # J:task/csv/service/CsvDataService.java:91-102
    data = "\n".join(["id,name,matched_name", ",Alice Wonderland,Alice Wonderland", " ,John Doe,John Doe", "7,Gill Bates,Gill Bates"])
    service = service_serving({"d.csv": data})
    format = {"id": "input_id", "name": "input_full_name", "matched_name": "hit_matched_name"}

    result = service.map_data_file("d.csv", format, make_configuration())

    assert [screened_data.name.fullName for screened_data, _ in result] == ["Alice Wonderland", "John Doe", "Gill Bates"]
    assert len({screened_data.id for screened_data, _ in result}) == 3  # the blank ones got generated ids, all different
    assert result[2][0].id == "7"
    assert [m for m in info_messages(caplog) if m.startswith("Parsing completed")] == [PARSING_COMPLETED % (3, 3)]


def test_the_input_id_is_trimmed_and_case_sensitive(caplog):  # J:task/csv/service/CsvDataService.java:91-96 (InputAttribute.value() trims)
    # A quoted value keeps its spaces in the CSV reader (an unquoted one is already trimmed there); InputAttribute.value() trims it.
    data = "\n".join(['id,name,matched_name', '" a ",Alice Wonderland,Alice Wonderland', 'A,Alice Wonderland,Alice Wonderland', 'a,John Doe,John Doe'])
    service = service_serving({"d.csv": data})
    format = {"id": "input_id", "name": "input_full_name", "matched_name": "hit_matched_name"}

    result = alerts_by_id(service.map_data_file("d.csv", format, make_configuration()))

    assert sorted(result) == ["A", "a"]
    assert [m for m in info_messages(caplog) if m.startswith("Parsing completed")] == [PARSING_COMPLETED % (2, 2)]  # two ids, not three
    assert len(result["a"][1]) == 2  # `" a "` and `a` are one alert, `A` another


def test_an_alert_that_is_stored_under_two_ids_is_returned_once(monkeypatch):  # J:task/csv/service/CsvDataService.java:142,202 (distinct())
    # CsvDataService stores an alert under its definitive id and, when that differs, under the input id too. They are
    # always equal with the real schema utils (both are the trimmed input_id), so the case is staged: the utils are made to
    # rename every alert.
    from evmig_nss.schema import screened_data_utils

    real = screened_data_utils.transform_from_map

    def renaming(attributes, line_number, errors):
        screened_data = real(attributes, line_number, errors)
        screened_data.id = "renamed-" + screened_data.id
        return screened_data

    monkeypatch.setattr(screened_data_utils, "transform_from_map", renaming)
    service = service_serving({"d.csv": samples.INPUT_DATA_2_INPUT_ID_5_HITS})
    format = {"id": "input_id", "name": "input_full_name", "matched_name": "hit_matched_name"}

    result = service.map_data_file("d.csv", format, make_configuration())

    assert [(screened_data.id, len(wles)) for screened_data, wles in result] == [("renamed-1", 3), ("renamed-2", 2)]


def test_a_failed_alert_swallows_its_later_rows_even_valid_ones(caplog):  # J:task/csv/service/CsvDataService.java:104-106,135-138
    data = "\n".join(["id,name,matched_name", "1,,Alice Wonderland", "1,Alice Wonderland,Alice Wonderland", "2,John Doe,John Doe"])
    service = service_serving({"d.csv": data})
    format = {"id": "input_id", "name": "input_full_name", "matched_name": "hit_matched_name"}

    result = service.map_data_file("d.csv", format, make_configuration())

    assert [screened_data.id for screened_data, _ in result] == ["2"]
    assert [m for m in info_messages(caplog) if "Parsing completed" in m] == []  # there was an error, so it is logged as one
    assert error_message(caplog) == PARSING_COMPLETED % (1, 2)


def test_a_later_invalid_hit_is_dropped_but_its_alert_stays(caplog):  # J:task/csv/service/CsvDataService.java:111,139-149
    data = "\n".join(["id,name,matched_name,hit_id", "1,Alice Wonderland,Alice Wonderland,H1", "1,Alice Wonderland,,H2", "1,Alice Wonderland,Alice Wonder,H3"])
    service = service_serving({"d.csv": data})
    format = {"id": "input_id", "name": "input_full_name", "matched_name": "hit_matched_name", "hit_id": "hit_id"}

    result = service.map_data_file("d.csv", format, make_configuration())

    assert [(screened_data.id, [wle.id for wle in wles]) for screened_data, wles in result] == [("1", ["H1", "H3"])]
    assert "Name parsing error in column (missing hit names) on line(s): 2" in error_lines(caplog)


def test_a_data_row_with_fewer_cells_than_the_header_has_the_missing_ones_absent(caplog):
    # commons-csv's toMap leaves them out, so the hit name is missing (not an empty string): the row is invalid.
    data = "\n".join(["id,name,matched_name", "1,Alice Wonderland"])
    service = service_serving({"d.csv": data})
    format = {"id": "input_id", "name": "input_full_name", "matched_name": "hit_matched_name"}

    result = service.map_data_file("d.csv", format, make_configuration())

    assert result == []
    assert "Name parsing error in column (missing hit names) on line(s): 1" in error_lines(caplog)


def test_columns_the_format_file_does_not_name_are_ignored():
    data = "\n".join(["id,name,matched_name,nobody_asked", "1,Alice Wonderland,Alice Wonderland,x"])
    service = service_serving({"d.csv": data})
    format = {"id": "input_id", "name": "input_full_name", "matched_name": "hit_matched_name"}

    result = service.map_data_file("d.csv", format, make_configuration())

    assert result[0][0].additionalData == {}


def test_header_names_are_matched_lower_cased_and_trimmed_and_the_format_file_is_too():
    format_file = 'nss_column,client_column\nInput_ID, " Alert ID "\n input_full_name ,NAME\nhit_matched_name,matched NAME\n'
    data = "\n".join(["ALERT id,name ,  Matched Name", "1,Alice Wonderland,Alice Wonderland"])
    service = service_serving({"f.csv": format_file, "d.csv": data})

    format = service.map_file_format("f.csv")
    result = service.map_data_file("d.csv", format, make_configuration())

    assert format == {"alert id": "input_id", "name": "input_full_name", "matched name": "hit_matched_name"}
    assert [screened_data.id for screened_data, _ in result] == ["1"]
