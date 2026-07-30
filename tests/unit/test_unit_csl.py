"""Tests for the internal CSL models.

These are not public API; they exist so that the CSL rendering back end can be
replaced without an API break. What matters here is that they serialise to the
aliases the CSL specification defines, and that they reject malformed dates.
"""

import json

import pydantic
import pytest

from pmid_to_citation._csl import CslData, CslDateVariable, CslNameVariable, CslType


class TestCslData:
    def test_type_and_id_are_required(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="Field required"):
            CslData()  # type: ignore[call-arg]

    def test_an_unknown_type_is_rejected(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="Input should be"):
            CslData(type="invented-type", id="x")  # type: ignore[arg-type]

    def test_unknown_fields_are_rejected(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="Extra inputs are not permitted"):
            CslData(type=CslType.ARTICLE, id="x", invented_field="y")  # type: ignore[call-arg]

    def test_hyphenated_csl_names_are_accepted_on_input(self) -> None:
        data = CslData.model_validate(
            {
                "type": "article-journal",
                "id": "smith2023",
                "container-title": "Nature",
                "publisher-place": "New York",
                "chapter-number": "5",
            }
        )
        assert data.container_title == "Nature"
        assert data.publisher_place == "New York"
        assert data.chapter_number == "5"

    def test_python_names_are_accepted_on_input_too(self) -> None:
        data = CslData(type=CslType.ARTICLE_JOURNAL, id="x", container_title="Nature")
        assert data.container_title == "Nature"

    def test_serialising_by_alias_produces_the_csl_names(self) -> None:
        data = CslData(
            type=CslType.ARTICLE_JOURNAL,
            id="test-article",
            title="Test Article",
            author=[CslNameVariable(family="Smith", given="John")],
            container_title="Test Journal",
            volume=1,
            page="10-20",
            issued=CslDateVariable(date_parts=[[2023, 12, 25]]),
        )

        dumped = data.model_dump(by_alias=True, exclude_none=True)

        assert dumped["type"] == "article-journal"
        assert dumped["container-title"] == "Test Journal"
        assert dumped["issued"]["date-parts"] == [[2023, 12, 25]]
        # Nothing unset leaks into the payload citeproc receives.
        assert "issue" not in dumped
        # The result must survive a JSON round trip, since that is how citeproc
        # consumes it.
        assert json.loads(json.dumps(dumped))["container-title"] == "Test Journal"


class TestCslNameVariable:
    def test_particles_use_their_hyphenated_aliases(self) -> None:
        name = CslNameVariable.model_validate({"family": "Doe", "given": "Jane", "dropping-particle": "van"})
        assert name.dropping_particle == "van"

    def test_unknown_fields_are_rejected(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="Extra inputs are not permitted"):
            CslNameVariable(family="Smith", invented_attr="x")  # type: ignore[call-arg]


class TestCslDateVariable:
    @pytest.mark.parametrize(
        "date_parts",
        [
            [[2023]],
            [[2023, 3]],
            [[2023, 3, 15]],
            [[2023, 6, 1], [2023, 6, 5]],  # a range
        ],
    )
    def test_shapes_the_specification_allows(self, date_parts: list[list[int]]) -> None:
        assert CslDateVariable(date_parts=date_parts).date_parts == date_parts

    def test_no_date_parts_at_all_is_allowed(self) -> None:
        assert CslDateVariable(literal="circa 1450").date_parts is None

    def test_an_explicit_none_passes_validation(self) -> None:
        assert CslDateVariable(date_parts=None, raw="in press").date_parts is None

    @pytest.mark.parametrize("date_parts", [[], [[2023], [2023], [2023]]])
    def test_the_outer_sequence_must_be_one_date_or_a_range_of_two(self, date_parts: list[list[int]]) -> None:
        with pytest.raises(pydantic.ValidationError, match="date-parts must have 1-2 elements"):
            CslDateVariable(date_parts=date_parts)

    @pytest.mark.parametrize("date_parts", [[[]], [[2023, 3, 15, 12]]])
    def test_a_date_must_hold_one_to_three_parts(self, date_parts: list[list[int]]) -> None:
        with pytest.raises(pydantic.ValidationError, match="Each date-part must have 1-3 elements"):
            CslDateVariable(date_parts=date_parts)

    def test_a_season_and_a_circa_flag_are_kept(self) -> None:
        date = CslDateVariable(date_parts=[[2023]], season="Spring", circa=True)
        assert (date.season, date.circa) == ("Spring", True)
