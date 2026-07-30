"""End-to-end tests: recorded MEDLINE text in, citation text out.

The snapshots here are the contract for rendered output. Review a snapshot diff
rather than re-recording to make a test pass — a changed citation is a change in
what this library promises.
"""

import pytest
import respx

from pmid_to_citation import (
    EFETCH_URL,
    CitationFormatter,
    CitationStyle,
    fetch_citation,
    fetch_record,
    parse_medline_file,
)
from tests.conftest import ALL_FIXTURES, MEDLINE_DIR, medline_text

TOOL = "pmid-to-citation-tests"
EMAIL = "tests@example.org"


@pytest.mark.parametrize("filename", ALL_FIXTURES)
def test_parse_and_format(filename: str, snapshot_json: object) -> None:
    """Every recorded record renders to exactly the same citation as before."""
    record = parse_medline_file(MEDLINE_DIR / filename)
    assert CitationFormatter().format_citation(record) == snapshot_json


class TestFacade:
    async def test_fetch_record_fetches_and_parses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NCBI_API_KEY", raising=False)
        with respx.mock() as router:
            router.get(EFETCH_URL).respond(200, text=medline_text("1.txt"))
            record = await fetch_record(1, tool=TOOL, email=EMAIL)

        assert record.pmid == 1
        assert record.title == "Formate assay in body fluids: application in methanol poisoning."

    async def test_fetch_citation_fetches_and_renders(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NCBI_API_KEY", raising=False)
        with respx.mock() as router:
            router.get(EFETCH_URL).respond(200, text=medline_text("1.txt"))
            citation = await fetch_citation(1, tool=TOOL, email=EMAIL)

        assert citation == (
            "Makar, A. B., McMartin, K. E., Palese, M. &amp; Tephly, T. R. Formate assay in body fluids: "
            "application in methanol poisoning. <i>Biochem Med</i> <b>13</b>, 117–26 (1975)."
        )

    async def test_fetch_citation_accepts_an_explicit_style(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NCBI_API_KEY", raising=False)
        with respx.mock() as router:
            router.get(EFETCH_URL).respond(200, text=medline_text("1.txt"))
            citation = await fetch_citation(1, tool=TOOL, email=EMAIL, style=CitationStyle.NATURE)

        assert "Makar" in citation

    async def test_an_api_key_reaches_the_request(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NCBI_API_KEY", raising=False)
        with respx.mock() as router:
            route = router.get(EFETCH_URL).respond(200, text=medline_text("1.txt"))
            await fetch_record(1, tool=TOOL, email=EMAIL, api_key="k")

        assert "api_key=k" in str(route.calls.last.request.url)
