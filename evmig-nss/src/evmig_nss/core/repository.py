"""The Data Fabric store (DEC-6): what Evelyn's Spring Data repositories do, over `sdk.entities`.

Spring Data <-> here, for a Java developer:
  - A repository interface (TransactionRepository extends JpaRepository) is a class per entity, below. Spring writes
    the finder SQL from the method name (getAlertAnalyticsByTransactionUuid); here a finder is a filter on one field.
  - save(entity) is a JPA merge: UPDATE if the id exists, else INSERT. Data Fabric has no merge, so save() below
    looks the row up first (one find, then one write).
  - There is no session and no @Transactional: every call below is one HTTP call, and nothing rolls back (D-6).
  - JPA throws DataIntegrityViolationException on a duplicate key; here an insert that loses a race raises
    DataIntegrityViolationError, and any other failure raises as it comes.
  - `entities` is `sdk.entities` (or a FakeEntities), passed in; the entity is found by name, once per store object.
  - A row crosses this module as a plain dict keyed by Data Fabric field name, with its own `Id` added on a read.
"""
import logging

from uipath.platform.entities.entities import EntityQueryFilter, EntityQueryFilterGroup, LogicalOperator, QueryFilterOperator

from evmig_nss.core.analytics import ALERT_ENTITY_NAME, HIT_ENTITY_NAME
from evmig_nss.core.transaction import ENTITY_NAME as TRANSACTION_ENTITY_NAME
from evmig_nss.core.transaction import Transaction

logger = logging.getLogger(__name__)

PAGE_SIZE = 1000  # a query returns at most 1,000 records


class DataFabricError(Exception):
    """Data Fabric refused rows in a batch."""


class DataIntegrityViolationError(Exception):
    """Spring's DataIntegrityViolationException: an insert failed because the row was written by someone else first."""


class EntityStore:
    entity_name: str = ""

    def __init__(self, entities, page_size: int = PAGE_SIZE):
        self._entities = entities
        self._page_size = page_size
        self._key: str | None = None

    @property
    def key(self) -> str:
        # Record calls take the entity's Id, which differs per tenant, so it is looked up by name (one call per store).
        if self._key is None:
            self._key = str(self._entities.retrieve_by_name(self.entity_name).id)
        return self._key

    def find_by(self, field: str, value: str) -> list[dict]:
        """Every row whose `field` equals `value`, all pages."""
        group = EntityQueryFilterGroup(
            logical_operator=LogicalOperator.And,
            query_filters=[EntityQueryFilter(field_name=field, operator=QueryFilterOperator.Equals, value=value)],
        )
        rows = []
        while True:
            page = self._entities.retrieve_records(self.key, filter_group=group, start=len(rows), limit=self._page_size)
            rows += [_row(record) for record in page.items]
            if not page.has_next_page or not page.items:
                return rows

    def insert(self, row: dict) -> dict:
        return _row(self._entities.insert_record(self.key, row))

    def insert_batch(self, rows: list[dict]) -> list[dict]:
        """One call for all rows. The SDK reports refused rows instead of raising, so any refused row raises here.

        A row that is neither written nor reported refused also raises (a count that does not add up), so none is lost silently.
        """
        response = self._entities.insert_records(self.key, rows)
        if response.failure_records:
            errors = [failure.error or "unknown error" for failure in response.failure_records]
            raise DataFabricError(f"{self.entity_name}: {len(errors)} of {len(rows)} rows were refused: {'; '.join(errors)}")
        if len(response.success_records) != len(rows):
            raise DataFabricError(
                f"{self.entity_name}: {len(rows)} rows were sent, {len(response.success_records)} were written and none was reported refused"
            )
        return [_row(record) for record in response.success_records]

    def update(self, record_id: str, row: dict) -> dict:
        # A dict, not a model: a model would send only the fields that were set, and a field set to None must reach Data Fabric as null.
        return _row(self._entities.update_record(self.key, record_id, row))


def _row(record) -> dict:
    return record.model_dump(by_alias=True)


class TransactionRepository(EntityStore):
    """C:repository/TransactionRepository.java:19 (Spring Data). Only save() is used on the CSV path; find_by_uuid is the lookup it needs here."""

    entity_name = TRANSACTION_ENTITY_NAME

    def find_by_uuid(self, uuid: str) -> dict | None:
        rows = self.find_by("Uuid", uuid)
        return rows[0] if rows else None

    def save(self, transaction: Transaction) -> Transaction:
        """JPA merge by Uuid: overwrite every field of the row if it exists (nulls included), else insert.

        Raises DataIntegrityViolationError when the insert fails and the row exists now (two producers racing on one uuid).
        """
        existing = self.find_by_uuid(transaction.Uuid)
        if existing is not None:
            self.update(existing["Id"], transaction.to_record())
            return transaction
        try:
            self.insert(transaction.to_record())
        except Exception as e:
            if self.find_by_uuid(transaction.Uuid) is None:
                raise  # not a race: a real failure
            raise DataIntegrityViolationError(f"transaction '{transaction.Uuid}' already exist") from e
        return transaction


class AlertAnalyticsRepository(EntityStore):
    """C:repository/analytics/AlertAnalyticsRepository.java:58 getAlertAnalyticsByTransactionUuid, plus save() (the base insert)."""

    entity_name = ALERT_ENTITY_NAME

    def find_by_transaction_uuid(self, transaction_uuid: str) -> list[dict]:
        return self.find_by("TransactionUuid", transaction_uuid)


class HitAnalyticsRepository(EntityStore):
    """C:repository/analytics/HitAnalyticsRepository.java:12. Java only saves; the finder is DEC-6 step 3 (a rerun must not duplicate hits)."""

    entity_name = HIT_ENTITY_NAME

    def find_by_transaction_uuid(self, transaction_uuid: str) -> list[dict]:
        return self.find_by("TransactionUuid", transaction_uuid)
