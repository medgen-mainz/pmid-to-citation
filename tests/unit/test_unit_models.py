"""Tests for the record models and the packed-string fields they normalise."""

import re
from datetime import datetime
from typing import cast

import pydantic
import pytest

from pmid_to_citation import (
    Author,
    Editor,
    Grant,
    Investigator,
    MeshTerm,
    Person,
    PersonalNameSubject,
    PublicationHistory,
    PublicationHistoryType,
    PubMedRecord,
    Substance,
)
from pmid_to_citation._dates import parse_pubmed_datetime

PEOPLE = [Person, Author, Editor, Investigator, PersonalNameSubject]

# Sphinx cross-reference roles, e.g. `:attr:`pmid`` or `:class:`PubMedRecord``.
SPHINX_ROLE = re.compile(r":[a-z]+:`")


class TestParsePubmedDatetime:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("2022/06/02 06:00", datetime(2022, 6, 2, 6, 0)),
            ("1975/06/01", datetime(1975, 6, 1)),
        ],
    )
    def test_recognised_layouts(self, value: str, expected: datetime) -> None:
        assert parse_pubmed_datetime(value) == expected

    @pytest.mark.parametrize("value", ["", "not a date", "2023/15/40", "2023/12/01 25:70"])
    def test_unrecognised_layouts_give_none(self, value: str) -> None:
        assert parse_pubmed_datetime(value) is None


class TestPersonShortForm:
    @pytest.mark.parametrize("cls", PEOPLE)
    def test_trailing_initials_are_split_off(self, cls: type[Person]) -> None:
        person = cls.from_short_form("Makar AB")
        assert (person.last_name, person.initials) == ("Makar", "AB")
        assert isinstance(person, cls)

    def test_multi_word_surname_is_kept_whole(self) -> None:
        person = Person.from_short_form("Martín Merinero H")
        assert (person.last_name, person.initials) == ("Martín Merinero", "H")

    def test_surrounding_whitespace_is_ignored(self) -> None:
        assert Person.from_short_form("  Makar AB  ").last_name == "Makar"

    @pytest.mark.parametrize("cls", PEOPLE)
    def test_trailing_token_that_is_not_initials_is_still_taken_as_initials(self, cls: type[Person]) -> None:
        # "ABC123" cannot be initials, but MEDLINE puts them last regardless.
        person = cls.from_short_form("Van der Berg ABC123")
        assert (person.last_name, person.initials) == ("Van der Berg", "ABC123")

    @pytest.mark.parametrize("cls", PEOPLE)
    def test_single_token_is_all_surname(self, cls: type[Person]) -> None:
        person = cls.from_short_form("Smith")
        assert (person.last_name, person.initials) == ("Smith", "")

    @pytest.mark.parametrize("cls", PEOPLE)
    def test_empty_value(self, cls: type[Person]) -> None:
        person = cls.from_short_form("")
        assert (person.last_name, person.initials) == ("", "")


class TestPersonFullForm:
    @pytest.mark.parametrize("cls", PEOPLE)
    def test_comma_separates_surname_from_given_names(self, cls: type[Person]) -> None:
        person = cls.from_full_form("Makar, A B")
        assert person.last_name == "Makar"
        assert person.initials == ""
        assert person.full_name == "Makar, A B"

    @pytest.mark.parametrize("cls", PEOPLE)
    def test_without_a_comma_the_whole_value_is_the_surname(self, cls: type[Person]) -> None:
        person = cls.from_full_form("John Smith")
        assert person.last_name == "John Smith"
        assert person.full_name == "John Smith"

    @pytest.mark.parametrize("cls", PEOPLE)
    def test_empty_value(self, cls: type[Person]) -> None:
        person = cls.from_full_form("")
        assert (person.last_name, person.initials, person.full_name) == ("", "", "")


class TestPersonSubclasses:
    def test_author_carries_an_affiliation_and_an_identifier(self) -> None:
        author = Author(last_name="Smith", initials="J", affiliation="Dept", identifier="0000-0001")
        assert (author.affiliation, author.identifier) == ("Dept", "0000-0001")

    @pytest.mark.parametrize("cls", [Editor, Investigator])
    def test_editors_and_investigators_carry_an_affiliation(self, cls: type[Editor] | type[Investigator]) -> None:
        assert cls(last_name="Smith", initials="J", affiliation="Dept").affiliation == "Dept"

    def test_a_name_as_subject_has_no_affiliation(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="Extra inputs are not permitted"):
            PersonalNameSubject(last_name="Einstein", initials="A", affiliation="Dept")  # type: ignore[call-arg]


class TestGrant:
    def test_full_value_is_split_into_id_agency_and_country(self) -> None:
        grant = Grant.from_string("F32 AG064886/AG/NIA NIH HHS/United States")
        assert (grant.grant_id, grant.agency, grant.country) == ("F32 AG064886", "AG", "United States")

    def test_value_without_separators_is_all_identifier(self) -> None:
        grant = Grant.from_string("Simple Grant ID")
        assert (grant.grant_id, grant.agency, grant.country) == ("Simple Grant ID", None, None)


class TestMeshTerm:
    def test_plain_descriptor(self) -> None:
        term = MeshTerm.from_string("Body Fluids")
        assert (term.descriptor, term.subheading, term.major_topic) == ("Body Fluids", None, False)

    def test_subheading_starred_as_major_topic(self) -> None:
        term = MeshTerm.from_string("Body Fluids/*analysis")
        assert (term.descriptor, term.subheading, term.major_topic) == ("Body Fluids", "analysis", True)

    def test_descriptor_starred_as_major_topic(self) -> None:
        term = MeshTerm.from_string("*Methanol")
        assert (term.descriptor, term.major_topic) == ("Methanol", True)

    def test_unstarred_subheading(self) -> None:
        term = MeshTerm.from_string("Humans/analysis")
        assert (term.subheading, term.major_topic) == ("analysis", False)

    def test_empty_subheading_is_dropped(self) -> None:
        assert MeshTerm.from_string("Humans/").subheading is None


class TestSubstance:
    def test_registry_number_and_name(self) -> None:
        substance = Substance.from_string("0 (Formates)")
        assert (substance.registry_number, substance.name) == ("0", "Formates")

    def test_bare_name_has_no_registry_number(self) -> None:
        substance = Substance.from_string("Simple Substance Name")
        assert (substance.registry_number, substance.name) == ("", "Simple Substance Name")


class TestPublicationHistory:
    def test_timestamp_with_time_of_day(self) -> None:
        entry = PublicationHistory.from_string("2022/06/01 06:03 [entrez]")
        assert entry.date == datetime(2022, 6, 1, 6, 3)
        assert entry.type is PublicationHistoryType.ENTREZ

    def test_timestamp_without_time_of_day(self) -> None:
        entry = PublicationHistory.from_string("2015/05/12 [received]")
        assert entry.date == datetime(2015, 5, 12)
        assert entry.type is PublicationHistoryType.RECEIVED

    @pytest.mark.parametrize(
        ("value", "match"),
        [
            ("not a valid format", "no bracketed type"),
            ("2022/06/01 06:03 [entrez", "no bracketed type"),
            ("2023/15/40 [pubmed]", "unparseable publication history date"),
            ("2023/12/01 25:70 [entrez]", "unparseable publication history date"),
        ],
    )
    def test_unparseable_values_raise_rather_than_inventing_a_date(self, value: str, match: str) -> None:
        # Falling back to "now" would put a fabricated timestamp into the record.
        with pytest.raises(ValueError, match=match):
            PublicationHistory.from_string(value)

    def test_unknown_type_raises(self) -> None:
        with pytest.raises(ValueError, match="not a valid PublicationHistoryType"):
            PublicationHistory.from_string("2022/06/01 [invented]")


class TestPubMedRecord:
    def test_only_the_pmid_is_required(self) -> None:
        record = PubMedRecord(pmid=1)
        assert record.pmid == 1
        assert record.title is None
        assert record.authors == []
        assert record.other_fields == {}

    def test_pmid_is_required(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="Field required"):
            PubMedRecord()  # type: ignore[call-arg]

    def test_unknown_fields_are_rejected(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="Extra inputs are not permitted"):
            PubMedRecord(pmid=1, invented_field="x")  # type: ignore[call-arg]

    def test_assignment_is_validated(self) -> None:
        record = PubMedRecord(pmid=1)
        with pytest.raises(pydantic.ValidationError):
            record.pmid = "not an integer"  # type: ignore[assignment]

    def test_whitespace_is_stripped(self) -> None:
        assert PubMedRecord(pmid=1, title="  padded  ").title == "padded"


class TestSchemaDescriptions:
    """Guards on the docstrings that reach consumers as schema descriptions.

    Every model docstring in this module is republished as a JSON Schema
    ``description``, so a service that uses one as a FastAPI ``response_model``
    puts it in its own OpenAPI document and its generated clients. These tests
    exist because an implementation note and two Sphinx roles once travelled that
    far and turned up in a downstream project's TypeScript.
    """

    @staticmethod
    def descriptions() -> dict[str, str]:
        """Collect every description in the record schema, keyed by its location."""
        found: dict[str, str] = {}

        def walk(node: object, path: str) -> None:
            if isinstance(node, dict):
                for key, value in cast("dict[str, object]", node).items():
                    if key == "description" and isinstance(value, str):
                        found[path] = value
                    walk(value, f"{path}.{key}")
            elif isinstance(node, list):
                for index, value in enumerate(cast("list[object]", node)):
                    walk(value, f"{path}[{index}]")

        walk(PubMedRecord.model_json_schema(), "$")
        return found

    def test_the_schema_actually_carries_descriptions(self) -> None:
        # Otherwise the checks below would pass vacuously.
        assert len(self.descriptions()) > 10

    def test_no_description_contains_sphinx_role_syntax(self) -> None:
        # `:attr:`pmid`` renders as documentation only in Sphinx. Everywhere else
        # — an OpenAPI document, a generated TypeScript client — it is noise.
        offenders = {path: text for path, text in self.descriptions().items() if SPHINX_ROLE.search(text)}
        assert not offenders, f"use plain prose or ``literals`` instead: {offenders}"

    def test_no_description_mentions_pydantic(self) -> None:
        # A note about how this library is built says nothing to somebody
        # consuming the data; such notes belong in comments.
        offenders = {path: text for path, text in self.descriptions().items() if "pydantic" in text.lower()}
        assert not offenders, f"move implementation notes into comments: {offenders}"
