"""Exception hierarchy raised by :mod:`pmid_to_citation`.

Every error this library raises derives from :class:`PmidToCitationError`, so a
caller that only wants to distinguish "this library failed" from anything else
needs a single ``except`` clause.
"""


class PmidToCitationError(Exception):
    """Base class for every error raised by this library."""


class EntrezError(PmidToCitationError):
    """Raised when the Entrez API cannot be reached or reports a failure.

    Args:
        message: Human-readable description of the failure.
        pmid: The PMID being requested, when the failure concerns one.
        status_code: The HTTP status code, when the failure was an HTTP error.
    """

    def __init__(
        self,
        message: str,
        *,
        pmid: int | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.pmid = pmid
        self.status_code = status_code


class RecordNotFoundError(EntrezError):
    """Raised when Entrez holds no record for a requested PMID.

    Entrez answers a request for an unknown PMID with an empty body rather than
    an HTTP error, so this is a distinct condition from :class:`EntrezError`.
    """


class RecordParseError(PmidToCitationError):
    """Raised when a MEDLINE record cannot be interpreted.

    Args:
        message: Human-readable description of the failure.
        line_number: The 1-based input line the failure was detected on, when
            it can be attributed to one.
    """

    def __init__(self, message: str, *, line_number: int | None = None) -> None:
        super().__init__(f"line {line_number}: {message}" if line_number is not None else message)
        self.line_number = line_number


class CitationFormatError(PmidToCitationError):
    """Raised when a record cannot be rendered in the requested style."""


class UnknownStyleError(CitationFormatError):
    """Raised when the style definition for a requested style is not installed."""
