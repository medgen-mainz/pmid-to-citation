"""Tests for citation rendering and for the record-to-CSL conversion."""

# These are white-box tests: the CSL conversion helpers are module-private
# because CSL is an implementation detail, but they are where the logic lives.
# pyright: reportPrivateUsage=false

import pytest

from pmid_to_citation import (
    Author,
    CitationFormatter,
    CitationStyle,
    Editor,
    Identifier,
    IdentifierType,
    Person,
    PublicationType,
    PubMedRecord,
    UnknownStyleError,
)
from pmid_to_citation._csl import CslType
from pmid_to_citation.formatter import _clean, _date_parts, _given_name, _issued, _load_style, _to_csl


@pytest.fixture(scope="module")
def formatter() -> CitationFormatter:
    """A Nature formatter, shared because compiling a CSL style is expensive."""
    return CitationFormatter()


@pytest.fixture
def article() -> PubMedRecord:
    """A journal article with every field the Nature style uses."""
    return PubMedRecord(
        pmid=12345678,
        title="A Revolutionary Discovery in Molecular Biology",
        authors=[
            Author(last_name="Smith", initials="J A", full_name="John A Smith"),
            Author(last_name="Johnson", initials="M", suffix="Jr.", full_name="Mary Johnson Jr."),
        ],
        journal_title="Nature",
        volume="615",
        issue="7952",
        pagination="123-130",
        publication_date="2023 Mar 15",
        identifiers=[Identifier(value="10.1038/s41586-023-12345-6", type=IdentifierType.DOI)],
        pmc_id="PMC9876543",
        publication_types=[PublicationType.JOURNAL_ARTICLE],
    )


@pytest.fixture
def chapter() -> PubMedRecord:
    """A book chapter, as GeneReviews entries appear in PubMed."""
    return PubMedRecord(
        pmid=20301598,
        title="C3 Glomerulopathy",
        authors=[Author(last_name="Martín", initials="B"), Author(last_name="Smith", initials="RJH")],
        book_title="GeneReviews(®)",
        editors=[Editor(last_name="Adam", initials="MP"), Editor(last_name="Feldman", initials="J")],
        publisher="University of Washington, Seattle",
        place_of_publication="Seattle (WA)",
        publication_date="1993",
        publication_types=[PublicationType.REVIEW, PublicationType.BOOK_CHAPTER],
        isbn="978-0123456789",
        chapter="5",
        pagination="123-145",
        edition="2nd",
    )


class TestCitationStyle:
    def test_nature_is_available(self) -> None:
        assert CitationStyle.NATURE == "nature"

    def test_a_definition_ships_for_every_style(self) -> None:
        for style in CitationStyle:
            assert CitationFormatter(style).style is style


class TestLoadStyle:
    def test_a_style_with_no_bundled_definition_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Point the loader at a package that holds no .csl files.
        monkeypatch.setattr("pmid_to_citation.formatter._STYLE_PACKAGE", "pmid_to_citation")
        with pytest.raises(UnknownStyleError, match="no CSL definition is installed for style 'nature'"):
            _load_style(CitationStyle.NATURE)

    def test_an_unknown_style_error_is_a_citation_format_error(self) -> None:
        from pmid_to_citation import CitationFormatError

        assert issubclass(UnknownStyleError, CitationFormatError)


class TestClean:
    def test_the_bibliography_index_is_stripped(self) -> None:
        assert _clean("1.Mocked Citation") == "Mocked Citation"

    def test_a_multi_digit_index_is_stripped(self) -> None:
        assert _clean("42.Mocked Citation") == "Mocked Citation"

    def test_only_the_leading_index_is_stripped(self) -> None:
        assert _clean("1.Smith, J. A. 5. things happened.") == "Smith, J. A. 5. things happened."

    def test_a_doubled_sentence_period_is_collapsed(self) -> None:
        assert _clean("1.Roe, R.. A paper.") == "Roe, R. A paper."

    def test_et_al_is_italicised(self) -> None:
        assert _clean("1.Smith, J. et al. A paper.") == "Smith, J. <i>et al.</i> A paper."


class TestGivenName:
    @pytest.mark.parametrize(
        ("initials", "expected"),
        [
            ("AB", "A. B."),
            ("A", "A."),
            ("RJH", "R. J. H."),
            ("J A", "J. A."),
            ("A B C", "A. B. C."),
            ("J. A. B.", "J. A. B."),
            ("Ja Bc", "Ja Bc"),
            ("A B C D E F G H", "A B C D E F G H"),
        ],
    )
    def test_initials_are_spelled_out_with_periods(self, initials: str, expected: str) -> None:
        assert _given_name(Person(last_name="Smith", initials=initials)) == expected

    def test_a_spelled_out_name_is_used_when_there_are_no_initials(self) -> None:
        person = Person(last_name="Smith", initials="", full_name="Smith, John Andrew")
        assert _given_name(person) == "John Andrew"

    def test_a_spelled_out_name_without_a_comma_is_used_whole(self) -> None:
        person = Person(last_name="Smith", initials="", full_name="John Andrew Smith")
        assert _given_name(person) == "John Andrew Smith"

    def test_neither_initials_nor_a_name_gives_nothing(self) -> None:
        assert _given_name(Person(last_name="Smith", initials="")) == ""


class TestDateParts:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("2023 Mar 15", [2023, 3, 15]),
            ("2023 Mar", [2023, 3]),
            ("2023", [2023]),
            ("2023-03-15", [2023, 3, 15]),
            ("2023-03", [2023, 3]),
            ("Mar 2023", [2023, 3]),
            ("  2023 Mar 15  ", [2023, 3, 15]),
        ],
    )
    def test_recognised_layouts(self, value: str, expected: list[int]) -> None:
        assert _date_parts(value) == expected

    @pytest.mark.parametrize(
        "value",
        ["not a date", "2023/13/45", "March 32, 2023", "2023-13-01", "2020 Jan-Feb", ""],
    )
    def test_unrecognised_layouts_give_none(self, value: str) -> None:
        assert _date_parts(value) is None

    def test_no_date_gives_no_csl_date(self) -> None:
        assert _issued(None) is None
        assert _issued("") is None

    def test_an_unparseable_date_gives_no_csl_date(self) -> None:
        assert _issued("sometime in the nineties") is None

    def test_a_parseable_date_becomes_csl_date_parts(self) -> None:
        issued = _issued("2023 Mar 15")
        assert issued is not None
        assert issued.date_parts == [[2023, 3, 15]]


class TestToCslArticle:
    def test_a_complete_article(self, article: PubMedRecord) -> None:
        data = _to_csl(article)
        assert data.type == CslType.ARTICLE_JOURNAL
        assert data.id == "pmid12345678"
        assert data.title == "A Revolutionary Discovery in Molecular Biology"
        assert data.container_title == "Nature"
        assert (data.volume, data.issue, data.page) == ("615", "7952", "123-130")
        assert data.PMID == "12345678"
        assert data.DOI == "10.1038/s41586-023-12345-6"
        assert data.URL == "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9876543/"
        assert data.issued is not None and data.issued.date_parts == [[2023, 3, 15]]

    def test_authors_carry_their_initials_and_suffix(self, article: PubMedRecord) -> None:
        authors = _to_csl(article).author
        assert authors is not None
        assert (authors[0].family, authors[0].given) == ("Smith", "J. A.")
        assert (authors[1].family, authors[1].given, authors[1].suffix) == ("Johnson", "M.", "Jr.")

    def test_an_author_without_a_suffix_has_none(self) -> None:
        record = PubMedRecord(pmid=1, authors=[Author(last_name="Doe", initials="J")])
        authors = _to_csl(record).author
        assert authors is not None and authors[0].suffix is None

    def test_the_journal_abbreviation_is_preferred_over_the_full_title(self) -> None:
        record = PubMedRecord(pmid=1, journal_title="Biochemical Medicine", journal_abbreviation="Biochem Med")
        assert _to_csl(record).container_title == "Biochem Med"

    def test_a_minimal_record(self) -> None:
        data = _to_csl(PubMedRecord(pmid=87654321, title="Minimal Record"))
        assert data.type == CslType.ARTICLE_JOURNAL
        assert data.id == "pmid87654321"
        assert data.author == []
        assert data.editor is None
        assert (data.container_title, data.issued, data.DOI, data.URL) == (None, None, None, None)

    def test_a_record_without_a_doi(self, article: PubMedRecord) -> None:
        article.identifiers = [Identifier(value="12345", type=IdentifierType.PMC)]
        assert _to_csl(article).DOI is None

    def test_the_first_doi_wins(self) -> None:
        record = PubMedRecord(
            pmid=1,
            identifiers=[
                Identifier(value="s41586", type=IdentifierType.PII),
                Identifier(value="10.1/first", type=IdentifierType.DOI),
                Identifier(value="10.1/second", type=IdentifierType.DOI),
            ],
        )
        assert _to_csl(record).DOI == "10.1/first"

    def test_a_record_without_a_pmc_id_has_no_url(self, article: PubMedRecord) -> None:
        article.pmc_id = None
        assert _to_csl(article).URL is None


class TestToCslChapter:
    def test_an_explicitly_labelled_chapter(self, chapter: PubMedRecord) -> None:
        data = _to_csl(chapter)
        assert data.type == CslType.CHAPTER
        assert data.container_title == "GeneReviews(®)"
        assert data.publisher == "University of Washington, Seattle"
        assert data.publisher_place == "Seattle (WA)"
        assert (data.ISBN, data.chapter_number, data.page, data.edition) == (
            "978-0123456789",
            "5",
            "123-145",
            "2nd",
        )
        # Journal-only fields stay unset.
        assert (data.volume, data.issue) == (None, None)

    @pytest.mark.parametrize(
        "field",
        ["book_title", "collection_title", "volume_title", "publisher", "isbn"],
    )
    def test_a_book_shaped_field_without_a_journal_implies_a_chapter(self, field: str) -> None:
        record = PubMedRecord(pmid=1, title="Chapter")
        setattr(record, field, "a value")
        assert _to_csl(record).type == CslType.CHAPTER

    def test_editors_without_a_journal_imply_a_chapter(self) -> None:
        record = PubMedRecord(pmid=1, editors=[Editor(last_name="Adam", initials="MP")])
        assert _to_csl(record).type == CslType.CHAPTER

    def test_spelled_out_editors_without_a_journal_imply_a_chapter(self) -> None:
        record = PubMedRecord(pmid=1, full_editors=[Editor.from_full_form("Adam, Margaret P")])
        assert _to_csl(record).type == CslType.CHAPTER

    def test_a_journal_title_beats_book_shaped_fields(self) -> None:
        record = PubMedRecord(pmid=1, journal_title="Nature", publisher="Springer")
        assert _to_csl(record).type == CslType.ARTICLE_JOURNAL

    def test_an_explicit_chapter_label_beats_a_journal_title(self) -> None:
        record = PubMedRecord(
            pmid=1,
            journal_title="Nature",
            publication_types=[PublicationType.BOOK_CHAPTER],
        )
        assert _to_csl(record).type == CslType.CHAPTER

    def test_a_bare_record_is_not_a_chapter(self) -> None:
        assert _to_csl(PubMedRecord(pmid=1)).type == CslType.ARTICLE_JOURNAL

    @pytest.mark.parametrize(
        ("fields", "expected"),
        [
            ({"book_title": "Book", "collection_title": "Collection"}, "Book"),
            ({"collection_title": "Collection", "volume_title": "Volume"}, "Collection"),
            ({"volume_title": "Volume"}, "Volume"),
        ],
    )
    def test_the_container_title_falls_back_through_the_book_fields(
        self, fields: dict[str, str], expected: str
    ) -> None:
        record = PubMedRecord(pmid=1)
        for field, value in fields.items():
            setattr(record, field, value)
        assert _to_csl(record).container_title == expected

    def test_a_chapter_keeps_its_doi_and_pmc_url(self) -> None:
        record = PubMedRecord(
            pmid=1,
            book_title="Test Book",
            publication_types=[PublicationType.BOOK_CHAPTER],
            identifiers=[Identifier(value="10.1234/test.chapter", type=IdentifierType.DOI)],
            pmc_id="PMC12345",
        )
        data = _to_csl(record)
        assert data.DOI == "10.1234/test.chapter"
        assert data.URL == "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12345/"


class TestEditors:
    def test_abbreviated_editors_are_preferred(self) -> None:
        record = PubMedRecord(
            pmid=1,
            book_title="Book",
            editors=[Editor(last_name="Primary", initials="A")],
            full_editors=[Editor(last_name="Secondary", initials="B"), Editor(last_name="Tertiary", initials="C")],
        )
        editors = _to_csl(record).editor
        assert editors is not None
        assert [editor.family for editor in editors] == ["Primary"]

    def test_spelled_out_editors_are_used_when_there_are_no_others(self) -> None:
        record = PubMedRecord(
            pmid=1,
            book_title="Book",
            editors=[],
            full_editors=[Editor(last_name="Full", initials="A"), Editor(last_name="Editor", initials="B")],
        )
        editors = _to_csl(record).editor
        assert editors is not None
        assert [editor.family for editor in editors] == ["Full", "Editor"]

    def test_editor_initials_are_spelled_out(self, chapter: PubMedRecord) -> None:
        editors = _to_csl(chapter).editor
        assert editors is not None
        assert (editors[0].family, editors[0].given) == ("Adam", "M. P.")

    def test_an_editor_suffix_is_kept(self) -> None:
        record = PubMedRecord(
            pmid=1,
            book_title="Book",
            editors=[Editor(last_name="Smith", initials="J", suffix="Jr.")],
        )
        editors = _to_csl(record).editor
        assert editors is not None and editors[0].suffix == "Jr."

    def test_a_record_with_no_editors_has_none(self, article: PubMedRecord) -> None:
        assert _to_csl(article).editor is None


class TestRendering:
    def test_a_complete_article_renders_in_nature_style(self, formatter: CitationFormatter) -> None:
        record = PubMedRecord(
            pmid=35642643,
            title="CRISPR-Cas9 gene editing for sickle cell disease and β-thalassemia",
            authors=[
                Author(last_name="Frangoul", initials="H"),
                Author(last_name="Altshuler", initials="D"),
                Author(last_name="Cappellini", initials="M D"),
            ],
            journal_title="The New England Journal of Medicine",
            volume="384",
            issue="3",
            pagination="252-260",
            publication_date="2021 Jan 21",
            identifiers=[Identifier(value="10.1056/NEJMoa2031054", type=IdentifierType.DOI)],
        )

        assert formatter.format_citation(record) == (
            "Frangoul, H., Altshuler, D. &amp; Cappellini, M. D. CRISPR-Cas9 gene editing for sickle cell "
            "disease and β-thalassemia. <i>The New England Journal of Medicine</i> <b>384</b>, 252–260 (2021)."
        )

    def test_a_record_without_authors_still_renders(self, formatter: CitationFormatter) -> None:
        record = PubMedRecord(pmid=1, title="Anonymous Article", journal_title="Test Journal", publication_date="2023")
        citation = formatter.format_citation(record)
        assert "Anonymous Article" in citation
        assert "Test Journal" in citation

    def test_a_record_with_only_a_pmid_still_renders(self, formatter: CitationFormatter) -> None:
        assert isinstance(formatter.format_citation(PubMedRecord(pmid=12345)), str)

    @pytest.mark.parametrize("date", ["2023 Mar 15", "2023 Mar", "2023", "2023-03-15", "Mar 2023", "no date at all"])
    def test_every_date_layout_renders(self, formatter: CitationFormatter, date: str) -> None:
        record = PubMedRecord(pmid=1, title="Test", authors=[Author(last_name="Test", initials="A")])
        record.publication_date = date
        assert formatter.format_citation(record)

    def test_a_chapter_names_its_editors(self, formatter: CitationFormatter, chapter: PubMedRecord) -> None:
        citation = formatter.format_citation(chapter)
        assert "Martín" in citation
        assert "C3 Glomerulopathy" in citation
        assert "GeneReviews" in citation
        assert "University of Washington" in citation
        assert "1993" in citation
        assert "eds." in citation or "ed." in citation

    def test_many_authors_are_abbreviated_with_an_italicised_et_al(self, formatter: CitationFormatter) -> None:
        record = PubMedRecord(
            pmid=1,
            title="A paper with many authors",
            authors=[Author(last_name=f"Author{i}", initials="A") for i in range(10)],
            journal_title="Nature",
            publication_date="2023",
        )
        assert "<i>et al.</i>" in formatter.format_citation(record)


class TestRenderingSeveralRecords:
    def test_no_records_gives_no_citations(self, formatter: CitationFormatter) -> None:
        assert formatter.format_citations([]) == []

    def test_one_record(self, formatter: CitationFormatter, article: PubMedRecord) -> None:
        assert formatter.format_citations([article]) == [formatter.format_citation(article)]

    def test_several_records_keep_their_order(self, formatter: CitationFormatter, article: PubMedRecord) -> None:
        second = PubMedRecord(
            pmid=87654321,
            title="Another Important Study",
            authors=[Author(last_name="Doe", initials="J")],
            journal_title="Science",
            publication_date="2022",
        )

        citations = formatter.format_citations([article, second])

        assert len(citations) == 2
        assert "Smith" in citations[0]
        assert "Doe" in citations[1]

    def test_batch_and_single_rendering_agree(self, formatter: CitationFormatter, chapter: PubMedRecord) -> None:
        # These went through different post-processing before the port.
        records = [chapter, PubMedRecord(pmid=2, title="Second", journal_title="Nature", publication_date="2020")]
        assert formatter.format_citations(records) == [formatter.format_citation(record) for record in records]
