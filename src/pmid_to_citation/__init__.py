"""Fetch PubMed citations from the NCBI Entrez API and render reference text.

The public API is re-exported here; import from :mod:`pmid_to_citation` rather
than from the submodules, which are free to move between releases.

Three layers, each usable on its own:

* :class:`EntrezClient` fetches MEDLINE text from Entrez.
* :func:`parse_medline` turns that text into a :class:`PubMedRecord`.
* :class:`CitationFormatter` renders a record as citation text.

:func:`fetch_citation` runs all three for the common case.
"""

from pmid_to_citation.client import EFETCH_URL, EntrezClient
from pmid_to_citation.exceptions import (
    CitationFormatError,
    EntrezError,
    PmidToCitationError,
    RecordNotFoundError,
    RecordParseError,
    UnknownStyleError,
)
from pmid_to_citation.facade import fetch_citation, fetch_record
from pmid_to_citation.formatter import CitationFormatter, CitationStyle
from pmid_to_citation.models import (
    ISSN,
    Author,
    CitationReference,
    Editor,
    Grant,
    Identifier,
    IdentifierType,
    Investigator,
    ISSNType,
    LanguageCode,
    MeshTerm,
    OtherAbstract,
    Owner,
    Person,
    PersonalNameSubject,
    PublicationHistory,
    PublicationHistoryType,
    PublicationStatus,
    PublicationType,
    PubMedRecord,
    Substance,
)
from pmid_to_citation.parser import parse_medline, parse_medline_file
from pmid_to_citation.version import __version__

__all__ = [
    "EFETCH_URL",
    "ISSN",
    "Author",
    "CitationFormatError",
    "CitationFormatter",
    "CitationReference",
    "CitationStyle",
    "Editor",
    "EntrezClient",
    "EntrezError",
    "Grant",
    "ISSNType",
    "Identifier",
    "IdentifierType",
    "Investigator",
    "LanguageCode",
    "MeshTerm",
    "OtherAbstract",
    "Owner",
    "Person",
    "PersonalNameSubject",
    "PmidToCitationError",
    "PubMedRecord",
    "PublicationHistory",
    "PublicationHistoryType",
    "PublicationStatus",
    "PublicationType",
    "RecordNotFoundError",
    "RecordParseError",
    "Substance",
    "UnknownStyleError",
    "__version__",
    "fetch_citation",
    "fetch_record",
    "parse_medline",
    "parse_medline_file",
]
