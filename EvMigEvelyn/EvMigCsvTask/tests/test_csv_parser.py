"""parse_csv against what commons-csv 1.14.1 answers (the Java side of S3DownloadService.downloadS3Content).

There is no Java test for the parsing itself; the Java tests only feed it files. Python's `csv` module differs from
commons-csv in ways that change results (Unicode spaces around a field, a blank line, trailing spaces of an unquoted
header), so csv_data_service has its own reader. tests/csv_parser_cases.py holds 55 inputs with the answers the real library
gave, on a JDK 21 with the jar (see the file's header). Every case here would fail on Python's own csv module.
"""
import pytest

from csv_data_service import CsvRecord, parse_csv
from csv_parser_cases import CASES


@pytest.mark.parametrize("name, text, expected", CASES, ids=[case[0] for case in CASES])
def test_parse_csv_gives_what_commons_csv_gives(name, text, expected):
    records = parse_csv(text)

    assert [(r.record_number, r.values, list(r.to_map().items())) for r in records] == expected


def test_a_field_over_the_size_limit_of_pythons_csv_module_is_read():
    # Python's csv module stops at 131,072 characters per field; commons-csv has no limit.
    records = parse_csv("a,b\n" + "x" * 200_000 + ",2\n")

    assert len(records) == 1 and len(records[0].values[0]) == 200_000


def test_get_past_the_end_of_a_short_row_has_javas_message():
    # CSVRecord.get(1) on a row with one value: ArrayIndexOutOfBoundsException, message "Index 1 out of bounds for length 1".
    record = CsvRecord(1, ["input_id"], {"nss": 0})

    with pytest.raises(IndexError, match=r"^Index 1 out of bounds for length 1$"):
        record.get(1)


def test_to_map_leaves_out_the_columns_a_short_row_does_not_have():
    assert CsvRecord(1, ["1"], {"a": 0, "b": 1}).to_map() == {"a": "1"}
