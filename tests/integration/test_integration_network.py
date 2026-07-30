"""Tests that call the live NCBI Entrez API.

Every test here is marked ``network`` and is therefore deselected by default —
see ``addopts`` in ``pyproject.toml``. CI never runs them: the suite must not
depend on a third-party service being up, and must not spend the project's Entrez
rate budget on every push.

Run them deliberately with ``make test-network``. They need ``NCBI_EMAIL`` set,
because the Entrez guidelines require a real contact address and this project
will not send a made-up one.
"""

import os

import pytest

from pmid_to_citation import CitationFormatter, EntrezClient, RecordNotFoundError

pytestmark = pytest.mark.network

TOOL = "pmid-to-citation-tests"

# Well past the highest assigned PMID, so it should stay unassigned for a while.
UNASSIGNED_PMID = 999999999


@pytest.fixture
def contact_email() -> str:
    """The address to identify these requests with, or skip."""
    email = os.environ.get("NCBI_EMAIL")
    if not email:
        pytest.skip("set NCBI_EMAIL to run the tests that call NCBI")
    return email


async def test_a_known_record_is_fetched_and_parsed(contact_email: str) -> None:
    """The client works against the real endpoint, not just against respx."""
    async with EntrezClient(tool=TOOL, email=contact_email) as client:
        record = await client.get_record(1)

    assert record.pmid == 1
    assert record.title == "Formate assay in body fluids: application in methanol poisoning."
    assert [author.last_name for author in record.authors] == ["Makar", "McMartin", "Palese", "Tephly"]


async def test_a_live_record_renders(contact_email: str) -> None:
    async with EntrezClient(tool=TOOL, email=contact_email) as client:
        record = await client.get_record(1)

    assert "Makar" in CitationFormatter().format_citation(record)


async def test_an_unassigned_pmid_is_reported_as_missing(contact_email: str) -> None:
    """Confirms the empty-body convention this library relies on still holds."""
    async with EntrezClient(tool=TOOL, email=contact_email) as client:
        with pytest.raises(RecordNotFoundError):
            await client.get_record(UNASSIGNED_PMID)
