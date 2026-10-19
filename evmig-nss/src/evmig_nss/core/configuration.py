"""The configuration reader of Evelyn (jnw-toolkit 3.0.0.87 JsonStringConfiguration) and the keys of the CSV path.

Java reads the Digital Worker's configuration JSON that arrives with every task. Here it is one JSON file in the
bucket, read once per process (DEC-8, D-3). Behaviour below was checked by running the toolkit jar
(jsonpath 2.10, Jackson 2.21) on about 50 documents; see tests/test_configuration.py.
"""
import json
import logging
from typing import Any

from evmig_nss.core.strings import is_blank, java_trim

logger = logging.getLogger(__name__)

# The five keys the three processors read, all with getRequiredProperty (docs/mapping.md section 7).
FORMAT_FILE_LOCATION_PATH = "provider.FORMAT_FILE_LOCATION"  # J:constants/CSVConfiguration.java:10
DATA_FILE_LOCATION_PATH = "provider.CSV_DATA_FILE_LOCATION"  # J:constants/CSVConfiguration.java:9
PROCEED_WITH_ERROR_DATA_PATH = "configuration.proceed_with_error_data"  # J:constants/NssConfiguration.java:66
KEEP_INPUT_FILE_NAME_FOR_QC_REPORT_PATH = "configuration.keep_input_file_name_for_qc_report"  # J:constants/NssConfiguration.java:68
ENABLE_LOCATION_WLE_PATH = "model.thresholds.location_wle_enable"  # J:constants/ThresholdConfiguration.java:20

# The file in the bucket (EvMigFiles); its key is the whole path.
CONFIG_FILE_KEY = "config/configuration_payload.json"

NO_REQUIRED_PROPERTY_MESSAGE = "Configuration does not contain property '%s'"  # JsonStringConfiguration.java:31


class IllegalStateException(Exception):
    """Java's IllegalStateException, which the toolkit throws for a missing or unreadable required property."""


class Configuration:
    """Ports JsonStringConfiguration, the read side. `document` is the parsed JSON (json.loads)."""

    def __init__(self, document: Any):
        self._document = document

    @classmethod
    def from_text(cls, text: str | None) -> "Configuration":
        """Blank text and text that is not JSON both give an empty configuration, as in Java (JsonStringConfiguration.java:47,73).

        Java swallows the parse error silently; a warning is logged here (the only addition).
        """
        if is_blank(text):
            return cls({})
        try:
            return cls(json.loads(text))
        except ValueError:
            logger.warning("Configuration is not valid JSON; reading it as empty")
            return cls({})

    def get_property(self, name: str) -> str | None:
        """The value as text, or None when the key is missing or null (JsonStringConfiguration.java:85)."""
        value = self._read_value(name)
        return None if value is None else _as_java_string(value)

    def get_required_property(self, name: str) -> str:
        """JsonStringConfiguration.java:90. An empty string is a value; null and missing are an error."""
        value = self.get_property(name)
        if value is None:
            raise IllegalStateException(NO_REQUIRED_PROPERTY_MESSAGE % name)
        return value

    def get_required_boolean(self, name: str) -> bool:
        """getRequiredProperty(name, Boolean.class), JsonStringConfiguration.java:105; Jackson's rules for a Boolean:

        JSON true/false; a JSON integer (0 is false, any other is true); the texts true/True/TRUE and false/False/FALSE
        (surrounding whitespace allowed). "", "null" and a missing key are "does not contain"; anything else is an error.
        Not accepted: "yes", "1", 1.0, "tRuE". (docs/decisions.md DEC-8 says "any case"; the toolkit does not.)
        """
        value = self._read_value(name)
        if isinstance(value, str):
            text = java_trim(value)
            if text in ("true", "True", "TRUE"):
                return True
            if text in ("false", "False", "FALSE"):
                return False
            value = None if text in ("", "null") else value
        elif isinstance(value, int) and not isinstance(value, bool):
            return value != 0
        if value is None:
            raise IllegalStateException(NO_REQUIRED_PROPERTY_MESSAGE % name)
        if isinstance(value, bool):
            return value
        raise IllegalStateException(f"Cannot deserialize value of type `java.lang.Boolean` from {_describe(value)}")

    def _read_value(self, name: str) -> Any:
        # JsonStringConfiguration.java:142: `a.b` is read as the nested path first, then as the flat key "a.b".
        # Only plain dotted keys are supported (the five above); JsonPath expressions are not.
        found = self._read_nested(name.split("."))
        if found is None and "." in name:
            found = self._document.get(name) if isinstance(self._document, dict) else None
        return found

    def _read_nested(self, path: list[str]) -> Any:
        node = self._document
        for step in path:
            if not isinstance(node, dict):
                return None
            node = node.get(step)
        return node


def _as_java_string(value: Any) -> str:
    # String.valueOf of what Jackson read: true -> "true", 5 -> "5". Objects and lists are not used by these keys.
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value)  # Java would print {a=1}
    return str(value)


def _describe(value: Any) -> str:
    if isinstance(value, str):
        return f'String "{value}": only "true" or "false" recognized'
    if isinstance(value, float):
        return "Floating-point value"
    return "Array value" if isinstance(value, list) else "Object value"


# ---- the loader (DEC-8) ----

_cached: Configuration | None = None


def load_configuration(store) -> Configuration:
    """The configuration file of the bucket, read once per process.

    `store` is a BucketStore. A missing file fails the job, since Evelyn has no defaults for these keys either.
    Tests call reset_configuration_cache() between cases.
    """
    global _cached
    if _cached is None:
        _cached = Configuration.from_text(store.read_text(CONFIG_FILE_KEY))
    return _cached


def reset_configuration_cache() -> None:
    global _cached
    _cached = None
