"""Internal models for Citation Style Language (CSL) data.

CSL is how this library reaches citeproc, and that is an implementation detail:
nothing here is public API. Keeping it internal is what allows the CSL rendering
back end to be replaced without an API break.

Field names follow the `CSL specification <https://docs.citationstyles.org/>`_,
which is why they are not all snake_case and why several are aliased.
"""

from collections.abc import Sequence
from enum import StrEnum
from typing import Annotated

import pydantic


class CslType(StrEnum):
    """CSL item types."""

    ARTICLE = "article"
    ARTICLE_JOURNAL = "article-journal"
    ARTICLE_MAGAZINE = "article-magazine"
    ARTICLE_NEWSPAPER = "article-newspaper"
    BILL = "bill"
    BOOK = "book"
    BROADCAST = "broadcast"
    CHAPTER = "chapter"
    CLASSIC = "classic"
    COLLECTION = "collection"
    DATASET = "dataset"
    DOCUMENT = "document"
    ENTRY = "entry"
    ENTRY_DICTIONARY = "entry-dictionary"
    ENTRY_ENCYCLOPEDIA = "entry-encyclopedia"
    EVENT = "event"
    FIGURE = "figure"
    GRAPHIC = "graphic"
    HEARING = "hearing"
    INTERVIEW = "interview"
    LEGAL_CASE = "legal_case"
    LEGISLATION = "legislation"
    MANUSCRIPT = "manuscript"
    MAP = "map"
    MOTION_PICTURE = "motion_picture"
    MUSICAL_SCORE = "musical_score"
    PAMPHLET = "pamphlet"
    PAPER_CONFERENCE = "paper-conference"
    PATENT = "patent"
    PERFORMANCE = "performance"
    PERIODICAL = "periodical"
    PERSONAL_COMMUNICATION = "personal_communication"
    POST = "post"
    POST_WEBLOG = "post-weblog"
    REGULATION = "regulation"
    REPORT = "report"
    REVIEW = "review"
    REVIEW_BOOK = "review-book"
    SOFTWARE = "software"
    SONG = "song"
    SPEECH = "speech"
    STANDARD = "standard"
    THESIS = "thesis"
    TREATY = "treaty"
    WEBPAGE = "webpage"


class CslNameVariable(pydantic.BaseModel):
    """CSL name variable (author, editor, etc.)."""

    family: str | None = None
    given: str | None = None
    dropping_particle: Annotated[str | None, pydantic.Field(alias="dropping-particle")] = None
    non_dropping_particle: Annotated[str | None, pydantic.Field(alias="non-dropping-particle")] = None
    suffix: str | None = None
    comma_suffix: Annotated[str | int | bool | None, pydantic.Field(alias="comma-suffix")] = None
    static_ordering: Annotated[str | int | bool | None, pydantic.Field(alias="static-ordering")] = None
    literal: str | None = None
    parse_names: Annotated[str | int | bool | None, pydantic.Field(alias="parse-names")] = None

    model_config = pydantic.ConfigDict(populate_by_name=True, extra="forbid", use_enum_values=True)


class CslDateVariable(pydantic.BaseModel):
    """CSL date variable."""

    date_parts: Annotated[Sequence[Sequence[str | int]] | None, pydantic.Field(alias="date-parts")] = None
    season: str | int | None = None
    circa: str | int | bool | None = None
    literal: str | None = None
    raw: str | None = None

    model_config = pydantic.ConfigDict(populate_by_name=True, extra="forbid", use_enum_values=True)

    @pydantic.field_validator("date_parts")
    @classmethod
    def _check_date_parts(cls, value: Sequence[Sequence[str | int]] | None) -> Sequence[Sequence[str | int]] | None:
        """Enforce the shape CSL defines for ``date-parts``.

        Args:
            value: The candidate value.

        Returns:
            The value unchanged.

        Raises:
            ValueError: If the outer sequence is not a single date or a range of
                two, or if a date does not hold one to three of year, month, day.
        """
        if value is None:
            return value
        if not 1 <= len(value) <= 2:
            raise ValueError("date-parts must have 1-2 elements")
        for date_part in value:
            if not 1 <= len(date_part) <= 3:
                raise ValueError("Each date-part must have 1-3 elements")
        return value


class CslData(pydantic.BaseModel):
    """CSL data item (bibliographic entry)."""

    # Required fields
    type: CslType
    id: str | int

    # Optional core fields
    citation_key: Annotated[str | None, pydantic.Field(alias="citation-key")] = None
    categories: list[str] | None = None
    language: str | None = None
    journal_abbreviation: Annotated[str | None, pydantic.Field(alias="journalAbbreviation")] = None
    short_title: Annotated[str | None, pydantic.Field(alias="shortTitle")] = None

    # Name variables
    author: list[CslNameVariable] | None = None
    chair: list[CslNameVariable] | None = None
    collection_editor: Annotated[list[CslNameVariable] | None, pydantic.Field(alias="collection-editor")] = None
    compiler: list[CslNameVariable] | None = None
    composer: list[CslNameVariable] | None = None
    container_author: Annotated[list[CslNameVariable] | None, pydantic.Field(alias="container-author")] = None
    contributor: list[CslNameVariable] | None = None
    curator: list[CslNameVariable] | None = None
    director: list[CslNameVariable] | None = None
    editor: list[CslNameVariable] | None = None
    editorial_director: Annotated[list[CslNameVariable] | None, pydantic.Field(alias="editorial-director")] = None
    executive_producer: Annotated[list[CslNameVariable] | None, pydantic.Field(alias="executive-producer")] = None
    guest: list[CslNameVariable] | None = None
    host: list[CslNameVariable] | None = None
    interviewer: list[CslNameVariable] | None = None
    illustrator: list[CslNameVariable] | None = None
    narrator: list[CslNameVariable] | None = None
    organizer: list[CslNameVariable] | None = None
    original_author: Annotated[list[CslNameVariable] | None, pydantic.Field(alias="original-author")] = None
    performer: list[CslNameVariable] | None = None
    producer: list[CslNameVariable] | None = None
    recipient: list[CslNameVariable] | None = None
    reviewed_author: Annotated[list[CslNameVariable] | None, pydantic.Field(alias="reviewed-author")] = None
    script_writer: Annotated[list[CslNameVariable] | None, pydantic.Field(alias="script-writer")] = None
    series_creator: Annotated[list[CslNameVariable] | None, pydantic.Field(alias="series-creator")] = None
    translator: list[CslNameVariable] | None = None

    # Date variables
    accessed: CslDateVariable | None = None
    available_date: Annotated[CslDateVariable | None, pydantic.Field(alias="available-date")] = None
    event_date: Annotated[CslDateVariable | None, pydantic.Field(alias="event-date")] = None
    issued: CslDateVariable | None = None
    original_date: Annotated[CslDateVariable | None, pydantic.Field(alias="original-date")] = None
    submitted: CslDateVariable | None = None

    # String variables
    abstract: str | None = None
    annote: str | None = None
    archive: str | None = None
    archive_collection: Annotated[str | None, pydantic.Field(alias="archive_collection")] = None
    archive_location: Annotated[str | None, pydantic.Field(alias="archive_location")] = None
    archive_place: Annotated[str | None, pydantic.Field(alias="archive-place")] = None
    authority: str | None = None
    call_number: Annotated[str | None, pydantic.Field(alias="call-number")] = None
    chapter_number: Annotated[str | int | None, pydantic.Field(alias="chapter-number")] = None
    citation_number: Annotated[str | int | None, pydantic.Field(alias="citation-number")] = None
    citation_label: Annotated[str | None, pydantic.Field(alias="citation-label")] = None
    collection_number: Annotated[str | int | None, pydantic.Field(alias="collection-number")] = None
    collection_title: Annotated[str | None, pydantic.Field(alias="collection-title")] = None
    container_title: Annotated[str | None, pydantic.Field(alias="container-title")] = None
    container_title_short: Annotated[str | None, pydantic.Field(alias="container-title-short")] = None
    dimensions: str | None = None
    division: str | None = None
    DOI: str | None = None
    edition: str | int | None = None
    event: str | None = None  # Deprecated
    event_title: Annotated[str | None, pydantic.Field(alias="event-title")] = None
    event_place: Annotated[str | None, pydantic.Field(alias="event-place")] = None
    first_reference_note_number: Annotated[str | int | None, pydantic.Field(alias="first-reference-note-number")] = None
    genre: str | None = None
    ISBN: str | None = None
    ISSN: str | None = None
    issue: str | int | None = None
    jurisdiction: str | None = None
    keyword: str | None = None
    locator: str | int | None = None
    medium: str | None = None
    note: str | None = None
    number: str | int | None = None
    number_of_pages: Annotated[str | int | None, pydantic.Field(alias="number-of-pages")] = None
    number_of_volumes: Annotated[str | int | None, pydantic.Field(alias="number-of-volumes")] = None
    original_publisher: Annotated[str | None, pydantic.Field(alias="original-publisher")] = None
    original_publisher_place: Annotated[str | None, pydantic.Field(alias="original-publisher-place")] = None
    original_title: Annotated[str | None, pydantic.Field(alias="original-title")] = None
    page: str | int | None = None
    page_first: Annotated[str | int | None, pydantic.Field(alias="page-first")] = None
    part: str | int | None = None
    part_title: Annotated[str | None, pydantic.Field(alias="part-title")] = None
    PMCID: str | None = None
    PMID: str | None = None
    printing: str | int | None = None
    publisher: str | None = None
    publisher_place: Annotated[str | None, pydantic.Field(alias="publisher-place")] = None
    references: str | None = None
    reviewed_genre: Annotated[str | None, pydantic.Field(alias="reviewed-genre")] = None
    reviewed_title: Annotated[str | None, pydantic.Field(alias="reviewed-title")] = None
    scale: str | None = None
    section: str | None = None
    source: str | None = None
    status: str | None = None
    supplement: str | int | None = None
    title: str | None = None
    title_short: Annotated[str | None, pydantic.Field(alias="title-short")] = None
    URL: str | None = None
    version: str | None = None
    volume: str | int | None = None
    volume_title: Annotated[str | None, pydantic.Field(alias="volume-title")] = None
    volume_title_short: Annotated[str | None, pydantic.Field(alias="volume-title-short")] = None
    year_suffix: Annotated[str | None, pydantic.Field(alias="year-suffix")] = None

    # Custom fields
    custom: dict[str, object] | None = None

    model_config = pydantic.ConfigDict(populate_by_name=True, extra="forbid", use_enum_values=True)
