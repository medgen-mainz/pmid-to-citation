"""Exception hierarchy raised by :mod:`pmid_to_citation`.

Every error this library raises derives from :class:`PmidToCitationError`, so a
caller that only wants to distinguish "this library failed" from anything else
needs a single ``except`` clause.
"""


class PmidToCitationError(Exception):
    """Base class for every error raised by this library."""


class EntrezError(PmidToCitationError):
    """Raised when the Entrez API cannot be reached or reports a failure."""


class RecordNotFoundError(EntrezError):
    """Raised when Entrez holds no record for a requested PMID."""


class RecordParseError(PmidToCitationError):
    """Raised when an Entrez response cannot be interpreted as a record."""


class CitationFormatError(PmidToCitationError):
    """Raised when a record lacks fields that the requested style requires."""
