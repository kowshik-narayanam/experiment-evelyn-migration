"""Evelyn's step error text and the path error of S3DownloadService.

Java throws these as exceptions that carry the Java class name in front of the text when a job fails; only the
text is reproduced (D-8).
"""
from contextlib import contextmanager


class NSSProcessingException(Exception):
    """J:exceptions/NSSProcessingException.java:5. The error a failed step raises."""


class InvalidPathException(Exception):
    """java.nio.file.InvalidPathException: the message is `<reason>: <input>`."""

    def __init__(self, input: str, reason: str):
        super().__init__(f"{reason}: {input}")
        self.input = input
        self.reason = reason


def step_error_message(step_id: str, error: BaseException) -> str:
    """J:exceptions/CustomErrorHandling.java:56."""
    return f"Exception was thrown by Evelyn NSS step {step_id}: {error}"


@contextmanager
def nss_step(step_id: str):
    """Wrap a step's body; any error comes out as NSSProcessingException with Evelyn's text.

    Java: NSSTaskProcessor.process() (J:task/NSSTaskProcessor.java:44) catches every Exception and calls
    CustomErrorHandling.handleException, which throws. No transaction is marked ERROR on this path because the
    CSV steps' input has no transaction_id (J:exceptions/CustomErrorHandling.java:49).
    """
    try:
        yield
    except Exception as e:
        raise NSSProcessingException(step_error_message(step_id, e)) from e
