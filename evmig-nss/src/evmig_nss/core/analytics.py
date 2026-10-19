"""Ports AlertAnalytics and HitAnalytics (C:domain/analytics/AlertAnalytics.java:21, C:domain/analytics/HitAnalytics.java:20).

The fields are the Data Fabric entities EvMigAlertAnalytics (20) and EvMigHitAnalytics (14), docs/mapping.md
sections 8.2 and 8.3. Only the fields set at init are filled; the rest stay null, as Evelyn leaves them.
"""
import uuid
from datetime import datetime

from pydantic import Field

from evmig_nss.core.data_fabric_row import DataFabricRow

ALERT_ENTITY_NAME = "EvMigAlertAnalytics"
HIT_ENTITY_NAME = "EvMigHitAnalytics"


class AlertAnalytics(DataFabricRow):
    AlertUuid: str = Field(default_factory=lambda: str(uuid.uuid4()))  # uuid, Hibernate generates it in Java; not `Uuid` (D-5)
    TransactionUuid: str | None = None
    AlertId: str | None = None
    AlertCategory: str | None = None
    AlertEntityType: str | None = None  # Java field entityType
    AlertDwDecision: str | None = None
    AlertDwExplanation: str | None = None
    AlertMtDecision: str | None = None
    AlertMtExplanation: str | None = None
    WorkerFullName: str | None = None
    WorkerId: str | None = None
    HtmlReportLink: str | None = None
    CsvReportLink: str | None = None
    AutoQC: bool = False  # Java selectedForAutoQC; a BOOLEAN field (D-5)
    Ticker: bool = False  # Java tickerUsed
    GoldDecision: str | None = None
    MtReviewStart: datetime | None = None
    MtReviewComplete: datetime | None = None
    ClientId: str = "1"
    OriginalTransactionUuid: str | None = None


class HitAnalytics(DataFabricRow):
    HitUuid: str = Field(default_factory=lambda: str(uuid.uuid4()))  # uuid; not `Uuid` (D-5)
    TransactionUuid: str | None = None
    WleId: str | None = None
    WleCategory: str | None = None
    WleEntityType: str | None = None
    WleDwDecision: str | None = None
    WleDwExplanation: str | None = None
    WleMtDecision: str | None = None
    WleMtExplanation: str | None = None
    WorkerFullName: str | None = None
    WorkerId: str | None = None
    GoldDecision: str | None = None
    NameMatchingScore: str | None = None
    WleDecisionScore: str | None = None
