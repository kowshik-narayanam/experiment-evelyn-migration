"""Shared by the tests: build the dict of InputAttribute that Java's tests build with `new InputAttribute(...)`."""
from evmig_nss.core.constants import InputAttribute

# Java tests are under .../names-screening/names-screening-schema/src/test/java/com/workfusion/dw/nss/ (schema),
# .../names-screening-core/src/test/java/com/workfusion/dw/nss/core/service/ (S3DownloadServiceTest) and
# .../names-screening-jnw/src/test/java/com/workfusion/dw/nss/service/ (the two service tests).
# Every test below says `ports <JavaTestFile>:<line> <method>`.


def attrs(cells: dict, client_column: str | None = "client_column") -> dict[str, InputAttribute]:
    return {key: InputAttribute(value, client_column) for key, value in cells.items()}


def unordered_equal(actual: list, expected: list) -> bool:
    """Same items, any order. Java builds aliases, dates and locations in HashMap order; the port keeps the row's order (D-8)."""
    remaining = list(expected)
    for item in actual:
        if item not in remaining:
            return False
        remaining.remove(item)
    return not remaining
