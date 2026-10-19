"""Ports DateUtils (S:DateUtils.java:26) and the DateFormat record (S:DateFormat.java:4), the methods the CSV path calls.

Skipped: getDetailedDates, fromRequestDate, toString(DetailedDate) (reports and the REST request mapping).

Dates are month-first: `06/10/1991` is 10 June 1991. Java reads them with SimpleDateFormat in non-lenient mode;
_java_parse below reproduces what that does for the 18 regexps of DATE_FORMAT_REGEXPS (S:DateUtils.java:33-50), which use
16 distinct SimpleDateFormat patterns ("yyyy" and "yyyy/MM" each come from more than one regexp); checked against
a real JDK 21 over about 130 inputs, see tests/test_date_utils.py. Not reproduced: a date that does not exist
in the default time zone (for example 30 Dec 2011 in Pacific/Apia).
"""
import re
from functools import lru_cache
from typing import NamedTuple

from evmig_nss.core.constants import DATE_FIELD, DATE_TYPE_FIELD, InputAttribute
from evmig_nss.core.strings import is_blank, is_not_blank
from evmig_nss.schema.error_utils import parse_field_and_record_error
from evmig_nss.schema.exceptions import InvalidInputDataException, UnsupportedDateFormatException
from evmig_nss.schema.models import DateEntity, DetailedDate


class DateFormat(NamedTuple):
    format: str  # the SimpleDateFormat pattern the client's text is read with
    nss_format: str  # the pattern NSS writes it back with


_MM_DD_YYYY = "MM/dd/yyyy"
_MM_YYYY = "MM/yyyy"

# S:DateUtils.java:33-50. The first regex that matches the whole lower-cased text decides the format (dict order).
DATE_FORMAT_REGEXPS = {
    r"^\d{4}$": DateFormat("yyyy", "yyyy"),
    r"^\d{4}/00/00$": DateFormat("yyyy", "yyyy"),
    r"^\d{4}/\d{1,2}/00$": DateFormat("yyyy/MM", _MM_YYYY),
    r"^\d{1,2}/\d{4}$": DateFormat(_MM_YYYY, _MM_YYYY),
    r"^\d{1,2}-\d{4}$": DateFormat("MM-yyyy", _MM_YYYY),
    r"^\d{1,2}\.\d{4}$": DateFormat("MM.yyyy", _MM_YYYY),
    r"^\d{1,2}/\d{1,2}/\d{4}$": DateFormat(_MM_DD_YYYY, _MM_DD_YYYY),
    r"^\d{1,2}-\d{1,2}-\d{4}$": DateFormat("MM-dd-yyyy", _MM_DD_YYYY),
    r"^\d{1,2}\.\d{1,2}\.\d{4}$": DateFormat("MM.dd.yyyy", _MM_DD_YYYY),
    r"^[a-z]{3}\s\d{4}$": DateFormat("MMM yyyy", _MM_YYYY),
    r"^\d{1,2}\s[a-z]{3}\s\d{4}$": DateFormat("dd MMM yyyy", _MM_DD_YYYY),
    r"^[a-z]{4,}\s\d{4}$": DateFormat("MMMM yyyy", _MM_YYYY),
    r"^\d{1,2}\s[a-z]{4,}\s\d{4}$": DateFormat("dd MMMM yyyy", _MM_DD_YYYY),
    r"^\d{4}/\d{1,2}$": DateFormat("yyyy/MM", _MM_YYYY),
    r"^\d{4}\d{2}\d{2}$": DateFormat("yyyyMMdd", _MM_DD_YYYY),
    r"^\d{4}/\d{1,2}/\d{1,2}$": DateFormat("yyyy/MM/dd", _MM_DD_YYYY),
    r"^\d{4}-\d{1,2}-\d{1,2}$": DateFormat("yyyy-MM-dd", _MM_DD_YYYY),
    r"^\d{4}\*\d{1,2}\*\d{1,2}$": DateFormat("yyyy*MM*dd", _MM_DD_YYYY),
}
# re.ASCII: Java's \d and \s match ASCII only by default, Python's match Unicode digits and spaces.
_COMPILED_REGEXPS = [(re.compile(regexp, re.ASCII), date_format) for regexp, date_format in DATE_FORMAT_REGEXPS.items()]


def get_date_entities(
    attributes: dict[str, InputAttribute], prefix: str, line_number: int | None, errors: dict[str, list[int | None]]
) -> list[DateEntity | None]:
    """S:DateUtils.java:64. `<prefix>_date_<x>_<n>` columns -> DateEntity; the type comes from `<prefix>_date_type_<n>`.

    A date that cannot be read is recorded in `errors` and leaves None in the list.
    """
    entities = []
    for key, attribute in attributes.items():
        if key.startswith(prefix + DATE_FIELD) and DATE_TYPE_FIELD not in key and is_not_blank(attribute.value):
            date_str = attribute.value
            # input_date_1 -> input_date_type_1; a key that does not end in digits maps to itself (Java replaceAll does the same).
            type_key = re.sub(r"^(.*)" + DATE_FIELD + r".*?(\d+)$", lambda m: m.group(1) + DATE_TYPE_FIELD + m.group(2), key, flags=re.ASCII)
            type_attribute = attributes.get(type_key)
            date_type = None if type_attribute is None else type_attribute.value
            entities.append(
                parse_field_and_record_error(
                    lambda: DateEntity(original=from_string(date_str, date_type, attribute.client_column)),
                    "Date",
                    line_number,
                    errors,
                )
            )
    return entities


def from_string(date_str: str, type: str | None, client_column: str | None) -> DetailedDate:
    """S:DateUtils.java:83. A date that cannot be read raises with the client column (or the reason) as message."""
    try:
        return _to_detailed_date(reformat_date(date_str), type)
    except UnsupportedDateFormatException as e:
        if is_blank(client_column):
            raise InvalidInputDataException(str(e)) from None
        raise InvalidInputDataException(client_column) from None


def reformat_date(date: str) -> str:
    """S:DateUtils.java:113. Any supported text -> NSS text: yyyy, MM/yyyy or MM/dd/yyyy."""
    if is_blank(date):
        return ""
    date_format = _determine_date_format(date)
    if date_format is None:
        raise UnsupportedDateFormatException("Failed to parse date: " + date)
    try:
        year, month, day = _java_parse(date_format.format, date)
    except ValueError:
        raise UnsupportedDateFormatException("Failed to parse date: " + date) from None
    return _java_format(date_format.nss_format, year, month, day)


def _determine_date_format(date_string: str) -> DateFormat | None:
    text = date_string.lower()
    return next((date_format for regexp, date_format in _COMPILED_REGEXPS if regexp.fullmatch(text)), None)


def _to_detailed_date(nss_format_date_str: str, type: str | None) -> DetailedDate | None:
    """S:DateUtils.java:159. NSS text -> year, month and day parts (month before day)."""
    parts = nss_format_date_str.split("/")
    if len(parts) == 1:
        return DetailedDate(type=type, full=nss_format_date_str, year=parts[0])
    if len(parts) == 2:
        return DetailedDate(type=type, full=nss_format_date_str, month=parts[0], year=parts[1])
    if len(parts) == 3:
        return DetailedDate(type=type, full=nss_format_date_str, month=parts[0], day=parts[1], year=parts[2])
    return None


# ---- SimpleDateFormat, non-lenient, Locale.ENGLISH ----

_MONTH_NAMES = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
# Java tries the full names, then the short ones ("sep", not "sept"), ignoring case.
_MONTHS = {**{name: i + 1 for i, name in enumerate(_MONTH_NAMES)}, **{name[:3]: i + 1 for i, name in enumerate(_MONTH_NAMES)}}
_PATTERN_TOKEN = re.compile(r"yyyy|MMMM|MMM|MM|dd|.")
_NUMBER_TOKENS = {"yyyy": ("year", 4), "MM": ("month", 2), "dd": ("day", 2)}


@lru_cache
def _pattern_regex(pattern: str) -> re.Pattern:
    tokens = _PATTERN_TOKEN.findall(pattern)
    parts = []
    for i, token in enumerate(tokens):
        if token in _NUMBER_TOKENS:
            name, width = _NUMBER_TOKENS[token]
            # Number fields glued together (yyyyMMdd) take exactly their width, others as many digits as there are.
            glued = i + 1 < len(tokens) and tokens[i + 1] in _NUMBER_TOKENS
            parts.append(f"(?P<{name}>\\d{{{width}}})" if glued else f"(?P<{name}>\\d+)")
        elif token in ("MMM", "MMMM"):
            parts.append("(?P<name>[A-Za-z]+)")
        else:
            parts.append(re.escape(token))
    return re.compile("".join(parts), re.ASCII)


def _java_parse(pattern: str, text: str) -> tuple[int, int, int]:
    """(year, month, day) of `text`, or ValueError. Like DateFormat.parse(String), text left over after the pattern is ignored."""
    match = _pattern_regex(pattern).match(text)
    if match is None:
        raise ValueError(text)
    fields = match.groupdict()
    year = int(fields["year"])
    month = _MONTHS.get(fields["name"].lower(), 0) if "name" in fields else int(fields.get("month") or 1)  # 0 fails the range check
    day = int(fields.get("day") or 1)
    if year < 1 or not 1 <= month <= 12 or not 1 <= day <= _days_in_month(year, month):
        raise ValueError(text)
    if (year, month) == (1582, 10) and 5 <= day <= 14:  # the days the calendar switch skipped
        raise ValueError(text)
    return year, month, day


def _days_in_month(year: int, month: int) -> int:
    # java.util.GregorianCalendar: Julian leap years up to 1582, Gregorian after.
    leap = year % 4 == 0 if year <= 1582 else year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    return [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]


def _java_format(pattern: str, year: int, month: int, day: int) -> str:
    return pattern.replace("yyyy", f"{year:04d}").replace("MM", f"{month:02d}").replace("dd", f"{day:02d}")
