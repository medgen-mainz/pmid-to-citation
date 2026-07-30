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

from pmid_to_citation import (
    CitationFormatter,
    EntrezClient,
    RecordNotFoundError,
    parse_medline_records,
)
from tests.conftest import multi_record_text

pytestmark = pytest.mark.network

TOOL = "pmid-to-citation-tests"

# Well past the highest assigned PMID, so it should stay unassigned for a while.
UNASSIGNED_PMID = 999999999

# Three of the recorded fixtures, to check batching against the real endpoint.
BATCH_PMIDS = [1, 35642643, 37940764]


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


async def test_a_batch_request_returns_every_record(contact_email: str) -> None:
    """Confirms EFetch really does answer several PMIDs in one call."""
    async with EntrezClient(tool=TOOL, email=contact_email) as client:
        records = await client.get_records(BATCH_PMIDS)

    assert sorted(records) == sorted(BATCH_PMIDS)


async def test_a_real_multi_record_payload_splits_the_way_the_fixtures_assume(contact_email: str) -> None:
    """Validates the assembled multi-record fixture against the real thing.

    ``tests.conftest.multi_record_text`` builds a multi-record payload by
    concatenating recorded single-record responses. That is an assumption about a
    layout only Entrez can confirm, so this is where it gets checked: the real
    payload must split into the same records, with the same line structure, as the
    assembled one.
    """
    async with EntrezClient(tool=TOOL, email=contact_email) as client:
        # Deliberately not `get_records`: this needs the raw payload.
        live = await client._fetch_text(BATCH_PMIDS)  # pyright: ignore[reportPrivateUsage]

    assembled = multi_record_text(*(f"{pmid}.txt" for pmid in BATCH_PMIDS))

    live_records = parse_medline_records(live)
    assembled_records = parse_medline_records(assembled)

    assert [record.pmid for record in live_records] == BATCH_PMIDS
    assert [record.pmid for record in assembled_records] == BATCH_PMIDS
    # Same number of records, and each the same size, means the separator
    # convention the assembled fixture assumes is the one Entrez uses.
    assert [len(text.splitlines()) for text in live.split("\nPMID- ")] == [
        len(text.splitlines()) for text in assembled.strip().split("\nPMID- ")
    ]


async def test_a_batch_with_a_missing_pmid_returns_the_rest(contact_email: str) -> None:
    """Confirms Entrez really does omit unknown PMIDs rather than failing."""
    async with EntrezClient(tool=TOOL, email=contact_email) as client:
        records = await client.get_records([1, UNASSIGNED_PMID])

    assert sorted(records) == [1]
