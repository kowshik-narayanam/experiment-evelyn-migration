"""The checks on the format file's mapping, run by csv_data_service.

Ports four small Java classes and the loop that runs them:
  DataSizeValidation                  J:utils/validation/rules/DataSizeValidation.java:16
  FileFormatInputFullNameValidator    J:utils/validation/rules/file/format/FileFormatInputFullNameValidator.java:17
  FileFormatInputIdValidator          J:utils/validation/rules/file/format/FileFormatInputIdValidator.java:17
  FileFormatHitMatchedNameValidator   J:utils/validation/rules/file/format/FileFormatHitMatchedNameValidator.java:17
  ValidationService.validateInputData J:utils/validation/ValidationService.java:20
(J = names-screening-jnw/src/main/java/com/workfusion/dw/nss.)

Java gives each check a class that implements an interface, and the loop calls them in a fixed order. Here each check is
a plain function that returns its error text, or None when the mapping is fine, and `validate_format` is the loop.
The `validate(AlertRequest)` method that each Java class also has (it throws NotImplementedException) is the REST input's,
so it is not ported.

`mapping` is the format file as csv_data_service.map_file_format builds it: {client column: NSS column}, both lower-cased
and trimmed.
"""
from evmig_nss.core.constants import HIT_MATCHED_NAME, INPUT_FULL_NAME, INPUT_ID


def data_size_validation(mapping: dict[str, str]) -> str | None:
    """DataSizeValidation.validate, J:...DataSizeValidation.java:16. Only the first problem that applies is reported."""
    if not mapping:
        return "Format file is empty"
    if all(is_blank_text(client_column) for client_column in mapping):
        return "Format file should contain mandatory client columns"
    if all(is_blank_text(nss_column) for nss_column in mapping.values()):
        return "Format file should contain mandatory NSS columns"
    return None


def input_full_name_validator(mapping: dict[str, str]) -> str | None:
    return _must_map(mapping, INPUT_FULL_NAME)


def input_id_validator(mapping: dict[str, str]) -> str | None:
    return _must_map(mapping, INPUT_ID)


def hit_matched_name_validator(mapping: dict[str, str]) -> str | None:
    return _must_map(mapping, HIT_MATCHED_NAME)


def validate_format(mapping: dict[str, str]) -> list[str]:
    """ValidationService.validateInputData with the four checks of CsvDataService.validateFormat, in its order.

    J:task/csv/service/CsvDataService.java:212-214. The order decides the order of the texts in the error.
    """
    checks = (data_size_validation, input_full_name_validator, input_id_validator, hit_matched_name_validator)
    errors = []
    for check in checks:
        error = check(mapping)
        if error is not None:
            errors.append(error)
    return errors


def _must_map(mapping: dict[str, str], nss_name: str) -> str | None:
    # Some NSS column must *contain* the name (a substring, not equality: `input_id_rn_extdata` also counts for
    # `input_id`) and not be blank. FileFormatValidation.errorMessage is J:...FileFormatValidation.java:8.
    if not any(nss_name in nss_column and not is_blank_text(nss_column) for nss_column in mapping.values()):
        return f"Format file should contain {nss_name} mapping"
    return None


def is_blank_text(text: str) -> bool:
    # Java: `k.trim().isEmpty()`. trim() removes characters up to U+0020, StringUtils.isBlank() the Unicode spaces
    # as well, so this is not the library's is_blank. The two differ only for exotic spaces such as U+2003.
    return text.strip("".join(chr(code) for code in range(0x21))) == ""
