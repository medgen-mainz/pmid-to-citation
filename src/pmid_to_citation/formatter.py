"""Rendering of PubMed records as citation text.

This layer is pure: it takes a record and returns text, and performs no I/O
beyond reading the bundled style definition. Rendering goes through
`citeproc-py <https://github.com/citeproc-py/citeproc-py>`_ and a Citation Style
Language definition, which is what makes further styles cheap to add.
"""

import re
from datetime import datetime
from enum import StrEnum
from importlib import resources
from typing import Any

from citeproc import (
    Citation,
    CitationItem,
    CitationStylesBibliography,
    CitationStylesStyle,
)
from citeproc.source.json import CiteProcJSON

from pmid_to_citation._csl import CslData, CslDateVariable, CslNameVariable, CslType
from pmid_to_citation.exceptions import UnknownStyleError
from pmid_to_citation.models import Person, PubMedRecord

__all__ = ["CitationFormatter", "CitationStyle"]

_STYLE_PACKAGE = "pmid_to_citation.styles"

# citeproc renders a numbered bibliography as ``1.<entry>``. Callers want the
# entry, so the index is stripped. Matching the digits explicitly rather than
# splitting on the first "." keeps a citation whose own text starts with an
# abbreviation intact.
_BIBLIOGRAPHY_INDEX = re.compile(r"^\d+\.")

# Date layouts PubMed uses in the DP field, most specific first.
_DATE_FORMATS = (
    "%Y %b %d",  # 2023 Mar 15
    "%Y %b",  # 2023 Mar
    "%Y",  # 2023
    "%Y-%m-%d",  # 2023-03-15
    "%Y-%m",  # 2023-03
    "%b %Y",  # Mar 2023
)

_PMC_URL_TEMPLATE = "https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/"


class CitationStyle(StrEnum):
    """Citation styles this library ships a definition for."""

    NATURE = "nature"


class CitationFormatter:
    """Renders records in one citation style.

    Compiling a CSL definition is expensive, so a formatter holds a compiled
    style and is worth reusing across records.

    The rendered text is an **HTML fragment**: the style italicises journal names
    and emboldens volume numbers, and ``&`` arrives as ``&amp;``. Treat it as
    markup, not as plain text.

    Args:
        style: The style to render in.

    Raises:
        UnknownStyleError: If no definition is installed for ``style``.
    """

    def __init__(self, style: CitationStyle = CitationStyle.NATURE) -> None:
        self.style = style
        self._csl_style = _load_style(style)

    def format_citation(self, record: PubMedRecord) -> str:
        """Render one record.

        Args:
            record: The record to render.

        Returns:
            The citation as an HTML fragment.

        Examples:
            >>> from pmid_to_citation import Author, PubMedRecord
            >>> record = PubMedRecord(
            ...     pmid=1,
            ...     title="A short paper",
            ...     authors=[Author(last_name="Makar", initials="AB")],
            ...     journal_title="Biochem Med",
            ...     publication_date="1975",
            ... )
            >>> CitationFormatter().format_citation(record)
            'Makar, A. B. A short paper. <i>Biochem Med</i> (1975).'
        """
        return self.format_citations([record])[0]

    def format_citations(self, records: list[PubMedRecord]) -> list[str]:
        """Render several records, reusing the compiled style.

        Args:
            records: The records to render, in the order the output should follow.

        Returns:
            One citation per record, as HTML fragments. An empty input gives an
            empty list.
        """
        if not records:
            return []

        items = [_to_csl(record).model_dump(by_alias=True, exclude_none=True) for record in records]

        # citeproc ships no annotations, so everything it returns is untyped.
        # Naming that explicitly keeps the untyped boundary to these four lines
        # instead of letting it leak into the return value.
        bibliography: Any = CitationStylesBibliography(self._csl_style, CiteProcJSON(items))
        for item in items:
            bibliography.register(Citation([CitationItem(item["id"])]))
        entries: list[Any] = bibliography.bibliography()

        return [_clean(str(entry)) for entry in entries]


def _load_style(style: CitationStyle) -> CitationStylesStyle:
    """Compile the bundled CSL definition for a style.

    Args:
        style: The style to load.

    Returns:
        The compiled style.

    Raises:
        UnknownStyleError: If the package ships no definition for ``style``.
    """
    definition = resources.files(_STYLE_PACKAGE).joinpath(f"{style.value}.csl")
    if not definition.is_file():
        raise UnknownStyleError(f"no CSL definition is installed for style {style.value!r}")
    with definition.open("rb") as handle:
        # The bundled definitions are vendored and known-good, so skipping RelaxNG
        # validation costs nothing and avoids citeproc's schema warning.
        return CitationStylesStyle(handle, validate=False)


def _clean(rendered: str) -> str:
    """Turn one rendered bibliography entry into the citation callers want.

    Args:
        rendered: The entry as citeproc produced it.

    Returns:
        The entry without its bibliography index, with a doubled sentence-ending
        period collapsed, and with ``et al.`` italicised — which the Nature style
        does not do itself.
    """
    collapsed = rendered.replace("..", ".").replace("et al.", "<i>et al.</i>")
    return _BIBLIOGRAPHY_INDEX.sub("", collapsed, count=1)


def _to_csl(record: PubMedRecord) -> CslData:
    """Convert a record into the CSL item that citeproc consumes.

    Args:
        record: The record to convert.

    Returns:
        The CSL representation.
    """
    is_chapter = _is_chapter(record)
    data = CslData(
        type=CslType.CHAPTER if is_chapter else CslType.ARTICLE_JOURNAL,
        id=f"pmid{record.pmid}",
        title=record.title,
        author=[_to_csl_name(author) for author in record.authors],
        issued=_issued(record.publication_date),
        PMID=str(record.pmid),
    )

    # MEDLINE gives editors in an abbreviated and a spelled-out field; prefer the
    # abbreviated one, which is what the styles expect.
    editors = record.editors or record.full_editors
    if editors:
        data.editor = [_to_csl_name(editor) for editor in editors]

    if is_chapter:
        data.container_title = record.book_title or record.collection_title or record.volume_title
        data.publisher = record.publisher
        data.publisher_place = record.place_of_publication
        data.edition = record.edition
        data.chapter_number = record.chapter
        data.page = record.pagination
        data.ISBN = record.isbn
    else:
        data.container_title = record.journal_abbreviation or record.journal_title
        data.volume = record.volume
        data.issue = record.issue
        data.page = record.pagination

    for identifier in record.identifiers:
        if identifier.type.value == "doi":
            data.DOI = identifier.value
            break

    if record.pmc_id:
        data.URL = _PMC_URL_TEMPLATE.format(pmc_id=record.pmc_id)

    return data


def _is_chapter(record: PubMedRecord) -> bool:
    """Decide whether a record describes a book chapter rather than an article.

    Args:
        record: The record to classify.

    Returns:
        ``True`` for a chapter. PubMed labels chapters explicitly only sometimes,
        so a record with no journal but with book-shaped fields counts as one —
        that is what GeneReviews entries look like.
    """
    if any(publication_type.value == "Book Chapter" for publication_type in record.publication_types):
        return True
    if record.journal_title:
        return False
    return any(
        (
            record.book_title,
            record.collection_title,
            record.volume_title,
            record.publisher,
            record.isbn,
            record.editors,
            record.full_editors,
        )
    )


def _to_csl_name(person: Person) -> CslNameVariable:
    """Convert a person into a CSL name variable.

    Args:
        person: The person to convert.

    Returns:
        The CSL name.
    """
    return CslNameVariable(
        family=person.last_name,
        given=_given_name(person),
        suffix=person.suffix,
    )


def _given_name(person: Person) -> str:
    """Render a person's given name the way CSL styles expect it.

    MEDLINE packs initials without punctuation (``JA``), and CSL styles expect
    them spelled out with periods (``J. A.``).

    Args:
        person: The person whose given name is wanted.

    Returns:
        The formatted given name, or an empty string if the record has neither
        initials nor a spelled-out name.

    Examples:
        >>> from pmid_to_citation import Author
        >>> _given_name(Author(last_name="Makar", initials="AB"))
        'A. B.'
        >>> _given_name(Author(last_name="Smith", initials="", full_name="Smith, John A"))
        'John A'
    """
    given = person.initials
    if not given and person.full_name:
        # "Smith, John A" -> "John A"
        given = person.full_name.split(", ", 1)[1].strip() if ", " in person.full_name else person.full_name

    if not given:
        return ""

    # Run-together initials, e.g. "AB" or "RJH".
    if len(given) <= 4 and given.isupper() and " " not in given and "." not in given:
        return ". ".join(given) + "."

    # Space-separated initials that are missing their periods, e.g. "A B C".
    if len(given) <= 7 and " " in given and "." not in given and all(c.isupper() or c.isspace() for c in given):
        return ". ".join(given.split()) + "."

    return given


def _issued(publication_date: str | None) -> CslDateVariable | None:
    """Convert a PubMed publication date into a CSL date.

    Args:
        publication_date: The ``DP`` field value, if the record has one.

    Returns:
        The CSL date, or ``None`` if there is no date or it matches no known
        layout. PubMed dates range from a bare year to a full date, and some are
        ranges this library does not attempt to interpret.
    """
    if not publication_date:
        return None
    parts = _date_parts(publication_date)
    return CslDateVariable(date_parts=[parts]) if parts else None


def _date_parts(publication_date: str) -> list[int] | None:
    """Split a PubMed publication date into CSL date parts.

    Args:
        publication_date: The ``DP`` field value.

    Returns:
        ``[year]``, ``[year, month]``, or ``[year, month, day]``, or ``None`` if
        the value matches no known layout.
    """
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(publication_date.strip(), fmt)
        except ValueError:
            continue
        parts = [parsed.year]
        if "%m" in fmt or "%b" in fmt:
            parts.append(parsed.month)
        if "%d" in fmt:
            parts.append(parsed.day)
        return parts
    return None
