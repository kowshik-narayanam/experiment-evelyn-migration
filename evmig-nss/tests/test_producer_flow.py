# Own test: the library as the csv-task -> csv-schema-producer hand-over uses it (J:task/csv/CsvSchemaProducerProcessor.java:42-62),
# without the function wrappers. A CSV row becomes models, the models cross the wire as JSON text, and the producer side
# reads them back and writes the transaction and the analytics rows.
import json
import logging

from evmig_nss.core.repository import AlertAnalyticsRepository, HitAnalyticsRepository, TransactionRepository
from evmig_nss.schema import screened_data_utils, wle_data_utils
from evmig_nss.schema.models import ScreenedData, WleData
from evmig_nss.service.analytics_service import AnalyticsService
from evmig_nss.service.transaction_service import RunContext, TransactionService
from evmig_nss.testing import FakeEntities
from helpers import attrs


def test_a_screened_alert_with_two_hits_goes_through_the_wire_to_three_data_fabric_rows():
    # csv-task side
    errors = {}
    alert_row = attrs({"input_id": "A-1", "client_id": "5", "input_full_name": "Alice Wonderland", "input_record_type": "individual", "input_date_1": "06/10/1991"})
    hit_rows = [
        attrs({"hit_id": "H-1", "hit_matched_name": "Alyce Wonderland", "hit_record_type": "individual"}),
        attrs({"hit_id": "H-2", "hit_matched_name": "Gill Bates", "hit_record_type": "location", "hit_address_1_country": "PL"}),
    ]
    screened = screened_data_utils.transform_from_map(alert_row, 2, errors)
    wles = [wle_data_utils.transform_from_map(row, True, 2, errors, logging.getLogger("test")) for row in hit_rows]
    assert errors == {}
    wire_screened = json.dumps(screened.model_dump(mode="json"))  # screened_data crosses as JSON
    wire_wles = json.dumps([wle.model_dump(mode="json") for wle in wles])

    # csv-schema-producer side
    screened_in = ScreenedData.model_validate(json.loads(wire_screened))
    wles_in = [WleData.model_validate(wle) for wle in json.loads(wire_wles)]
    assert screened_in == screened and wles_in == wles

    entities = FakeEntities()
    transactions = TransactionService(TransactionRepository(entities), RunContext.from_inputs("run-1", "2026-10-19T07:15:00.000Z"))
    analytics = AnalyticsService(AlertAnalyticsRepository(entities), HitAnalyticsRepository(entities))
    transaction = transactions.start_new_transaction(screened_in.clientId, screened_in.uuid, "alice.csv")
    analytics.init_full_analytics(transaction, screened_in, wles_in)

    assert transaction.Uuid == screened.uuid  # the transaction id is screened_data.uuid
    (tx_row,) = entities.rows["EvMigTransaction-entity"]
    assert (tx_row["Uuid"], tx_row["ClientId"], tx_row["ExtRecordId"], tx_row["StartBpUuid"]) == (screened.uuid, "5", "alice.csv", "run-1")
    (alert_row_out,) = entities.rows["EvMigAlertAnalytics-entity"]
    assert (alert_row_out["AlertId"], alert_row_out["AlertEntityType"], alert_row_out["TransactionUuid"]) == ("A-1", "INDIVIDUAL", screened.uuid)
    hit_rows_out = entities.rows["EvMigHitAnalytics-entity"]
    assert [(r["WleId"], r["WleEntityType"]) for r in hit_rows_out] == [("H-1", "INDIVIDUAL"), ("H-2", "LOCATION")]
