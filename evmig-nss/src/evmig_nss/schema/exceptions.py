"""The two exceptions of the schema module (S:InvalidInputDataException.java, S:UnsupportedDateFormatException.java)."""


class InvalidInputDataException(Exception):
    """A cell that cannot be parsed. Its message is the client's column name (or None), see ErrorUtils."""

    def __init__(self, message: str | None):
        super().__init__(message)
        self.message = message  # Java getMessage(): null stays null, where str(exception) would say "None"

    def __str__(self) -> str:
        return self.message or ""


class UnsupportedDateFormatException(Exception):
    """A date text no format matches. Java extends NssNonRetriableException; nothing here uses that base."""
