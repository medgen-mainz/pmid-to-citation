"""Fixtures shared across the test suite."""

from pathlib import Path

import pytest
import syrupy
from syrupy.extensions.json import JSONSnapshotExtension

#: Real MEDLINE records, recorded byte-for-byte as Entrez returned them.
MEDLINE_DIR = Path(__file__).parent / "data" / "medline"

#: Every recorded fixture, for tests that should hold across all of them.
ALL_FIXTURES = [
    "1.txt",  # 1975 letter: the oldest record shape, no abstract
    "11181995.txt",  # GeneReviews chapter: a book, not an article
    "20301598.txt",  # GeneReviews chapter with many editors
    "26432245.txt",  # consortium paper with hundreds of investigators
    "32510551.txt",
    "34189567.txt",
    "35457587.txt",
    "35522339.txt",
    "35642643.txt",  # many authors, no MeSH terms
    "37940764.txt",
]


@pytest.fixture
def snapshot_json(snapshot: syrupy.assertion.SnapshotAssertion) -> syrupy.assertion.SnapshotAssertion:
    """A snapshot asserter that records JSON rather than Python reprs."""
    return snapshot.use_extension(JSONSnapshotExtension)


def medline_text(filename: str) -> str:
    """Read one recorded MEDLINE fixture.

    Args:
        filename: Basename of a file in ``tests/data/medline``.

    Returns:
        The file's contents.
    """
    return (MEDLINE_DIR / filename).read_text(encoding="utf-8")
