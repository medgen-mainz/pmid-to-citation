"""Parser for MEDLINE-format PubMed records.

MEDLINE is a line-oriented format: a four-character field tag, a hyphen, then the
value, with continuation lines indented. A record uses roughly ninety distinct
tags, of which any given record uses a few dozen.

This module is pure text processing — it performs no I/O beyond reading a file
you hand it, and knows nothing about Entrez.
"""

import re
from collections.abc import Callable
from pathlib import Path

from pmid_to_citation._dates import parse_pubmed_datetime
from pmid_to_citation.exceptions import RecordParseError
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
    PersonalNameSubject,
    PublicationHistory,
    PublicationStatus,
    PublicationType,
    PubMedRecord,
    Substance,
)

__all__ = ["parse_medline", "parse_medline_file", "parse_medline_records"]

# A field tag is one to four capitals, then a hyphen, then the value.
_FIELD_LINE = re.compile(r"^([A-Z]{1,4})\s*-\s*(.*)")

# A record in a multi-record payload starts with an unindented PMID field, which
# MEDLINE always emits first. Blank lines are not a usable delimiter: Entrez puts
# one before the first record, and nothing in the format forbids one inside a
# value, whereas a continuation line is always indented and so can never be
# mistaken for a record boundary.
_RECORD_START = re.compile(r"^PMID\s*-")

_ISSN_FIELD = re.compile(r"^([0-9]{4}-[0-9]{3}[0-9X])\s*(?:\(([^)]+)\))?")

_ARTICLE_IDENTIFIER = re.compile(r"^([^\[]+)\s*\[([^\]]+)\]")

# PMIDs embedded in the free text of a cross-reference field.
_EMBEDDED_PMID = re.compile(r"\b(\d{8})\b")

# Continuation lines are indented by at least this much.
_CONTINUATION_INDENT = "      "

_Handler = Callable[[str, PubMedRecord], None]


def _set(attribute: str) -> _Handler:
    """Build a handler that assigns the raw value to one record attribute.

    Args:
        attribute: The :class:`~pmid_to_citation.models.PubMedRecord` field name.

    Returns:
        A field handler.
    """

    def handler(value: str, record: PubMedRecord) -> None:
        setattr(record, attribute, value)

    return handler


def _append(attribute: str) -> _Handler:
    """Build a handler that appends the raw value to one list-valued attribute.

    Args:
        attribute: The :class:`~pmid_to_citation.models.PubMedRecord` field name.

    Returns:
        A field handler.
    """

    def handler(value: str, record: PubMedRecord) -> None:
        collection: list[str] = getattr(record, attribute)
        collection.append(value)

    return handler


def _append_parsed(attribute: str, parse: Callable[[str], object]) -> _Handler:
    """Build a handler that parses the value and appends it to a list attribute.

    Args:
        attribute: The :class:`~pmid_to_citation.models.PubMedRecord` field name.
        parse: Converts the raw field value into the element type.

    Returns:
        A field handler.
    """

    def handler(value: str, record: PubMedRecord) -> None:
        collection: list[object] = getattr(record, attribute)
        collection.append(parse(value))

    return handler


def _append_citation_reference(attribute: str) -> _Handler:
    """Build a handler for one of the cross-reference fields.

    Args:
        attribute: The :class:`~pmid_to_citation.models.PubMedRecord` field name.

    Returns:
        A field handler.
    """
    return _append_parsed(attribute, _parse_citation_reference)


def _parse_citation_reference(value: str) -> CitationReference:
    """Interpret a cross-reference field, keeping the text and any PMID in it.

    Args:
        value: The field value, which is free-form citation text.

    Returns:
        The reference, with ``pmid`` set when one could be recognised.
    """
    match = _EMBEDDED_PMID.search(value)
    return CitationReference(pmid=int(match.group(1)) if match else None, citation_text=value, type=None)


def _set_enum(attribute: str, enum: Callable[[str], object]) -> _Handler:
    """Build a handler that assigns an enum member, ignoring unknown values.

    PubMed adds vocabulary terms over time. An unrecognised value leaves the
    field unset rather than failing the whole record.

    Args:
        attribute: The :class:`~pmid_to_citation.models.PubMedRecord` field name.
        enum: The enum to look the value up in.

    Returns:
        A field handler.
    """

    def handler(value: str, record: PubMedRecord) -> None:
        try:
            setattr(record, attribute, enum(value))
        except ValueError:
            setattr(record, attribute, None)

    return handler


def _parse_pmid(value: str, record: PubMedRecord) -> None:
    """Parse the ``PMID`` field.

    Args:
        value: The field value.
        record: The record being built.

    Raises:
        RecordParseError: If the value is not an integer. Unlike every other
            field, this one cannot be skipped — it identifies the record.
    """
    try:
        record.pmid = int(value)
    except ValueError:
        raise RecordParseError(f"invalid PMID: {value!r}") from None


def _parse_issn(value: str, record: PubMedRecord) -> None:
    """Parse an ``IS`` field, e.g. ``1558-8238 (Electronic)``.

    Args:
        value: The field value.
        record: The record being built.
    """
    match = _ISSN_FIELD.match(value)
    if not match:
        return
    try:
        issn_type = ISSNType(match.group(2) or "Print")
    except ValueError:
        return  # An ISSN medium this library does not model.
    record.issn_list.append(ISSN(issn=match.group(1), type=issn_type))


def _parse_publication_type(value: str, record: PubMedRecord) -> None:
    """Parse a ``PT`` field, ignoring types this library does not model.

    Args:
        value: The field value.
        record: The record being built.
    """
    try:
        record.publication_types.append(PublicationType(value))
    except ValueError:
        return


def _parse_article_identifier(value: str, record: PubMedRecord) -> None:
    """Parse an ``AID`` field, e.g. ``10.1172/JCI161852 [doi]``.

    Args:
        value: The field value.
        record: The record being built.
    """
    match = _ARTICLE_IDENTIFIER.match(value)
    if match:
        try:
            id_type = IdentifierType(match.group(2).strip())
        except ValueError:
            return  # An identifier type this library does not model.
        record.identifiers.append(Identifier(value=match.group(1).strip(), type=id_type))
    elif "10." in value:
        # Untagged, but shaped like a DOI.
        record.identifiers.append(Identifier(value=value, type=IdentifierType.DOI))


def _parse_book_title(value: str, record: PubMedRecord) -> None:
    """Parse a ``BTI`` field.

    Args:
        value: The field value. MEDLINE writes a registered-trademark sign as
            ``(®)``, which is expanded here.
        record: The record being built.
    """
    record.book_title = value.replace("(®)", "®")


def _parse_number_of_references(value: str, record: PubMedRecord) -> None:
    """Parse an ``RF`` field, ignoring a non-numeric value.

    Args:
        value: The field value.
        record: The record being built.
    """
    try:
        record.number_of_references = int(value)
    except ValueError:
        return


def _parse_datetime_field(attribute: str) -> _Handler:
    """Build a handler for a timestamp field.

    Args:
        attribute: The :class:`~pmid_to_citation.models.PubMedRecord` field name.

    Returns:
        A field handler that leaves the field unset if the value is unparseable.
    """

    def handler(value: str, record: PubMedRecord) -> None:
        setattr(record, attribute, parse_pubmed_datetime(value))

    return handler


def _attach_to_last(primary: str, fallback: str, attribute: str) -> _Handler:
    """Build a handler for a field that qualifies the person named just before it.

    MEDLINE writes affiliations and identifiers as separate fields that follow
    the name they belong to, so they attach to whichever person was seen last.

    Args:
        primary: The preferred list attribute, normally the spelled-out names.
        fallback: The list attribute to use when ``primary`` is empty.
        attribute: The field to set on the person.

    Returns:
        A field handler.
    """

    def handler(value: str, record: PubMedRecord) -> None:
        people = getattr(record, primary) or getattr(record, fallback)
        if people:
            setattr(people[-1], attribute, value)

    return handler


def _parse_other_abstract_language(value: str, record: PubMedRecord) -> None:
    """Parse an ``OABL`` field, which qualifies the abstract named before it.

    Args:
        value: The field value.
        record: The record being built.
    """
    if record.other_abstracts:
        record.other_abstracts[-1].language = value


_HANDLERS: dict[str, _Handler] = {
    "PMID": _parse_pmid,
    "OWN": _set_enum("owner", Owner),
    "STAT": _set_enum("status", PublicationStatus),
    "LR": _set("last_revision_date"),
    "IS": _parse_issn,
    "VI": _set("volume"),
    "IP": _set("issue"),
    "DP": _set("publication_date"),
    "TI": _set("title"),
    "TT": _set("transliterated_title"),
    "PG": _set("pagination"),
    "AB": _set("abstract"),
    "OAB": _append_parsed("other_abstracts", lambda value: OtherAbstract(text=value)),
    "OABL": _parse_other_abstract_language,
    "FAU": _append_parsed("full_authors", Author.from_full_form),
    "AU": _append_parsed("authors", Author.from_short_form),
    "AD": _attach_to_last("full_authors", "authors", "affiliation"),
    "AUID": _attach_to_last("full_authors", "authors", "identifier"),
    "CN": _append("corporate_authors"),
    "ED": _append_parsed("editors", Editor.from_short_form),
    "FED": _append_parsed("full_editors", Editor.from_full_form),
    "IR": _append_parsed("investigators", Investigator.from_short_form),
    "FIR": _append_parsed("full_investigators", Investigator.from_full_form),
    "IRAD": _attach_to_last("full_investigators", "investigators", "affiliation"),
    "PS": _append_parsed("personal_name_subjects", PersonalNameSubject.from_short_form),
    "FPS": _append_parsed("full_personal_name_subjects", PersonalNameSubject.from_full_form),
    "BTI": _parse_book_title,
    "CTI": _set("collection_title"),
    "VTI": _set("volume_title"),
    "CP": _set("chapter"),
    "EN": _set("edition"),
    "PB": _set("publisher"),
    "ISBN": _set("isbn"),
    "DEP": _set("electronic_publication_date"),
    "CTDT": _set("contribution_date"),
    "DRDT": _set("revision_date"),
    "LA": _set_enum("language", LanguageCode),
    "GR": _append_parsed("grants", Grant.from_string),
    "PT": _parse_publication_type,
    "PL": _set("place_of_publication"),
    "TA": _set("journal_abbreviation"),
    "JT": _set("journal_title"),
    "JID": _set("journal_id"),
    "RN": _append_parsed("substances", Substance.from_string),
    "NM": _append_parsed("substances", Substance.from_string),
    "SB": _set("subset"),
    "MH": _append_parsed("mesh_terms", MeshTerm.from_string),
    "GS": _append("gene_symbols"),
    "OT": _append("other_terms"),
    "OTO": _set("other_term_owner"),
    "EDAT": _parse_datetime_field("entry_date"),
    "MHDA": _parse_datetime_field("mesh_date"),
    "CRDT": _parse_datetime_field("create_date"),
    "PHST": _append_parsed("publication_history", PublicationHistory.from_string),
    "AID": _parse_article_identifier,
    "LID": _append("location_ids"),
    "MID": _set("manuscript_id"),
    "OID": _append("other_ids"),
    "PST": _set("publication_status"),
    "SO": _set("source"),
    "PMC": _set("pmc_id"),
    "PMCR": _set("pmc_release_date"),
    "EFR": _append_citation_reference("erratum_for"),
    "EIN": _append_citation_reference("erratum_in"),
    "CIN": _append_citation_reference("comment_in"),
    "CON": _append_citation_reference("comment_on"),
    "CRF": _append_citation_reference("corrected_republished_from"),
    "CRI": _append_citation_reference("corrected_republished_in"),
    "RIN": _append_citation_reference("retraction_in"),
    "ROF": _append_citation_reference("retraction_of"),
    "RRF": _append_citation_reference("retracted_republished_from"),
    "RRI": _append_citation_reference("retracted_republished_in"),
    "RPF": _append_citation_reference("republished_from"),
    "RPI": _append_citation_reference("republished_in"),
    "ECF": _append_citation_reference("expression_concern_for"),
    "ECI": _append_citation_reference("expression_concern_in"),
    "UIN": _append_citation_reference("update_in"),
    "UOF": _append_citation_reference("update_of"),
    "ORI": _append_citation_reference("original_report_in"),
    "SPIN": _append_citation_reference("summary_for_patients_in"),
    "DDIN": _append_citation_reference("dataset_described_in"),
    "DRIN": _append_citation_reference("dataset_use_reported_in"),
    "CI": _set("copyright_information"),
    "OCI": _set("other_copyright_information"),
    "COI": _set("conflict_of_interest"),
    "GN": _set("general_note"),
    "SFM": _set("space_flight_mission"),
    "SI": _append("secondary_source_ids"),
    "RF": _parse_number_of_references,
    "DCOM": _set("completion_date"),
}


def _group_fields(lines: list[str]) -> dict[str, list[str]]:
    """Fold continuation lines into their field, grouping values by tag.

    Args:
        lines: The record's lines, without trailing newlines.

    Returns:
        Field values keyed by tag, in the order the tags first appeared. A tag
        that repeats (authors, MeSH terms) maps to several values.

    Raises:
        RecordParseError: If content appears before the first field tag.
    """
    fields: dict[str, list[str]] = {}
    current_tag: str | None = None
    current_value = ""

    def flush() -> None:
        if current_tag and current_value:
            fields.setdefault(current_tag, []).append(current_value.strip())

    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue

        match = _FIELD_LINE.match(line)
        if match:
            flush()
            current_tag = match.group(1)
            current_value = match.group(2)
            continue

        if current_tag is None:
            raise RecordParseError(f"malformed line: {line!r}", line_number=line_number)

        # A continuation line, whether or not it carries the usual indent. Join
        # with a single space so that a value wrapped mid-sentence reads back as
        # it was written. It cannot strip to nothing here, because a line that
        # holds only whitespace was already skipped above.
        continuation = line.removeprefix(_CONTINUATION_INDENT).strip()
        if current_value and not current_value.endswith(" "):
            current_value += " "
        current_value += continuation

    flush()
    return fields


def _parse_lines(lines: list[str]) -> PubMedRecord:
    """Build a record from already-split lines.

    Args:
        lines: The record's lines, without trailing newlines.

    Returns:
        The parsed record.

    Raises:
        RecordParseError: If the input is empty, carries no ``PMID`` field, or
            has an unparseable ``PMID``.
    """
    if not lines:
        raise RecordParseError("empty input")

    record = PubMedRecord(pmid=0)  # Replaced by the PMID field below.

    for tag, values in _group_fields(lines).items():
        handler = _HANDLERS.get(tag)
        if handler is None:
            # An unmodelled tag. Keep the values rather than dropping them.
            record.other_fields.setdefault(tag, []).extend(values)
            continue
        for value in values:
            try:
                handler(value, record)
            except RecordParseError:
                raise
            except Exception:
                # A value this library cannot interpret — a malformed date, a
                # name that defeats the grammar. Keep the text so that nothing
                # is silently lost, and carry on with the rest of the record.
                record.other_fields.setdefault(tag, []).append(value)

    if record.pmid == 0:
        raise RecordParseError("missing required PMID field")

    return record


def parse_medline(text: str) -> PubMedRecord:
    r"""Parse a single MEDLINE-format record.

    Args:
        text: The record as returned by Entrez with ``rettype=medline`` and
            ``retmode=text``.

    Returns:
        The parsed record.

    Raises:
        RecordParseError: If the text is empty, carries no ``PMID`` field, has an
            unparseable ``PMID``, or begins with content before any field tag.

    Examples:
        >>> parse_medline("PMID- 1\nTI  - A short paper.").title
        'A short paper.'
    """
    return _parse_lines(text.splitlines())


def _split_records(text: str) -> list[str]:
    """Split a payload holding any number of MEDLINE records.

    Args:
        text: One or more records, as Entrez returns them for a multi-PMID
            request. A leading blank line is expected and ignored — Entrez sends
            one — as are blank lines between records.

    Returns:
        One string per record, in the order they appeared. An empty payload gives
        an empty list, which is how Entrez reports that it knew none of the PMIDs.

    Raises:
        RecordParseError: If non-blank content appears before the first record.
    """
    records: list[list[str]] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if _RECORD_START.match(line):
            records.append([line])
        elif records:
            records[-1].append(line)
        elif line.strip():
            raise RecordParseError(f"content before the first record: {line!r}", line_number=line_number)
    return ["\n".join(lines) for lines in records]


def parse_medline_records(text: str) -> list[PubMedRecord]:
    r"""Parse a payload holding any number of MEDLINE records.

    Use this for the response to a multi-PMID request. Unlike
    :func:`parse_medline`, each record must begin with its ``PMID`` field, since
    that is what delimits one record from the next.

    Args:
        text: One or more records, as Entrez returns them.

    Returns:
        The parsed records, in the order they appeared. Entrez omits PMIDs it does
        not know rather than reporting them, so this may be shorter than the
        request — compare the PMIDs you asked for against the ones you got back.

    Raises:
        RecordParseError: If non-blank content appears before the first record, or
            if any individual record cannot be parsed.

    Examples:
        >>> text = "\nPMID- 1\nTI  - First.\n\nPMID- 2\nTI  - Second.\n"
        >>> [record.pmid for record in parse_medline_records(text)]
        [1, 2]
        >>> parse_medline_records("")
        []
    """
    return [_parse_lines(record.splitlines()) for record in _split_records(text)]


def parse_medline_file(path: Path | str) -> PubMedRecord:
    """Parse a single MEDLINE-format record from a file.

    Args:
        path: Path to a UTF-8 encoded file holding one record.

    Returns:
        The parsed record.

    Raises:
        OSError: If the file cannot be read.
        RecordParseError: As for :func:`parse_medline`.
    """
    return parse_medline(Path(path).read_text(encoding="utf-8"))
