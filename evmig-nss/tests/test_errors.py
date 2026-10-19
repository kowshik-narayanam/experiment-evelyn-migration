# Own tests of core/errors.py: Evelyn's step error text (J:exceptions/CustomErrorHandling.java:56) and the path error.
import pytest

from evmig_nss.core.errors import InvalidPathException, NSSProcessingException, nss_step, step_error_message


def test_the_step_error_text_is_evelyns():
    assert step_error_message("csv-monitor-task", ValueError("Missing bucket name: nss_input_format.csv")) == (
        "Exception was thrown by Evelyn NSS step csv-monitor-task: Missing bucket name: nss_input_format.csv"
    )  # the text of JT:task/csv/it/CsvMonitorTaskProcessorIT.java:218, minus Java's class-name prefix (D-8)


def test_a_failing_step_body_comes_out_as_nss_processing_exception_with_the_original_as_cause():
    original = InvalidPathException("doc-upload/x.csv", "Please provide correct path to file")
    with pytest.raises(NSSProcessingException) as raised:
        with nss_step("csv-task"):
            raise original
    assert str(raised.value) == "Exception was thrown by Evelyn NSS step csv-task: Please provide correct path to file: doc-upload/x.csv"
    assert raised.value.__cause__ is original


def test_a_step_body_that_works_passes_through():
    with nss_step("csv-task"):
        result = 1 + 1
    assert result == 2


def test_invalid_path_exception_message_is_reason_colon_input():
    error = InvalidPathException("doc-upload/", "Path to file or folder isn't correct")
    assert str(error) == "Path to file or folder isn't correct: doc-upload/"
    assert (error.input, error.reason) == ("doc-upload/", "Path to file or folder isn't correct")
