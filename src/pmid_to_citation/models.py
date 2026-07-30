"""Validated models for a PubMed record.

These models know nothing about HTTP or about output formats. They describe what
a MEDLINE record contains, and normalise the handful of fields that PubMed ships
as packed strings (author names, MeSH terms, grants, substances).
"""

import re
from datetime import datetime
from enum import StrEnum
from typing import Self

import pydantic

from pmid_to_citation._dates import parse_pubmed_datetime

__all__ = [
    "ISSN",
    "Author",
    "CitationReference",
    "Editor",
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
    "PubMedRecord",
    "PublicationHistory",
    "PublicationHistoryType",
    "PublicationStatus",
    "PublicationType",
    "Substance",
]

# Initials in a MEDLINE short-form name are one to three capitals at the end of
# the string, e.g. the "AB" in "Makar AB". Anything else is part of the surname,
# which is why this is anchored rather than a plain split.
_SHORT_FORM_NAME = re.compile(r"^(.+?)\s+([A-Z]{1,3})$")


class PublicationStatus(StrEnum):
    """Publication status types."""

    MEDLINE = "MEDLINE"
    PUBMED_NOT_MEDLINE = "PubMed-not-MEDLINE"
    IN_PROCESS = "in-process"
    PUBLISHER = "publisher"


class Owner(StrEnum):
    """Data owner types."""

    NLM = "NLM"
    NASA = "NASA"
    PIP = "PIP"
    KIE = "KIE"
    HSR = "HSR"
    HMD = "HMD"
    SIS = "SIS"
    NOTNLM = "NOTNLM"


class LanguageCode(StrEnum):
    """Common language codes."""

    ENG = "eng"
    GER = "ger"
    FRE = "fre"
    SPA = "spa"
    ITA = "ita"
    JPN = "jpn"
    RUS = "rus"
    CHI = "chi"


class PublicationType(StrEnum):
    """Publication types as defined in PubMed."""

    JOURNAL_ARTICLE = "Journal Article"
    REVIEW = "Review"
    CASE_REPORTS = "Case Reports"
    CLINICAL_TRIAL = "Clinical Trial"
    RANDOMIZED_CONTROLLED_TRIAL = "Randomized Controlled Trial"
    META_ANALYSIS = "Meta-Analysis"
    SYSTEMATIC_REVIEW = "Systematic Review"
    COMPARATIVE_STUDY = "Comparative Study"
    MULTICENTER_STUDY = "Multicenter Study"
    RESEARCH_SUPPORT_NIH_EXTRAMURAL = "Research Support, N.I.H., Extramural"
    RESEARCH_SUPPORT_NIH_INTRAMURAL = "Research Support, N.I.H., Intramural"
    RESEARCH_SUPPORT_NON_US_GOVT = "Research Support, Non-U.S. Gov't"
    RESEARCH_SUPPORT_US_GOVT_NON_PHS = "Research Support, U.S. Gov't, Non-P.H.S."
    RESEARCH_SUPPORT_US_GOVT_PHS = "Research Support, U.S. Gov't, P.H.S."
    PUBLISHED_ERRATUM = "Published Erratum"
    RETRACTED_PUBLICATION = "Retracted Publication"
    RETRACTION_NOTICE = "Retraction Notice"
    EDITORIAL = "Editorial"
    LETTER = "Letter"
    COMMENT = "Comment"
    NEWS = "News"
    BIOGRAPHY = "Biography"
    HISTORICAL_ARTICLE = "Historical Article"
    INTERVIEW = "Interview"
    LECTURE = "Lecture"
    LEGAL_CASE = "Legal Case"
    LEGISLATION = "Legislation"
    GUIDELINE = "Guideline"
    PRACTICE_GUIDELINE = "Practice Guideline"
    CONSENSUS_DEVELOPMENT_CONFERENCE = "Consensus Development Conference"
    CONSENSUS_DEVELOPMENT_CONFERENCE_NIH = "Consensus Development Conference, NIH"
    VALIDATION_STUDY = "Validation Study"
    EVALUATION_STUDY = "Evaluation Study"
    TWIN_STUDY = "Twin Study"
    TECHNICAL_REPORT = "Technical Report"
    DATASET = "Dataset"
    PREPRINT = "Preprint"
    BOOK_CHAPTER = "Book Chapter"


class ISSNType(StrEnum):
    """ISSN types."""

    PRINT = "Print"
    ELECTRONIC = "Electronic"
    LINKING = "Linking"


class IdentifierType(StrEnum):
    """Article identifier types."""

    DOI = "doi"
    PII = "pii"
    PMC = "pmc"
    PMID = "pmid"
    ISBN = "isbn"


class PublicationHistoryType(StrEnum):
    """Publication history status types."""

    RECEIVED = "received"
    REVISED = "revised"
    ACCEPTED = "accepted"
    AHEADOFPRINT = "aheadofprint"
    ENTREZ = "entrez"
    PUBMED = "pubmed"
    MEDLINE = "medline"
    PMC_RELEASE = "pmc-release"


class Person(pydantic.BaseModel):
    """A person named in a record.

    MEDLINE gives every kind of person (author, editor, investigator, name as
    subject) in the same two shapes, so the parsing lives here once.
    """

    last_name: str
    initials: str
    suffix: str | None = None
    full_name: str | None = None

    # A misspelled field would otherwise be silently dropped, and these are
    # constructed from parsed text where a typo is easy to make.
    model_config = pydantic.ConfigDict(extra="forbid")

    @classmethod
    def from_short_form(cls, text: str) -> Self:
        """Parse the abbreviated form, e.g. ``Makar AB`` or ``Martín Merinero H``.

        Args:
            text: The field value as it appears in the record.

        Returns:
            The parsed person.

        Examples:
            >>> Person.from_short_form("Makar AB")
            Person(last_name='Makar', initials='AB', suffix=None, full_name=None)
        """
        text = text.strip()
        match = _SHORT_FORM_NAME.match(text)
        if match:
            return cls(last_name=match.group(1), initials=match.group(2))

        # No trailing initials: treat the last whitespace-separated token as the
        # initials anyway, since that is where MEDLINE puts them.
        parts = text.split()
        if len(parts) >= 2:
            return cls(last_name=" ".join(parts[:-1]), initials=parts[-1])
        return cls(last_name=text, initials="")

    @classmethod
    def from_full_form(cls, text: str) -> Self:
        """Parse the spelled-out form, e.g. ``Makar, A B``.

        Args:
            text: The field value as it appears in the record.

        Returns:
            The parsed person, with ``full_name`` set to the original text.

        Examples:
            >>> Person.from_full_form("Makar, A B").last_name
            'Makar'
        """
        last_name = text.split(", ", 1)[0] if ", " in text else text
        return cls(last_name=last_name, initials="", full_name=text)


class Author(Person):
    """An author of the work."""

    affiliation: str | None = None
    identifier: str | None = None


class Editor(Person):
    """An editor, for books and collections."""

    affiliation: str | None = None


class Investigator(Person):
    """An investigator or collaborator."""

    affiliation: str | None = None


class PersonalNameSubject(Person):
    """A person who is the subject of the work rather than a contributor."""


class CitationReference(pydantic.BaseModel):
    """A cross-reference to another record: a correction, comment, retraction."""

    pmid: int | None = None
    citation_text: str | None = None
    type: str | None = None


class OtherAbstract(pydantic.BaseModel):
    """An abstract contributed by someone other than the publisher."""

    text: str
    language: str | None = None
    type: str | None = None


class ISSN(pydantic.BaseModel):
    """An ISSN together with the medium it identifies."""

    issn: str
    type: ISSNType


class Identifier(pydantic.BaseModel):
    """An article identifier, such as a DOI."""

    value: str
    type: IdentifierType


class Grant(pydantic.BaseModel):
    """Funding information."""

    grant_id: str
    agency: str | None = None
    country: str | None = None

    @classmethod
    def from_string(cls, text: str) -> Self:
        """Parse a ``GR`` field, e.g. ``F32 AG064886/AG/NIA NIH HHS/United States``.

        Args:
            text: The field value as it appears in the record.

        Returns:
            The parsed grant. Fields absent from the value are left unset.
        """
        parts = text.split("/")
        if len(parts) >= 3:
            return cls(
                grant_id=parts[0].strip(),
                agency=parts[1].strip(),
                country=parts[-1].strip(),
            )
        return cls(grant_id=text.strip())


class MeshTerm(pydantic.BaseModel):
    """A MeSH descriptor with an optional subheading."""

    descriptor: str
    subheading: str | None = None
    major_topic: bool = False

    @classmethod
    def from_string(cls, text: str) -> Self:
        """Parse an ``MH`` field, e.g. ``Body Fluids/*analysis``.

        Args:
            text: The field value as it appears in the record. A leading or
                embedded ``*`` marks the term as a major topic.

        Returns:
            The parsed term.
        """
        major_topic = text.startswith("*") or "/*" in text
        text = text.replace("*", "")

        if "/" in text:
            descriptor, subheading = text.split("/", 1)
            return cls(
                descriptor=descriptor.strip(),
                subheading=subheading.strip() if subheading else None,
                major_topic=major_topic,
            )
        return cls(descriptor=text.strip(), major_topic=major_topic)


class Substance(pydantic.BaseModel):
    """A chemical substance with its registry number."""

    registry_number: str
    name: str

    @classmethod
    def from_string(cls, text: str) -> Self:
        """Parse an ``RN`` field, e.g. ``0 (Formates)``.

        Args:
            text: The field value as it appears in the record.

        Returns:
            The parsed substance. A value with no registry number leaves
            ``registry_number`` empty.
        """
        if " (" in text and text.endswith(")"):
            registry_number, name = text.split(" (", 1)
            return cls(registry_number=registry_number.strip(), name=name.rstrip(")").strip())
        return cls(registry_number="", name=text.strip())


class PublicationHistory(pydantic.BaseModel):
    """One dated step in the publication history."""

    date: datetime
    type: PublicationHistoryType

    @classmethod
    def from_string(cls, text: str) -> Self:
        """Parse a ``PHST`` field, e.g. ``2022/06/01 06:03 [entrez]``.

        Args:
            text: The field value as it appears in the record.

        Returns:
            The parsed history entry.

        Raises:
            ValueError: If the value has no bracketed type, an unrecognised
                type, or a date that cannot be parsed. The caller decides what
                to do with an unparseable entry; inventing a date here would put
                a fabricated timestamp into the record.
        """
        if "[" not in text or not text.endswith("]"):
            raise ValueError(f"publication history entry has no bracketed type: {text!r}")

        date_part, type_part = text.rsplit(" [", 1)
        date = parse_pubmed_datetime(date_part.strip())
        if date is None:
            raise ValueError(f"unparseable publication history date: {date_part!r}")
        return cls(date=date, type=PublicationHistoryType(type_part.rstrip("]")))


class PubMedRecord(pydantic.BaseModel):
    """A complete PubMed record.

    Only :attr:`pmid` is required; PubMed populates the rest unevenly, and a
    record for a 1975 letter shares few fields with one for a GeneReviews
    chapter. Fields whose tag this library does not model are preserved verbatim
    in :attr:`other_fields` rather than discarded.

    The mutable defaults below are safe: pydantic deep-copies a default value for
    every instance, so no two records share a list.
    """

    # Required fields
    pmid: int

    # Bibliographic information
    title: str | None = None
    transliterated_title: str | None = None
    abstract: str | None = None
    other_abstracts: list[OtherAbstract] = []
    authors: list[Author] = []
    full_authors: list[Author] = []
    corporate_authors: list[str] = []

    # Book and collection specific fields
    book_title: str | None = None
    collection_title: str | None = None
    volume_title: str | None = None
    chapter: str | None = None
    edition: str | None = None
    editors: list[Editor] = []
    full_editors: list[Editor] = []
    publisher: str | None = None
    isbn: str | None = None

    # Journal information
    journal_title: str | None = None
    journal_abbreviation: str | None = None
    journal_id: str | None = None
    issn_list: list[ISSN] = []

    # Publication details
    publication_date: str | None = None
    electronic_publication_date: str | None = None
    contribution_date: str | None = None
    revision_date: str | None = None
    volume: str | None = None
    issue: str | None = None
    pagination: str | None = None
    language: LanguageCode | None = None
    place_of_publication: str | None = None

    # Classification
    publication_types: list[PublicationType] = []
    mesh_terms: list[MeshTerm] = []
    substances: list[Substance] = []
    gene_symbols: list[str] = []
    other_terms: list[str] = []
    other_term_owner: str | None = None

    # Identifiers
    identifiers: list[Identifier] = []
    location_ids: list[str] = []
    pmc_id: str | None = None
    manuscript_id: str | None = None
    other_ids: list[str] = []

    # People and affiliations
    investigators: list[Investigator] = []
    full_investigators: list[Investigator] = []
    personal_name_subjects: list[PersonalNameSubject] = []
    full_personal_name_subjects: list[PersonalNameSubject] = []

    # Funding
    grants: list[Grant] = []

    # Administrative
    owner: Owner | None = None
    status: PublicationStatus | None = None
    status_tag: str | None = None
    subset: str | None = None

    # Dates
    entry_date: datetime | None = None
    mesh_date: datetime | None = None
    create_date: datetime | None = None
    last_revision_date: str | None = None
    completion_date: str | None = None
    pmc_release_date: str | None = None

    # Publication history
    publication_history: list[PublicationHistory] = []

    # Comments, corrections, and related articles
    comment_in: list[CitationReference] = []
    comment_on: list[CitationReference] = []
    erratum_in: list[CitationReference] = []
    erratum_for: list[CitationReference] = []
    corrected_republished_from: list[CitationReference] = []
    corrected_republished_in: list[CitationReference] = []
    retraction_in: list[CitationReference] = []
    retraction_of: list[CitationReference] = []
    retracted_republished_from: list[CitationReference] = []
    retracted_republished_in: list[CitationReference] = []
    republished_from: list[CitationReference] = []
    republished_in: list[CitationReference] = []
    expression_concern_for: list[CitationReference] = []
    expression_concern_in: list[CitationReference] = []
    update_in: list[CitationReference] = []
    update_of: list[CitationReference] = []
    original_report_in: list[CitationReference] = []
    summary_for_patients_in: list[CitationReference] = []
    dataset_described_in: list[CitationReference] = []
    dataset_use_reported_in: list[CitationReference] = []

    # Additional information
    copyright_information: str | None = None
    other_copyright_information: str | None = None
    conflict_of_interest: str | None = None
    general_note: str | None = None
    space_flight_mission: str | None = None
    secondary_source_ids: list[str] = []
    number_of_references: int | None = None

    # Legacy fields
    publication_status: str | None = None
    source: str | None = None

    # Any field tag this library does not model, kept verbatim.
    other_fields: dict[str, list[str]] = {}

    model_config = pydantic.ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")
