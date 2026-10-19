"""Ports Transaction and TransactionStatus (C:domain/Transaction.java:20, C:domain/TransactionStatus.java:3).

The 14 fields are the Data Fabric entity EvMigTransaction (docs/mapping.md section 8.1). The Java field and column
each one comes from is on its line.
"""
import uuid
from datetime import datetime
from enum import Enum

from pydantic import Field

from evmig_nss.core.data_fabric_row import DataFabricRow

ENTITY_NAME = "EvMigTransaction"


class TransactionStatus(str, Enum):
    NEW = "NEW"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


class Transaction(DataFabricRow):
    Uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))  # uuid
    StartTime: datetime | None = None  # start_time
    EndTime: datetime | None = None  # end_time
    Status: TransactionStatus | None = None  # status
    StartBpUuid: str | None = None  # start_bp_uuid, Java field bpRunUuid
    BpStartTime: datetime | None = None  # bp_start_time
    ErrorMessage: str | None = None  # error_message
    ErrorStep: str | None = None  # error_step
    DwVariation: str | None = None  # dw_variation
    DwVersion: str | None = None  # dw_version
    ModelVersion: str | None = None  # model_version
    ExtRecordId: str | None = ""  # ext_record_id, Java default StringUtils.EMPTY
    ClientId: str = "1"  # client_id, the column's default
    OriginalTransactionUuid: str | None = None  # original_transaction_uuid
