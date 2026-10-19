# Own tests: the three row types against docs/mapping.md section 8 (the final Liquibase state), and the time format.
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from evmig_nss.core.analytics import AlertAnalytics, HitAnalytics
from evmig_nss.core.data_fabric_row import format_utc, parse_utc
from evmig_nss.core.transaction import Transaction, TransactionStatus

TRANSACTION_FIELDS = [  # section 8.1, 14 columns
    "TransactionUuid", "StartTime", "EndTime", "Status", "StartBpUuid", "BpStartTime", "ErrorMessage", "ErrorStep", "DwVariation",
    "DwVersion", "ModelVersion", "ExtRecordId", "ClientId", "OriginalTransactionUuid",
]  # fmt: skip
ALERT_FIELDS = [  # section 8.2, 20 columns
    "AlertUuid", "TransactionUuid", "AlertId", "AlertCategory", "AlertEntityType", "AlertDwDecision", "AlertDwExplanation", "AlertMtDecision",
    "AlertMtExplanation", "WorkerFullName", "WorkerId", "HtmlReportLink", "CsvReportLink", "AutoQC", "Ticker", "GoldDecision",
    "MtReviewStart", "MtReviewComplete", "ClientId", "OriginalTransactionUuid",
]  # fmt: skip
HIT_FIELDS = [  # section 8.3, 14 columns
    "HitUuid", "TransactionUuid", "WleId", "WleCategory", "WleEntityType", "WleDwDecision", "WleDwExplanation", "WleMtDecision",
    "WleMtExplanation", "WorkerFullName", "WorkerId", "GoldDecision", "NameMatchingScore", "WleDecisionScore",
]  # fmt: skip


def test_the_rows_have_exactly_the_data_fabric_fields_of_the_mapping():
    assert list(Transaction.model_fields) == TRANSACTION_FIELDS
    assert list(AlertAnalytics.model_fields) == ALERT_FIELDS
    assert list(HitAnalytics.model_fields) == HIT_FIELDS


def test_a_misspelt_field_is_refused_at_construction():
    with pytest.raises(ValidationError):
        Transaction(TransactionUuid="t1", StartBpUuId="x")


def test_defaults_match_evelyns_entities():
    transaction = Transaction()
    assert len(transaction.TransactionUuid) == 36 and transaction.ClientId == "1" and transaction.ExtRecordId == "" and transaction.Status is None
    alert = AlertAnalytics()
    assert alert.AutoQC is False and alert.Ticker is False and alert.ClientId == "1" and len(alert.AlertUuid) == 36
    assert HitAnalytics().HitUuid != HitAnalytics().HitUuid  # a new uuid per row


def test_to_record_is_a_plain_dict_with_every_field_nulls_included_and_enums_and_times_as_text():
    moment = datetime(2026, 10, 19, 7, 15, 0, 123456, tzinfo=UTC)
    record = Transaction(TransactionUuid="t1", Status=TransactionStatus.NEW, StartTime=moment).to_record()
    assert list(record) == TRANSACTION_FIELDS
    assert record["Status"] == "NEW" and type(record["Status"]) is str
    assert record["StartTime"] == "2026-10-19T07:15:00.123Z"
    assert record["EndTime"] is None and record["ErrorMessage"] is None


def test_format_utc_converts_to_utc_and_keeps_milliseconds():
    plus_two = timezone(timedelta(hours=2))
    assert format_utc(datetime(2026, 1, 2, 3, 4, 5, 6000, tzinfo=plus_two)) == "2026-01-02T01:04:05.006Z"


@pytest.mark.parametrize("text", ["2026-10-19T07:15:00.123Z", "2026-10-19T09:15:00.123+02:00", "2026-10-19T07:15:00.123", " 2026-10-19T07:15:00.123Z "])
def test_parse_utc_reads_iso_text_with_or_without_an_offset(text):
    assert parse_utc(text) == datetime(2026, 10, 19, 7, 15, 0, 123000, tzinfo=UTC)
