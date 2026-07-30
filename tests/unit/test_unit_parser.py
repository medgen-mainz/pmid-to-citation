"""Tests for the MEDLINE parser.

The snapshot test is the safety net for the recorded fixtures; the rest of the
file pins down the behaviour of individual field tags and of the line grammar.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from pmid_to_citation import (
    IdentifierType,
    ISSNType,
    LanguageCode,
    Owner,
    PublicationStatus,
    PublicationType,
    PubMedRecord,
    RecordParseError,
    parse_medline,
    parse_medline_file,
)
from tests.conftest import ALL_FIXTURES, MEDLINE_DIR

SNAPSHOT_FIXTURES = ["1.txt", "11181995.txt", "20301598.txt", "26432245.txt", "35642643.txt", "37940764.txt"]


def parse(*lines: str) -> PubMedRecord:
    """Parse a record assembled from the given field lines, adding a PMID."""
    return parse_medline("\n".join(("PMID- 12345", *lines)))


@pytest.mark.parametrize("filename", SNAPSHOT_FIXTURES)
def test_parse_medline_snapshot(filename: str, snapshot_json: object) -> None:
    """Every recorded record parses to exactly the same shape as before."""
    record = parse_medline_file(MEDLINE_DIR / filename)
    dumped = record.model_dump()

    # PubMed does not guarantee an order for repeated fields, so sort the ones
    # whose order carries no meaning before comparing.
    sort_keys = {
        "authors": ("last_name", "initials"),
        "full_authors": ("last_name", "full_name"),
        "grants": ("grant_id",),
        "substances": ("registry_number", "name"),
        "mesh_terms": ("descriptor",),
        "issn_list": ("issn", "type"),
        "identifiers": ("type", "value"),
        "publication_history": ("date", "type"),
    }
    for field, keys in sort_keys.items():
        entries: list[dict[str, Any]] = dumped[field]
        dumped[field] = sorted(entries, key=lambda entry: tuple(str(entry[key]) for key in keys))
    dumped["publication_types"] = sorted(dumped["publication_types"])

    assert dumped == snapshot_json


class TestRecordedFixtures:
    @pytest.mark.parametrize("filename", ALL_FIXTURES)
    def test_pmid_matches_the_filename(self, filename: str) -> None:
        assert parse_medline_file(MEDLINE_DIR / filename).pmid == int(Path(filename).stem)

    @pytest.mark.parametrize("filename", ALL_FIXTURES)
    def test_every_record_has_a_title_a_container_and_a_date(self, filename: str) -> None:
        record = parse_medline_file(MEDLINE_DIR / filename)
        assert record.title is not None
        assert record.journal_abbreviation or record.journal_title or record.book_title
        assert record.publication_date is not None
        assert record.authors

    def test_a_consortium_paper_keeps_all_its_authors(self) -> None:
        record = parse_medline_file(MEDLINE_DIR / "26432245.txt")
        assert len(record.authors) >= 10
        assert record.abstract
        assert record.grants

    def test_the_oldest_record_has_no_abstract(self) -> None:
        record = parse_medline_file(MEDLINE_DIR / "1.txt")
        assert record.abstract is None
        assert len(record.authors) == 4
        assert record.authors[0].last_name == "Makar"
        assert record.mesh_terms
        assert record.substances

    def test_a_book_record_has_a_book_title_and_editors(self) -> None:
        record = parse_medline_file(MEDLINE_DIR / "20301598.txt")
        assert record.book_title
        assert record.editors or record.full_editors


class TestLineGrammar:
    def test_empty_input(self) -> None:
        with pytest.raises(RecordParseError, match="empty input"):
            parse_medline("")

    def test_missing_pmid(self) -> None:
        with pytest.raises(RecordParseError, match="missing required PMID field"):
            parse_medline("TI  - Some title\nAU  - Smith J")

    def test_unparseable_pmid_says_so(self) -> None:
        with pytest.raises(RecordParseError, match="invalid PMID"):
            parse_medline("PMID- not-a-number\nTI  - Some title")

    def test_content_before_the_first_tag_reports_its_line(self) -> None:
        with pytest.raises(RecordParseError, match="line 1: malformed line") as excinfo:
            parse_medline("stray text\nPMID- 1")
        assert excinfo.value.line_number == 1

    def test_indented_continuation_lines_are_folded_into_one_value(self) -> None:
        record = parse_medline(
            "PMID- 123\nTI  - Human C-terminal CUBN variants associate with chronic proteinuria and normal \n"
            "      renal function."
        )
        assert (
            record.title
            == "Human C-terminal CUBN variants associate with chronic proteinuria and normal renal function."
        )

    def test_unindented_continuation_lines_are_folded_too(self) -> None:
        record = parse_medline("PMID- 123\nTI  - A title split\nacross lines")
        assert record.title == "A title split across lines"

    def test_blank_lines_are_ignored(self) -> None:
        record = parse_medline("PMID- 123\n\nTI  - A title\n   \nAB  - An abstract")
        assert (record.title, record.abstract) == ("A title", "An abstract")

    def test_a_value_already_ending_in_a_space_is_not_double_spaced(self) -> None:
        record = parse_medline("PMID- 123\nTI  - A title \n      continued")
        assert record.title == "A title continued"

    def test_repeated_tags_accumulate(self) -> None:
        record = parse("AU  - Smith AB", "AU  - Jones CD")
        assert [author.last_name for author in record.authors] == ["Smith", "Jones"]

    def test_a_tag_with_an_empty_value_is_dropped(self) -> None:
        assert parse("TI  - ").title is None

    def test_parse_medline_file_accepts_a_string_path(self) -> None:
        assert parse_medline_file(str(MEDLINE_DIR / "1.txt")).pmid == 1

    def test_parse_medline_file_reports_a_missing_file(self) -> None:
        with pytest.raises(OSError, match="No such file"):
            parse_medline_file(MEDLINE_DIR / "does-not-exist.txt")


class TestUnmodelledFields:
    def test_an_unknown_tag_is_kept_verbatim(self) -> None:
        record = parse("XYZ - Unknown field value", "XYZ - Second value")
        assert record.other_fields["XYZ"] == ["Unknown field value", "Second value"]

    def test_a_value_the_handler_cannot_interpret_is_kept_verbatim(self) -> None:
        # A malformed publication history entry must not be silently dropped.
        record = parse("PHST- garbage without a type")
        assert record.publication_history == []
        assert record.other_fields["PHST"] == ["garbage without a type"]


class TestEnumFields:
    @pytest.mark.parametrize(
        ("line", "attribute", "expected"),
        [
            ("OWN - NLM", "owner", Owner.NLM),
            ("STAT- MEDLINE", "status", PublicationStatus.MEDLINE),
            ("LA  - eng", "language", LanguageCode.ENG),
        ],
    )
    def test_known_values_are_recognised(self, line: str, attribute: str, expected: object) -> None:
        assert getattr(parse(line), attribute) is expected

    @pytest.mark.parametrize(
        ("line", "attribute"),
        [
            ("OWN - INVENTED", "owner"),
            ("STAT- INVENTED", "status"),
            ("LA  - xyz", "language"),
        ],
    )
    def test_unknown_values_leave_the_field_unset(self, line: str, attribute: str) -> None:
        # PubMed extends its vocabularies; one new term must not fail a record.
        assert getattr(parse(line), attribute) is None

    def test_a_known_publication_type_is_collected(self) -> None:
        assert parse("PT  - Journal Article").publication_types == [PublicationType.JOURNAL_ARTICLE]

    def test_an_unknown_publication_type_is_skipped(self) -> None:
        assert parse("PT  - Invented Type").publication_types == []


class TestIssnField:
    def test_medium_in_parentheses(self) -> None:
        issns = parse("IS  - 1558-8238 (Electronic)").issn_list
        assert (issns[0].issn, issns[0].type) == ("1558-8238", ISSNType.ELECTRONIC)

    def test_no_medium_defaults_to_print(self) -> None:
        issns = parse("IS  - 0021-9738").issn_list
        assert (issns[0].issn, issns[0].type) == ("0021-9738", ISSNType.PRINT)

    def test_trailing_check_digit_x_is_accepted(self) -> None:
        assert parse("IS  - 0021-973X").issn_list[0].issn == "0021-973X"

    def test_an_unmodelled_medium_is_skipped(self) -> None:
        assert parse("IS  - 1558-8238 (Holographic)").issn_list == []

    def test_a_value_that_is_not_an_issn_is_skipped(self) -> None:
        assert parse("IS  - not an issn").issn_list == []


class TestArticleIdentifierField:
    def test_tagged_doi(self) -> None:
        identifiers = parse("AID - 10.1172/JCI161852 [doi]").identifiers
        assert (identifiers[0].value, identifiers[0].type) == ("10.1172/JCI161852", IdentifierType.DOI)

    def test_tagged_pii(self) -> None:
        assert parse("AID - 161852 [pii]").identifiers[0].type is IdentifierType.PII

    def test_an_unmodelled_tag_is_skipped(self) -> None:
        assert parse("AID - something [invented]").identifiers == []

    def test_an_untagged_value_shaped_like_a_doi_is_taken_as_one(self) -> None:
        identifiers = parse("AID - 10.1234/abc").identifiers
        assert (identifiers[0].value, identifiers[0].type) == ("10.1234/abc", IdentifierType.DOI)

    def test_an_untagged_value_not_shaped_like_a_doi_is_skipped(self) -> None:
        assert parse("AID - plain text").identifiers == []


class TestScalarAndListFields:
    def test_book_title_expands_the_registered_trademark_sign(self) -> None:
        assert parse("BTI - GeneReviews(®)").book_title == "GeneReviews®"

    def test_number_of_references(self) -> None:
        assert parse("RF  - 25").number_of_references == 25

    def test_a_non_numeric_reference_count_is_ignored(self) -> None:
        assert parse("RF  - many").number_of_references is None

    @pytest.mark.parametrize(
        ("line", "attribute", "expected"),
        [
            ("TI  - A title", "title", "A title"),
            ("TT  - Transliterated", "transliterated_title", "Transliterated"),
            ("AB  - An abstract", "abstract", "An abstract"),
            ("VI  - 615", "volume", "615"),
            ("IP  - 7952", "issue", "7952"),
            ("DP  - 2023 Mar", "publication_date", "2023 Mar"),
            ("PG  - 117-26", "pagination", "117-26"),
            ("LR  - 20220601", "last_revision_date", "20220601"),
            ("CTI - Collection", "collection_title", "Collection"),
            ("VTI - Volume", "volume_title", "Volume"),
            ("CP  - 5", "chapter", "5"),
            ("EN  - 3rd", "edition", "3rd"),
            ("PB  - Academic Press", "publisher", "Academic Press"),
            ("ISBN- 978-0123456789", "isbn", "978-0123456789"),
            ("DEP - 20220101", "electronic_publication_date", "20220101"),
            ("CTDT- 20220201", "contribution_date", "20220201"),
            ("DRDT- 20220301", "revision_date", "20220301"),
            ("PL  - England", "place_of_publication", "England"),
            ("TA  - Biochem Med", "journal_abbreviation", "Biochem Med"),
            ("JT  - Biochemical Medicine", "journal_title", "Biochemical Medicine"),
            ("JID - 0151424", "journal_id", "0151424"),
            ("SB  - IM", "subset", "IM"),
            ("OTO - Custom", "other_term_owner", "Custom"),
            ("MID - MS001", "manuscript_id", "MS001"),
            ("PST- ppublish", "publication_status", "ppublish"),
            ("SO  - Biochem Med. 1975", "source", "Biochem Med. 1975"),
            ("PMC - PMC123", "pmc_id", "PMC123"),
            ("PMCR- 2023/01/01", "pmc_release_date", "2023/01/01"),
            ("CI  - Copyright 2022", "copyright_information", "Copyright 2022"),
            ("OCI - Other copyright", "other_copyright_information", "Other copyright"),
            ("COI - No conflicts", "conflict_of_interest", "No conflicts"),
            ("GN  - A note", "general_note", "A note"),
            ("SFM - Mission Alpha", "space_flight_mission", "Mission Alpha"),
            ("DCOM- 20220701", "completion_date", "20220701"),
        ],
    )
    def test_plain_string_fields(self, line: str, attribute: str, expected: str) -> None:
        assert getattr(parse(line), attribute) == expected

    @pytest.mark.parametrize(
        ("line", "attribute", "expected"),
        [
            ("CN  - WHO Group", "corporate_authors", ["WHO Group"]),
            ("GS  - BRCA1", "gene_symbols", ["BRCA1"]),
            ("OT  - Special Term", "other_terms", ["Special Term"]),
            ("LID - 10.1234/x [doi]", "location_ids", ["10.1234/x [doi]"]),
            ("OID - OTHER123", "other_ids", ["OTHER123"]),
            ("SI  - GENBANK/X123", "secondary_source_ids", ["GENBANK/X123"]),
        ],
    )
    def test_plain_list_fields(self, line: str, attribute: str, expected: list[str]) -> None:
        assert getattr(parse(line), attribute) == expected

    @pytest.mark.parametrize(
        ("line", "attribute", "expected"),
        [
            ("EDAT- 2022/06/02 06:00", "entry_date", datetime(2022, 6, 2, 6, 0)),
            ("MHDA- 2022/06/03 06:00", "mesh_date", datetime(2022, 6, 3, 6, 0)),
            ("CRDT- 2022/06/01 06:03", "create_date", datetime(2022, 6, 1, 6, 3)),
        ],
    )
    def test_timestamp_fields(self, line: str, attribute: str, expected: datetime) -> None:
        assert getattr(parse(line), attribute) == expected

    def test_an_unparseable_timestamp_leaves_the_field_unset(self) -> None:
        assert parse("EDAT- garbage").entry_date is None

    def test_parsed_list_fields(self) -> None:
        record = parse(
            "GR  - F32 AG064886/AG/NIA NIH HHS/United States",
            "MH  - Body Fluids/*analysis",
            "RN  - 0 (Formates)",
            "NM  - Aspirin",
            "PHST- 2022/06/01 06:03 [entrez]",
        )
        assert record.grants[0].grant_id == "F32 AG064886"
        assert record.mesh_terms[0].descriptor == "Body Fluids"
        assert [s.name for s in record.substances] == ["Formates", "Aspirin"]
        assert record.publication_history[0].date == datetime(2022, 6, 1, 6, 3)


class TestPeopleFields:
    def test_short_and_full_forms_land_in_separate_lists(self) -> None:
        record = parse("AU  - Smith AB", "FAU - Smith, Alice B")
        assert record.authors[0].initials == "AB"
        assert record.full_authors[0].full_name == "Smith, Alice B"

    @pytest.mark.parametrize(
        ("lines", "attribute", "expected_surname"),
        [
            (("ED  - Jones AB",), "editors", "Jones"),
            (("FED - Jones, Alice B",), "full_editors", "Jones"),
            (("IR  - Brown CD",), "investigators", "Brown"),
            (("FIR - Brown, Charles D",), "full_investigators", "Brown"),
            (("PS  - Einstein A",), "personal_name_subjects", "Einstein"),
            (("FPS - Einstein, Albert",), "full_personal_name_subjects", "Einstein"),
        ],
    )
    def test_every_kind_of_person(self, lines: tuple[str, ...], attribute: str, expected_surname: str) -> None:
        assert getattr(parse(*lines), attribute)[0].last_name == expected_surname

    def test_affiliation_and_identifier_attach_to_the_spelled_out_name(self) -> None:
        record = parse("FAU - Smith, John A", "AD  - Dept of Medicine", "AUID- 0000-0001")
        assert record.full_authors[0].affiliation == "Dept of Medicine"
        assert record.full_authors[0].identifier == "0000-0001"

    def test_affiliation_and_identifier_fall_back_to_the_short_name(self) -> None:
        record = parse("AU  - Smith AB", "AD  - University", "AUID- ORCID123")
        assert record.full_authors == []
        assert record.authors[0].affiliation == "University"
        assert record.authors[0].identifier == "ORCID123"

    def test_an_affiliation_with_no_preceding_name_is_dropped(self) -> None:
        record = parse("AD  - University with nobody to attach to")
        assert record.authors == [] and record.full_authors == []

    def test_investigator_affiliation_prefers_the_spelled_out_name(self) -> None:
        record = parse("FIR - Brown, Charles D", "IRAD- Research Institute")
        assert record.full_investigators[0].affiliation == "Research Institute"

    def test_investigator_affiliation_falls_back_to_the_short_name(self) -> None:
        record = parse("IR  - Brown CD", "IRAD- Research Lab")
        assert record.investigators[0].affiliation == "Research Lab"

    def test_an_investigator_affiliation_with_no_preceding_name_is_dropped(self) -> None:
        assert parse("IRAD- Nobody's lab").investigators == []


class TestOtherAbstracts:
    def test_language_attaches_to_the_preceding_abstract(self) -> None:
        record = parse("OAB - Un resumen", "OABL- Spanish")
        assert record.other_abstracts[0].text == "Un resumen"
        assert record.other_abstracts[0].language == "Spanish"

    def test_a_language_with_no_preceding_abstract_is_dropped(self) -> None:
        assert parse("OABL- Spanish").other_abstracts == []


class TestCrossReferenceFields:
    @pytest.mark.parametrize(
        ("tag", "attribute"),
        [
            ("EFR", "erratum_for"),
            ("EIN", "erratum_in"),
            ("CIN", "comment_in"),
            ("CON", "comment_on"),
            ("CRF", "corrected_republished_from"),
            ("CRI", "corrected_republished_in"),
            ("RIN", "retraction_in"),
            ("ROF", "retraction_of"),
            ("RRF", "retracted_republished_from"),
            ("RRI", "retracted_republished_in"),
            ("RPF", "republished_from"),
            ("RPI", "republished_in"),
            ("ECF", "expression_concern_for"),
            ("ECI", "expression_concern_in"),
            ("UIN", "update_in"),
            ("UOF", "update_of"),
            ("ORI", "original_report_in"),
            ("SPIN", "summary_for_patients_in"),
            ("DDIN", "dataset_described_in"),
            ("DRIN", "dataset_use_reported_in"),
        ],
    )
    def test_every_cross_reference_tag_keeps_its_text_and_pmid(self, tag: str, attribute: str) -> None:
        references = getattr(parse(f"{tag} - J Med. 2022;1(1):1. PMID: 12345678"), attribute)
        assert references[0].citation_text == "J Med. 2022;1(1):1. PMID: 12345678"
        assert references[0].pmid == 12345678

    def test_a_cross_reference_without_a_pmid(self) -> None:
        assert parse("CIN - Comment in J Med. 2022").comment_in[0].pmid is None
