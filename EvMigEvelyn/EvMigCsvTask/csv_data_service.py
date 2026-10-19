"""The format file and the data file of csv-task: CSV text in, screened records out.

Ports (J = names-screening-jnw/src/main/java/com/workfusion/dw/nss, C = names-screening-core/src/main/java/com/workfusion/dw/nss/core):
  CsvDataService     J:task/csv/service/CsvDataService.java:42   `CsvDataService` below
  downloadS3Content  C:service/S3DownloadService.java:110        `CsvDataService.download_s3_content` (the bucket read is
                     the library's BucketStore.read_csv_text; the commons-csv parsing is `parse_csv` here)
  CSVRecord          commons-csv 1.14.1                          `CsvRecord`

Spring service <-> Python module: Java injects a logger and the S3 service into CsvDataService; here the class takes the
same two things in its constructor (a logger and a BucketStore). Java's `Map<ScreenedData, List<WleData>>` (ScreenedData
as a map key) becomes a list of (ScreenedData, [WleData]) pairs, because a pydantic model cannot be a dict key.
"""
import logging
from dataclasses import dataclass

from evmig_nss.core.bucket_store import BucketStore
from evmig_nss.core.configuration import (
    ENABLE_LOCATION_WLE_PATH,
    PROCEED_WITH_ERROR_DATA_PATH,
    Configuration,
    IllegalStateException,
)
from evmig_nss.core.constants import INPUT_ID, InputAttribute
from evmig_nss.core.strings import is_blank, java_trim
from evmig_nss.schema import screened_data_utils, wle_data_utils
from evmig_nss.schema.models import ScreenedData, WleData

from file_format_validation import validate_format

# The format file's columns (J:task/csv/service/CsvDataService.java:45-46).
CLIENT_COLUMN = 1
NSS_COLUMN = 0

# J:task/csv/service/CsvDataService.java:44
ERRORS_MESSAGE_FORMAT = "\n--------------/ERRORS/-----------------\n%s\n--------------/ERRORS/-----------------\n"


class InvalidInputException(Exception):
    """com.workfusion.dw.nss.exceptions.InvalidInputException: the format file is not usable."""


class DataException(Exception):
    """com.workfusion.dw.nss.exceptions.DataException: the details of the rows that could not be read.

    Java logs it as the "cause" of an error line; here it goes to `logger.error(..., exc_info=error)`.
    """


# ---- commons-csv ----


@dataclass
class CsvRecord:
    """One row of a CSV file (commons-csv CSVRecord).

    `record_number` counts the data rows from 1, a blank line included; the header row is not counted
    (CSVParser.java:565 `this.recordNumber = recordNumber - 1`, after the header was read).
    `header` maps a header name to its column; with a name twice, the last column wins (CSVParser.java:644 `headerMap.put(header, ...)`).
    """

    record_number: int
    values: list[str]
    header: dict[str, int]

    def get(self, index: int) -> str:
        # CSVRecord.get(int) is `values[i]`: a row that is too short raises ArrayIndexOutOfBoundsException, with this text.
        if not 0 <= index < len(self.values):
            raise IndexError(f"Index {index} out of bounds for length {len(self.values)}")
        return self.values[index]

    def to_map(self) -> dict[str, str]:
        """CSVRecord.toMap: header name -> value, only for the columns this row has (a short row gives fewer entries)."""
        return {name: self.values[column] for name, column in self.header.items() if column < len(self.values)}


def parse_csv(text: str) -> list[CsvRecord]:
    """Reads `text` as commons-csv does with the format of S3DownloadService.downloadS3Content.

    C:service/S3DownloadService.java:125-131: CSVFormat.EXCEL (comma, double quote, no escape character, empty lines are
    NOT skipped), the first row is the header, ignoreSurroundingSpaces. In commons-csv 1.14.1, EXCEL also allows trailing
    data after a closing quote and an end of file inside quotes. The rules, which the Python `csv` module only
    approximates (it does not trim the Unicode spaces that Java's Character.isWhitespace knows, and gives a blank
    line as an empty row):
      - leading white space of a field is dropped; trailing white space too, but only for a field that does not start
        with a quote (for a quoted one, anything after the closing quote up to the next comma is kept as it is);
      - `""` inside quotes is one quote; a quote inside a field that does not start with one is an ordinary character;
      - a line end is LF, CR or CRLF; one inside quotes is part of the value; a blank line is a row with one empty value;
      - a missing closing quote at the end of the file ends the field there (no error).
    That a file with a BOM has had it removed, and that a zero-byte file fails, is the library's read_csv_text.
    """
    rows = _read_rows(text)
    if not rows:
        return []
    header: dict[str, int] = {}
    for column, name in enumerate(rows[0]):
        header[name] = column
    return [CsvRecord(number, values, header) for number, values in enumerate(rows[1:], start=1)]


def _read_rows(text: str) -> list[list[str]]:
    # A port of commons-csv's Lexer.nextToken and CSVParser.nextRecord, for the one format above.
    rows: list[list[str]] = []
    row: list[str] = []
    pos, size = 0, len(text)
    after_comma = False  # the last field ended with a comma, so a field follows even at the end of the file
    while True:
        if pos >= size and not after_comma:
            return rows  # the end of the file, or a line end that was the last character: no more rows
        while pos < size and text[pos] not in ",\r\n" and is_blank(text[pos]):
            pos += 1  # leading white space (ignoreSurroundingSpaces)
        after_comma = False
        end_of_row = False
        value = ""
        if pos >= size:
            end_of_row = True  # white space, or a comma, and then the end of the file: an empty last field
        elif text[pos] == ",":
            pos += 1
            after_comma = True
        elif text[pos] in "\r\n":
            pos = _after_line_end(text, pos)
            end_of_row = True
        elif text[pos] == '"':
            value, pos, after_comma, end_of_row = _read_quoted(text, pos + 1)
        else:
            start = pos
            while pos < size and text[pos] not in ",\r\n":
                pos += 1
            value = text[start:pos]
            while value and is_blank(value[-1]):
                value = value[:-1]  # trailing white space of an unquoted field
            if pos >= size:
                end_of_row = True
            elif text[pos] == ",":
                pos += 1
                after_comma = True
            else:
                pos = _after_line_end(text, pos)
                end_of_row = True
        row.append(value)
        if end_of_row:
            rows.append(row)
            row = []


def _read_quoted(text: str, pos: int) -> tuple[str, int, bool, bool]:
    """The rest of a quoted field, `pos` being just after the opening quote. Returns (value, pos, after_comma, end_of_row)."""
    size = len(text)
    chars: list[str] = []
    while pos < size:
        char = text[pos]
        pos += 1
        if char != '"':
            chars.append(char)
        elif pos < size and text[pos] == '"':
            chars.append('"')
            pos += 1
        else:
            # The closing quote. Whatever follows, up to the next comma or line end, is added to the value as it is.
            while pos < size and text[pos] not in ",\r\n":
                chars.append(text[pos])
                pos += 1
            if pos >= size:
                return "".join(chars), pos, False, True
            if text[pos] == ",":
                return "".join(chars), pos + 1, True, False
            return "".join(chars), _after_line_end(text, pos), False, True
    return "".join(chars), pos, False, True  # no closing quote: the file ends inside the field


def _after_line_end(text: str, pos: int) -> int:
    # `pos` is at a CR or LF. CRLF is one line end.
    return pos + 2 if text.startswith("\r\n", pos) else pos + 1


# ---- CsvDataService ----


class CsvDataService:
    """J:task/csv/service/CsvDataService.java:42."""

    def __init__(self, logger: logging.Logger, store: BucketStore):
        self._logger = logger
        self._store = store

    def download_s3_content(self, file_path: str) -> list[CsvRecord]:
        """S3DownloadService.downloadS3Content (C:service/S3DownloadService.java:110): a bucket file as CSV rows.

        A tests' stand-in for the Java `when(s3DownloadService.downloadS3Content(...)).thenReturn(...)` replaces this method.
        """
        text = self._store.read_csv_text(file_path)  # the path checks, the BOM and "File ... is empty" are the library's
        # Java wraps IOException and IllegalStateException here as InvalidPathException(path, "S3 file content can not be
        # parsed: ..."), C:service/S3DownloadService.java:135-136. Nothing in the parsing can raise either: commons-csv 1.14.1
        # EXCEL allows trailing data and a missing closing quote at the end of the file, and allows missing and repeated header
        # names (checked on 56 inputs, tests/csv_parser_cases.py), and an in-memory text has no I/O error. So the wrapper is
        # ponytail: the wrapper is not ported; it is dead code in Java too, and a catch-all here would only hide bugs.
        return parse_csv(text)

    def map_file_format(self, format_file_location: str) -> dict[str, str]:
        """J:task/csv/service/CsvDataService.java:62. The format file as {client column: NSS column}, both lower-cased and trimmed.

        Rows whose client column is empty are skipped. A client column that occurs twice fails (Java's Collectors.toMap).
        """
        record_list = self.download_s3_content(format_file_location)
        result: dict[str, str] = {}
        for csv_record in record_list:
            if csv_record.get(CLIENT_COLUMN) == "":
                continue
            client_column = java_trim(csv_record.get(CLIENT_COLUMN).lower())
            nss_column = java_trim(csv_record.get(NSS_COLUMN).lower())
            if client_column in result:
                raise IllegalStateException(
                    f"Duplicate key {client_column} (attempted merging values {result[client_column]} and {nss_column})"
                )
            result[client_column] = nss_column
        self._validate_format(result)
        return result

    def map_data_file(
        self, data_file_location: str, format: dict[str, str], configuration: Configuration
    ) -> list[tuple[ScreenedData, list[WleData]]]:
        """J:task/csv/service/CsvDataService.java:74. The data file as one (alert, its hits) pair per alert that can proceed."""
        is_location_wle_enabled = configuration.get_required_boolean(ENABLE_LOCATION_WLE_PATH)
        proceed_with_errors = configuration.get_required_boolean(PROCEED_WITH_ERROR_DATA_PATH)
        record_list = self.download_s3_content(data_file_location)

        screened_data_map: dict[str, ScreenedData] = {}  # Java: a LinkedHashMap; a dict keeps insertion order too
        wles_by_input_id: dict[str, list[WleData]] = {}
        parsing_errors: dict[str, list[int | None]] = {}  # error text -> the line numbers it happened on
        failed_source_input_ids: set[str] = set()

        total_alerts_in_file = 0
        seen_input_ids_for_count: set[str] = set()

        for record in record_list:
            current_line = record.record_number
            formatted_row = self._format_row(record.to_map(), format)

            # An input_id that is missing or blank is None: such a row is its own alert.
            source_input_id = None
            input_id_attribute = formatted_row.get(INPUT_ID)
            if input_id_attribute is not None and java_trim(input_id_attribute.value) != "":
                source_input_id = input_id_attribute.value

            if source_input_id is not None:
                if source_input_id not in seen_input_ids_for_count:
                    seen_input_ids_for_count.add(source_input_id)
                    total_alerts_in_file += 1
            else:
                total_alerts_in_file += 1

            if source_input_id is not None and source_input_id in failed_source_input_ids:
                continue  # the first row of this alert was invalid: every row of it is skipped

            wle_errors_before = self._count_total_errors(parsing_errors)
            wle_data = wle_data_utils.transform_from_map(formatted_row, is_location_wle_enabled, current_line, parsing_errors, self._logger)
            wle_errors_after = self._count_total_errors(parsing_errors)
            is_wle_part_valid = wle_data is not None and wle_errors_after == wle_errors_before

            new_screened_data = None
            is_screened_data_part_valid = True
            definitive_id = None

            existing_screened_data = screened_data_map.get(source_input_id) if source_input_id is not None else None
            if existing_screened_data is None:
                sd_errors_before = self._count_total_errors(parsing_errors)
                new_screened_data = screened_data_utils.transform_from_map(formatted_row, current_line, parsing_errors)
                sd_errors_after = self._count_total_errors(parsing_errors)

                if sd_errors_after > sd_errors_before or new_screened_data is None:
                    is_screened_data_part_valid = False
                else:
                    definitive_id = new_screened_data.id
            else:
                definitive_id = existing_screened_data.id

            is_first_row_for_alert = existing_screened_data is None
            can_create_new_alert = is_first_row_for_alert and is_screened_data_part_valid and is_wle_part_valid

            if is_first_row_for_alert and not can_create_new_alert:
                if source_input_id is not None:
                    failed_source_input_ids.add(source_input_id)
            else:
                if can_create_new_alert:
                    screened_data_map[definitive_id] = new_screened_data
                    if source_input_id is not None and source_input_id != definitive_id:
                        screened_data_map[source_input_id] = new_screened_data

                if is_wle_part_valid and definitive_id is not None:
                    wles_by_input_id.setdefault(definitive_id, []).append(wle_data)

        return self._handle_parsing_completion(
            screened_data_map, wles_by_input_id, parsing_errors, proceed_with_errors, total_alerts_in_file
        )

    # ---- private ----

    def _format_row(self, row: dict[str, str], format: dict[str, str]) -> dict[str, InputAttribute]:
        """J:...CsvDataService.java:156. A data row keyed by the client's column names -> keyed by NSS column names.

        Columns the format file does not mention are dropped. Two columns that map to the same NSS name fail.
        """
        result: dict[str, InputAttribute] = {}
        for client_column, value in row.items():
            client_column = java_trim(client_column.lower())
            if client_column not in format:
                continue
            nss_column = format[client_column]
            attribute = InputAttribute(value, client_column)
            if nss_column in result:
                raise IllegalStateException(
                    f"Duplicate key {nss_column} (attempted merging values "
                    f"{_record_text(result[nss_column])} and {_record_text(attribute)})"
                )
            result[nss_column] = attribute
        return result

    @staticmethod
    def _count_total_errors(parsing_errors: dict[str, list[int | None]]) -> int:
        return sum(len(lines) for lines in parsing_errors.values())

    def _handle_parsing_completion(
        self,
        screened_data_map: dict[str, ScreenedData],
        wles_by_input_id: dict[str, list[WleData]],
        parsing_errors: dict[str, list[int | None]],
        proceed_with_errors: bool,
        total_alerts_in_file: int,
    ) -> list[tuple[ScreenedData, list[WleData]]]:
        """J:...CsvDataService.java:170. Logs the outcome and returns the alerts, or nothing when the file is to be dropped."""
        result_map = self._build_result_map(screened_data_map, wles_by_input_id)

        if not parsing_errors:
            self._logger.info(
                "Parsing completed. %s out of %s alerts will proceed to NSS main Business Process.", len(result_map), total_alerts_in_file
            )
            return result_map

        error_details = "\n".join(
            f"{error} on line(s): {','.join(str(line) for line in lines)}" for error, lines in parsing_errors.items()
        )
        error = DataException(ERRORS_MESSAGE_FORMAT % error_details)

        if proceed_with_errors:
            message = "Parsing completed. %s out of %s alerts will proceed to NSS main Business Process." % (
                len(result_map),
                total_alerts_in_file,
            )
            self._logger.error(message, exc_info=error)
            return result_map
        self._logger.error("Stopping processing due to parsing errors.", exc_info=error)
        return []

    @staticmethod
    def _build_result_map(
        screened_data_map: dict[str, ScreenedData], wles_by_input_id: dict[str, list[WleData]]
    ) -> list[tuple[ScreenedData, list[WleData]]]:
        # J:...CsvDataService.java:201. An alert can be in the map under two keys (its definitive id and the input id);
        # distinct() keeps it once, in the order it was created. No two alerts are equal (their uuids differ), so "the same
        # object" is the same as Java's "equal".
        result = []
        seen: set[int] = set()
        for screened_data in screened_data_map.values():
            if id(screened_data) not in seen:
                seen.add(id(screened_data))
                result.append((screened_data, wles_by_input_id.get(screened_data.id, [])))
        return result

    @staticmethod
    def _validate_format(mapped_file_format: dict[str, str]) -> None:
        errors = validate_format(mapped_file_format)
        if errors:
            raise InvalidInputException(f"Errors found: [{', '.join(errors)}]")  # Java prints a List as [a, b]


def _record_text(attribute: InputAttribute) -> str:
    # The text of a Java record (InputAttribute is one), used in the "Duplicate key" message: its fields as they are, untrimmed.
    return f"InputAttribute[value={attribute.raw_value}, clientColumn={attribute.client_column}]"
