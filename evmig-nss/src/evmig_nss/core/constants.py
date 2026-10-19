"""Constants of the core module, and InputAttribute.

Ports InputParameters, HitParameters, AttributeNames (C:constants/*.java, the ones the schema utils use) and
InputAttribute (C:service/InputAttribute.java:3).
"""
from dataclasses import dataclass
from enum import Enum

from evmig_nss.core.strings import java_trim

# The one Orchestrator bucket that stands in for Evelyn's S3 (DEC-7).
BUCKET_NAME = "EvMigFiles"

# InputParameters (C:constants/InputParameters.java)
INPUT_ID = "input_id"
CLIENT_ID = "client_id"
INPUT_CATEGORY = "input_category"
INPUT_RECORD_TYPE = "input_record_type"
INPUT_ENTITY_TYPE = "input_entity_type"
INPUT_GENDER = "input_gender"
INPUT_FULL_NAME = "input_full_name"
INPUT_FIRST_NAME = "input_first_name"
INPUT_LAST_NAME = "input_last_name"
INPUT_MIDDLE_NAME = "input_middle_name"
ADDRESS_FIELD = "_address_"
DATE_FIELD = "_date_"
DATE_TYPE_FIELD = "_date_type_"
INPUT = "input"
IDENTIFIERS_POSTFIX = "_identifier"
EXT_DATA_POSTFIX = "_extdata"
NAME_POSTFIX = "_name"
ALERT_GOLD_RESOLUTION = "alert_gold_resolution"

# HitParameters (C:constants/HitParameters.java)
HIT = "hit"
HIT_ID = "hit_id"
HIT_RECORD_TYPE = "hit_record_type"
HIT_ENTITY_TYPE = "hit_entity_type"
HIT_MATCHED_NAME = "hit_matched_name"
HIT_FIRST_NAME = "hit_first_name"
HIT_MIDDLE_NAME = "hit_middle_name"
HIT_LAST_NAME = "hit_last_name"
HIT_CATEGORY = "hit_category"
HIT_GENDER = "hit_gender"
HIT_GOLD_RESOLUTION = "hit_gold_resolution"

# AttributeNames (C:constants/AttributeNames.java)
INPUT_ATTR_CASE_SYSTEM_ID = "input_case_system_id"


class AttributeType(Enum):
    """S:readable/enums/AttributeType.java: which side of a CSV row a column belongs to."""

    INPUT = "input"
    HIT = "hit"

    @property
    def prefix(self) -> str:
        return self.value


@dataclass(frozen=True)
class InputAttribute:
    """One cell of a CSV row: the raw text and the client's column name it came from.

    Java: a record whose value() accessor trims. Here `raw_value` is the text as read and `value` is the
    trimmed one, which is the only one the rest of the code uses.
    """

    raw_value: str | None
    client_column: str | None

    @property
    def value(self) -> str | None:
        return None if self.raw_value is None else java_trim(self.raw_value)
