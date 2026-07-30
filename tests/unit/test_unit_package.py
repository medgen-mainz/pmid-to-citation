"""Smoke tests for the packaging and the exception hierarchy.

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
    __version__,
)


def test_version_is_a_release_version() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__), __version__


def test_py_typed_marker_is_installed() -> None:
    assert (Path(pmid_to_citation.__file__).parent / "py.typed").is_file()


def test_all_names_are_importable() -> None:
    for name in pmid_to_citation.__all__:
        assert hasattr(pmid_to_citation, name), name


def test_every_error_derives_from_the_base_error() -> None:
    for error in (EntrezError, RecordNotFoundError, RecordParseError, CitationFormatError):
        assert issubclass(error, PmidToCitationError)


def test_missing_record_is_an_entrez_failure() -> None:
    assert issubclass(RecordNotFoundError, EntrezError)
