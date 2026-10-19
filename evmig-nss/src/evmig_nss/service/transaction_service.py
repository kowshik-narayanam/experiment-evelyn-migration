"""Ports TransactionService.startNewTransaction (J:service/TransactionService.java:53 and :57), docs/decisions.md DEC-5, DEC-6.

Skipped: the 2-argument startNewTransaction (random uuid, REST input), finishTransactionWithError/WithSuccess,
isTransactionFailed, updateTransactionStatus, allTransactionsProcessed, the find* methods, resolveExtRecordId: later steps.
"""
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from evmig_nss.core import usecase
from evmig_nss.core.data_fabric_row import parse_utc, utc_now
from evmig_nss.core.repository import DataIntegrityViolationError, TransactionRepository
from evmig_nss.core.strings import is_blank
from evmig_nss.core.transaction import Transaction, TransactionStatus

logger = logging.getLogger(__name__)

FOLDER_KEY_ENV = "UIPATH_FOLDER_KEY"  # the SDK reads the same variable for the job's folder


@dataclass(frozen=True)
class RunContext:
    """What WorkFusion's task context gave Evelyn and a Python function does not have (D-2). Java: ExecutionUtils, BPDetails.

    bp_run_id      the CSV flow's instance id, passed in by the flow ($metadata.InstanceId); stored as StartBpUuid
    bp_start_time  the time csv-monitor-task started (UTC)
    dw_variation   the job's folder key, "" when absent (Evelyn's own fallback, J:utils/ExecutionUtils.java:62)
    """

    bp_run_id: str
    bp_start_time: datetime
    dw_variation: str = ""

    def __post_init__(self):
        if is_blank(self.bp_run_id):
            raise ValueError("bp_run_id is empty: the CSV flow must pass its instance id ($metadata.InstanceId)")

    @classmethod
    def from_inputs(cls, bp_run_id: str, bp_start_time: str) -> "RunContext":
        """`bp_start_time` is the ISO text the monitor returned; the variation is read from the environment."""
        return cls(bp_run_id, parse_utc(bp_start_time), os.environ.get(FOLDER_KEY_ENV, ""))


class TransactionService:
    def __init__(self, repository: TransactionRepository, run_context: RunContext, clock: Callable[[], datetime] = utc_now):
        self._repository = repository
        self._run_context = run_context
        self._clock = clock

    def start_new_transaction(self, client_id: str, uuid: str, ext_record_id: str, original_transaction_uuid: str | None = None) -> Transaction:
        """Write the transaction `uuid` with status NEW and return it. Called with 3 arguments (the CSV path) or 4.

        A second call with the same uuid overwrites the row (status back to NEW, end and error fields cleared), as
        Evelyn's JPA merge does. If two producers race on one uuid and the other one wins, the loser logs
        "transaction '<uuid>' already exist" and returns its own, unsaved, row, as Java does.
        """
        transaction = Transaction(
            TransactionUuid=uuid,
            OriginalTransactionUuid=original_transaction_uuid,
            ClientId=client_id,
            StartBpUuid=self._run_context.bp_run_id,
            BpStartTime=self._run_context.bp_start_time,
            DwVariation=self._run_context.dw_variation,
            StartTime=self._clock(),
            Status=TransactionStatus.NEW,
            DwVersion=usecase.dw_version(),
            ModelVersion=usecase.MODEL_VERSION,
            ExtRecordId=ext_record_id,
        )
        try:
            return self._repository.save(transaction)
        except DataIntegrityViolationError:
            logger.warning("transaction '%s' already exist", transaction.TransactionUuid)
            return transaction
