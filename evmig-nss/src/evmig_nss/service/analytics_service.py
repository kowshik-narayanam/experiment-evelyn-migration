"""Ports AnalyticsService.initFullAnalytics (J:service/AnalyticsService.java:84), docs/decisions.md DEC-6 steps 2 and 3.

Skipped: the 4-argument initAlertAnalytics, setTickerLookupUsed and the update* methods (decisions, reviews and
reports: later steps).

Java writes both tables in one @Transactional call; here the two writes are separate calls (D-6).
"""
import logging
from collections import Counter

from evmig_nss.core.analytics import AlertAnalytics, HitAnalytics
from evmig_nss.core.repository import AlertAnalyticsRepository, HitAnalyticsRepository
from evmig_nss.core.transaction import Transaction
from evmig_nss.schema import entity_type_utils
from evmig_nss.schema.models import ScreenedData, WleData

logger = logging.getLogger(__name__)


class AnalyticsService:
    def __init__(self, alert_repository: AlertAnalyticsRepository, hit_repository: HitAnalyticsRepository):
        self._alerts = alert_repository
        self._hits = hit_repository

    def init_full_analytics(self, transaction: Transaction, screened_data: ScreenedData, wle_data_list: list[WleData] | None) -> None:
        """J:service/AnalyticsService.java:84: the alert row, then the hit rows."""
        self.init_alert_analytics(transaction, screened_data)
        self.init_hits_analytics(transaction.Uuid, wle_data_list)

    def init_alert_analytics(self, transaction: Transaction, screened_data: ScreenedData) -> None:
        """J:service/AnalyticsService.java:33 and :44 (the 2-argument overload calls the long one). One alert row per
        transaction: written only when none exists, so a rerun does not duplicate it."""
        if self._alerts.find_by_transaction_uuid(transaction.Uuid):
            return
        alert = AlertAnalytics(
            TransactionUuid=transaction.Uuid,
            OriginalTransactionUuid=screened_data.originalTransaction,
            ClientId=screened_data.clientId,
            AlertId=screened_data.id,
            AlertCategory=screened_data.category,
            AlertEntityType=entity_type_utils.to_string(screened_data.entityType),
            GoldDecision=screened_data.goldDecision,
        )
        self._alerts.insert(alert.to_record())

    def init_hits_analytics(self, transaction_uuid: str, wle_data_list: list[WleData] | None) -> None:
        """J:service/AnalyticsService.java:64. One hit row per WLE, all in one batch call.

        Java saves every WLE, so a rerun duplicates them (D-7). Here the rows already stored for the transaction are
        counted by WleId and only the WLEs beyond those counts are written: identical hit ids are legal, so a
        multiset, not a set.
        """
        if not wle_data_list:
            return
        stored = Counter(row.get("WleId") for row in self._hits.find_by_transaction_uuid(transaction_uuid))
        new_rows = []
        for wle in wle_data_list:
            if stored[wle.id] > 0:
                stored[wle.id] -= 1
                continue
            hit = HitAnalytics(
                TransactionUuid=transaction_uuid,
                WleId=wle.id,
                WleCategory=wle.category,
                WleEntityType=entity_type_utils.to_string(wle.entityType),
                GoldDecision=wle.goldDecision,
            )
            new_rows.append(hit.to_record())
        if new_rows:
            self._hits.insert_batch(new_rows)
