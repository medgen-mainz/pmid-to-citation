"""Smoke tests for the packaging, the public surface, and the exception hierarchy.

These assert the invariants that the rest of the suite and the published wheel
depend on, so a broken installation fails here rather than deep in a parser.
"""

import re
from pathlib import Path

import pmid_to_citation
from pmid_to_citation import (
    CitationFormatError,
    EntrezError,
    PmidToCitationError,
    RecordNotFoundError,
    RecordParseError,
    UnknownStyleError,
)

ERRORS = [
    EntrezError,
    RecordNotFoundError,
    RecordParseError,
    CitationFormatError,
    UnknownStyleError,
]


def test_version_is_a_release_version() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", pmid_to_citation.__version__), pmid_to_citation.__version__


def test_py_typed_marker_is_installed() -> None:
    assert (Path(pmid_to_citation.__file__).parent / "py.typed").is_file()


def test_the_bundled_style_definitions_are_installed() -> None:
    # A wheel without these installs cleanly and then cannot format anything.
    styles = Path(pmid_to_citation.__file__).parent / "styles"
    assert {path.stem for path in styles.glob("*.csl")} == {style.value for style in pmid_to_citation.CitationStyle}


def test_all_names_are_importable() -> None:
    for name in pmid_to_citation.__all__:
        assert hasattr(pmid_to_citation, name), name


def test_all_is_free_of_duplicates() -> None:
    # Ruff's RUF022 already enforces the ordering, using its own convention.
    assert len(pmid_to_citation.__all__) == len(set(pmid_to_citation.__all__))


def test_no_csl_type_leaks_into_the_public_surface() -> None:
    # CSL is an implementation detail; keeping it out is what allows the
    # rendering back end to be replaced without an API break.
    assert not [name for name in pmid_to_citation.__all__ if name.startswith("Csl")]


def test_every_error_derives_from_the_base_error() -> None:
    for error in ERRORS:
        assert issubclass(error, PmidToCitationError)


def test_missing_record_is_an_entrez_failure() -> None:
    assert issubclass(RecordNotFoundError, EntrezError)


def test_an_unknown_style_is_a_formatting_failure() -> None:
    assert issubclass(UnknownStyleError, CitationFormatError)
