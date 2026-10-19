"""ScreenedData, WleData and their nested types (S:generated from nss_schema.yaml, docs/mapping.md section 9).

Gson <-> pydantic, for a Java developer:
  gson.fromJson(text, ScreenedData.class)   ->  ScreenedData.model_validate(obj)   (obj is a dict; json.loads(text) first)
  gson.toJson(screenedData)                 ->  screened_data.model_dump(mode="json")   (a dict of plain JSON values)
Both use the Java field names as keys, so camelCase attributes here are deliberate and there are no aliases.
  - extra="ignore" is Gson skipping JSON keys the class does not have.
  - A key absent from the input keeps the default below, like a Gson-built object keeps its field initialisers
    (lists and maps empty, clientId "1", addToOngoingMonitor false, everything else None = null).
  - A key present with null sets None, as in Gson: so a list or map field may also be None.
  - model_dump() keeps None as null, like Gson's serializeNulls() (C:config/AppConfig.java:49).
  - Enum fields hold plain strings ("INDIVIDUAL"), also in model_dump(); compare with EntityType.INDIVIDUAL, which is a str.
Assigning an attribute (model.name = ...) is validated like construction (validate_assignment).
"""
from enum import Enum
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


class EntityType(str, Enum):
    INDIVIDUAL = "INDIVIDUAL"
    ORGANIZATION = "ORGANIZATION"
    SECURITIES = "SECURITIES"
    LOCATION = "LOCATION"


class Gender(str, Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"


def _uuid_text(value: str | None) -> str | None:
    # The Java type is UUID. A string field keeps the JSON text-only; this does what Gson does on a read:
    # reject a non-UUID and write the canonical lower-case form back.
    return None if value is None else str(UUID(value))


UuidText = Annotated[str | None, AfterValidator(_uuid_text)]


class SchemaModel(BaseModel):
    model_config = ConfigDict(extra="ignore", use_enum_values=True, validate_assignment=True)


class NameEntity(SchemaModel):
    fullName: str | None = None
    firstName: str | None = None
    lastName: str | None = None
    middleName: str | None = None
    derived: str | None = None
    source: str | None = None


class DetailedDate(SchemaModel):
    type: str | None = None
    full: str | None = None
    year: str | None = None
    month: str | None = None
    day: str | None = None


class DateEntity(SchemaModel):
    original: DetailedDate | None = None
    derived: DetailedDate | None = None
    source: str | None = None


class Location(SchemaModel):
    type: str | None = None
    country: str | None = None
    state: str | None = None
    city: str | None = None
    street: str | None = None
    address: str | None = None
    latitude: str | None = None
    longitude: str | None = None


class LocationEntity(SchemaModel):
    original: Location | None = None
    enriched: list[Location] | None = Field(default_factory=list)
    source: str | None = None


class ScreenedData(SchemaModel):
    uuid: UuidText = None
    id: str | None = None
    clientId: str | None = "1"
    category: str | None = None
    entityType: EntityType | None = None
    gender: Gender | None = None
    name: NameEntity | None = None
    # A date that fails to parse leaves a None in the list (S:DateUtils.java:77); such a record is dropped by the CSV step.
    dates: list[DateEntity | None] | None = Field(default_factory=list)
    locations: list[LocationEntity] | None = Field(default_factory=list)
    aliases: list[NameEntity] | None = Field(default_factory=list)
    identifiers: dict[str, str] | None = Field(default_factory=dict)
    additionalData: dict[str, str] | None = Field(default_factory=dict)
    goldDecision: str | None = None
    addToOngoingMonitor: bool | None = False
    originalTransaction: UuidText = None


class WleData(SchemaModel):
    uuid: UuidText = None
    id: str | None = None
    category: str | None = None
    entityType: EntityType | None = None
    gender: Gender | None = None
    name: NameEntity | None = None
    dates: list[DateEntity | None] | None = Field(default_factory=list)
    locations: list[LocationEntity] | None = Field(default_factory=list)
    aliases: list[NameEntity] | None = Field(default_factory=list)
    identifiers: dict[str, str] | None = Field(default_factory=dict)
    additionalData: dict[str, str] | None = Field(default_factory=dict)
    goldDecision: str | None = None
