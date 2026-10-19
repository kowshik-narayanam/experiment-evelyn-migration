"""The base of the three Data Fabric row types, and the time format Data Fabric gets.

Java: JPA entities (C:domain/Transaction.java:20 and the analytics ones). A row here is a pydantic model whose
attribute names ARE the Data Fabric field names (PascalCase, docs/mapping.md section 8), so model_dump() is the payload.
"""
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict


def utc_now() -> datetime:
    return datetime.now(UTC)


def format_utc(moment: datetime) -> str:
    """DATETIME_WITH_TZ values are written in UTC: 2026-10-19T07:15:00.123Z. (Not yet seen accepted by a tenant.)"""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def parse_utc(text: str) -> datetime:
    """The inverse of format_utc; also accepts any ISO 8601 text with an offset. A text without one is read as UTC."""
    moment = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


class DataFabricRow(BaseModel):
    # use_enum_values: an enum field is written as its text. extra="forbid": a misspelt field fails here, not on the tenant.
    model_config = ConfigDict(use_enum_values=True, extra="forbid")

    def to_record(self) -> dict:
        """The row as the dict Data Fabric takes: every field, None as an explicit null, times as UTC text."""
        return {name: format_utc(value) if isinstance(value, datetime) else value for name, value in self.model_dump().items()}
