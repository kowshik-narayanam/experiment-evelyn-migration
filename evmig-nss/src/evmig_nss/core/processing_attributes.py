"""Record keys that travel between the steps (J:constants/ProcessingAttributes.java), the ones this path uses."""

SCREENED_DATA = "screened_data"
WLE_LIST = "wle_list"
REQUEST_ID = "request_id"
TRANSACTION_ID = "transaction_id"
WLE_COUNT = "wle_count"
INTERNAL_REQUEST = "is_internal_request"
PROVIDER_ID = "provider_id"

# Not in ProcessingAttributes: literals of the CSV steps.
STOP = "stop"  # J:task/csv/CsvTaskProcessor.java:77
REST_REQUEST = "rest_request"  # RestRequest.REQUEST_FIELD_NAME, read in J:task/csv/CsvSchemaProducerProcessor.java:49
# The monitor's row keys are the lower-cased CSVConfiguration enum names (J:task/csv/CsvMonitorTaskProcessor.java:40).
DATA_FILE_LOCATION = "data_file_location"
FORMAT_FILE_LOCATION = "format_file_location"
