# Ports DateUtilsTest (names-screening-schema .../nss/DateUtilsTest.java), the methods the CSV path calls.
import pytest

from evmig_nss.schema import date_utils
from evmig_nss.schema.exceptions import InvalidInputDataException, UnsupportedDateFormatException
from evmig_nss.schema.models import DateEntity, DetailedDate
from helpers import attrs

# (text, DetailedDate(type, full, year, month, day)), DateUtilsTest.java:25-54
EXPECTED_DATES = [
    ("2024", (None, "2024", "2024", None, None)),
    ("2024/00/00", (None, "2024", "2024", None, None)),
    ("2024/05/00", (None, "05/2024", "2024", "05", None)),
    ("3/2024", (None, "03/2024", "2024", "03", None)),
    ("12/2024", (None, "12/2024", "2024", "12", None)),
    ("12-2024", (None, "12/2024", "2024", "12", None)),
    ("3-2024", (None, "03/2024", "2024", "03", None)),
    ("12.2024", (None, "12/2024", "2024", "12", None)),
    ("3.2024", (None, "03/2024", "2024", "03", None)),
    ("1/3/2024", (None, "01/03/2024", "2024", "01", "03")),
    ("01/12/2024", (None, "01/12/2024", "2024", "01", "12")),
    ("11/18/2024", (None, "11/18/2024", "2024", "11", "18")),
    ("01-12-2024", (None, "01/12/2024", "2024", "01", "12")),
    ("1-1-2024", (None, "01/01/2024", "2024", "01", "01")),
    ("01.12.2024", (None, "01/12/2024", "2024", "01", "12")),
    ("1.2.2024", (None, "01/02/2024", "2024", "01", "02")),
    ("MAY 2001", (None, "05/2001", "2001", "05", None)),
    ("31 MAY 2001", (None, "05/31/2001", "2001", "05", "31")),
    ("25 JUNE 2001", (None, "06/25/2001", "2001", "06", "25")),
    ("2024/4", (None, "04/2024", "2024", "04", None)),
    ("2024/11", (None, "11/2024", "2024", "11", None)),
    ("20241213", (None, "12/13/2024", "2024", "12", "13")),
    ("2024/12/13", (None, "12/13/2024", "2024", "12", "13")),
    ("2024/4/1", (None, "04/01/2024", "2024", "04", "01")),
    ("2024-12-13", (None, "12/13/2024", "2024", "12", "13")),
    ("2024-4-1", (None, "04/01/2024", "2024", "04", "01")),
    ("2024*12*13", (None, "12/13/2024", "2024", "12", "13")),
    ("2024*4*1", (None, "04/01/2024", "2024", "04", "01")),
]


@pytest.mark.parametrize("date_str, expected", EXPECTED_DATES, ids=[d for d, _ in EXPECTED_DATES])
def test_get_dates(date_str, expected):  # ports DateUtilsTest.java:59 getDates
    type_, full, year, month, day = expected
    actual = date_utils.get_date_entities(attrs({"input_date_1": date_str}), "input", 1, {})
    assert actual[0].original == DetailedDate(type=type_, full=full, year=year, month=month, day=day)


@pytest.mark.parametrize("cells", [{}, {"": ""}], ids=["empty map", "blank key"])
def test_should_return_empty_list_when_wrong_date(cells):  # ports DateUtilsTest.java:76 shouldReturnEmptyListWhenWrongDate
    assert date_utils.get_date_entities(attrs(cells), "input", 1, {}) == []


@pytest.mark.parametrize("date", ["00/00/00", "0/00/00"])
def test_should_not_fail_on_parsing_date_entity(date):  # ports DateUtilsTest.java:93 shouldNotFailOnParsingDateEntity
    with pytest.raises(UnsupportedDateFormatException):
        date_utils.reformat_date(date)


@pytest.mark.parametrize("date_str", ["wrong_date", "2001 Feb 30", "19/02/2025"])
@pytest.mark.parametrize("client_column", [None, "client_column"])
def test_should_fail_on_impossible_date(date_str, client_column):  # ports DateUtilsTest.java:109 shouldFailOnImpossibleDate
    with pytest.raises(InvalidInputDataException) as raised:
        date_utils.from_string(date_str, None, client_column)
    assert raised.value.message == ("Failed to parse date: " + date_str if client_column is None else "client_column")


# ---- own tests ----


def test_get_date_entities_reads_the_type_column_and_records_a_bad_date_with_its_line():
    # Java: DateUtils.java:75-77. input_date_type_2 is the type of input_date_2; a bad date leaves None and an error on that line.
    cells = {"input_date_1": "2/25/2025", "input_date_type_1": "DOB", "input_date_2": "19/02/2025", "input_date_type_2": "X"}
    errors = {}
    actual = date_utils.get_date_entities(attrs(cells), "input", 7, errors)
    assert actual == [DateEntity(original=DetailedDate(type="DOB", full="02/25/2025", year="2025", month="02", day="25")), None]
    assert errors == {"Date parsing error in column (client_column)": [7]}


def test_get_date_entities_takes_a_hit_date_whose_name_has_a_word_before_the_number():
    cells = {"hit_date_full_1": "2019", "hit_date_type_1": "DOB"}  # the type key is hit_date_type_1
    (entity,) = date_utils.get_date_entities(attrs(cells), "hit", None, {})
    assert entity.original.type == "DOB" and entity.original.year == "2019"


def test_a_date_column_not_ending_in_digits_is_its_own_type_column():
    # Java's replaceAll leaves such a key unchanged, so the type is read from the date column itself (DateUtils.java:75).
    (entity,) = date_utils.get_date_entities(attrs({"input_date_full": "2019"}), "input", None, {})
    assert entity.original.type == "2019"


def test_the_error_has_no_line_number_when_none_is_given_and_no_client_column_text_when_blank():
    errors = {}
    date_utils.get_date_entities(attrs({"input_date_1": "nope"}, client_column=None), "input", None, errors)
    assert errors == {"Date parsing error in column (Failed to parse date: nope)": [None]}


def test_a_date_is_month_first():  # docs/mapping.md section 5.4: 06/10/1991 is 10 June
    (entity,) = date_utils.get_date_entities(attrs({"input_date_1": "06/10/1991"}), "input", 1, {})
    assert (entity.original.month, entity.original.day) == ("06", "10")


# Each text below was run through Evelyn's DateUtils.reformatDate code on JDK 21 (SimpleDateFormat, non-lenient,
# Locale.ENGLISH, the regex table of DateUtils.java:33-50); None means it throws. Not Evelyn tests: they pin the cases the
# hand-written parser (_java_parse) could get wrong: month and day limits, leap years (Julian before 1582), the 1582
# calendar switch, month names ("sep" yes, "sept" no), year 0, trailing text ("2024/05/00"), non-ASCII digits.
JDK_VECTORS = [
    ('2024', '2024'),
    ('2024/00/00', '2024'),
    ('2024/05/00', '05/2024'),
    ('3/2024', '03/2024'),
    ('12/2024', '12/2024'),
    ('12-2024', '12/2024'),
    ('3-2024', '03/2024'),
    ('12.2024', '12/2024'),
    ('3.2024', '03/2024'),
    ('1/3/2024', '01/03/2024'),
    ('01/12/2024', '01/12/2024'),
    ('11/18/2024', '11/18/2024'),
    ('01-12-2024', '01/12/2024'),
    ('1-1-2024', '01/01/2024'),
    ('01.12.2024', '01/12/2024'),
    ('1.2.2024', '01/02/2024'),
    ('MAY 2001', '05/2001'),
    ('31 MAY 2001', '05/31/2001'),
    ('25 JUNE 2001', '06/25/2001'),
    ('2024/4', '04/2024'),
    ('2024/11', '11/2024'),
    ('20241213', '12/13/2024'),
    ('2024/12/13', '12/13/2024'),
    ('2024/4/1', '04/01/2024'),
    ('2024-12-13', '12/13/2024'),
    ('2024-4-1', '04/01/2024'),
    ('2024*12*13', '12/13/2024'),
    ('2024*4*1', '04/01/2024'),
    ('wrong_date', None),
    ('2001 Feb 30', None),
    ('19/02/2025', None),
    ('00/00/00', None),
    ('0/00/00', None),
    ('0000', None),
    ('0001', '0001'),
    ('0999', '0999'),
    ('2024/13/00', None),
    ('2024/0/00', None),
    ('2024/00', None),
    ('2024/13', None),
    ('13/2024', None),
    ('0/2024', None),
    ('00/2024', None),
    ('02/29/2024', '02/29/2024'),
    ('02/29/2023', None),
    ('02/29/1900', None),
    ('02/29/2000', '02/29/2000'),
    ('02/29/1500', '02/29/1500'),
    ('02/29/1700', None),
    ('10/05/1582', None),
    ('10/04/1582', '10/04/1582'),
    ('10/15/1582', '10/15/1582'),
    ('10/14/1582', None),
    ('04/31/2024', None),
    ('04/30/2024', '04/30/2024'),
    ('13/01/2024', None),
    ('1/32/2024', None),
    ('0/1/2024', None),
    ('1/0/2024', None),
    ('00/00/0000', None),
    ('01/01/0000', None),
    ('01/01/0001', '01/01/0001'),
    ('12/31/9999', '12/31/9999'),
    ('sept 2001', None),
    ('sep 2001', '09/2001'),
    ('Sep 2001', '09/2001'),
    ('sept. 2001', None),
    ('january 2001', '01/2001'),
    ('JANUARY 2001', '01/2001'),
    ('Jan 2001', '01/2001'),
    ('jan 2001', '01/2001'),
    ('may 2001', '05/2001'),
    ('mar 2001', '03/2001'),
    ('march 2001', '03/2001'),
    ('marc 2001', None),
    ('decem 2001', None),
    ('dec 2001', '12/2001'),
    ('decemberr 2001', None),
    ('5 jan 2001', '01/05/2001'),
    ('05 jan 2001', '01/05/2001'),
    ('5 January 2001', '01/05/2001'),
    ('31 feb 2001', None),
    ('29 feb 2024', '02/29/2024'),
    ('29 feb 2023', None),
    ('30 sept 2001', None),
    ('30 sep 2001', '09/30/2001'),
    ('1 sept 2001', None),
    ('2024/02/30', None),
    ('2024/2/29', '02/29/2024'),
    ('2024/2/30', None),
    ('20240230', None),
    ('20240229', '02/29/2024'),
    ('20230229', None),
    ('20241301', None),
    ('20240001', None),
    ('20240100', None),
    ('2024/0/1', None),
    ('2024/1/0', None),
    ('2024-1-0', None),
    ('2024*0*1', None),
    ('1.1.2024', '01/01/2024'),
    ('1.13.2024', '01/13/2024'),
    ('31.12.2024', None),
    ('4.2.2024', '04/02/2024'),
    ('2024/5/00', '05/2024'),
    ('99991231', '12/31/9999'),
    ('00010101', '01/01/0001'),
    ('00000101', None),
    ('5/2024', '05/2024'),
    ('05/2024', '05/2024'),
    (' 1/2024', None),
    ('1/2024 ', None),
    ('1/ 2024', None),
    ('٢٠٢٤', None),
    ('1/٣/2024', None),
]



@pytest.mark.parametrize("text, expected", JDK_VECTORS, ids=[repr(text) for text, _ in JDK_VECTORS])
def test_reformat_date_agrees_with_the_jdk(text, expected):
    if expected is None:
        with pytest.raises(UnsupportedDateFormatException, match="Failed to parse date: "):
            date_utils.reformat_date(text)
    else:
        assert date_utils.reformat_date(text) == expected
