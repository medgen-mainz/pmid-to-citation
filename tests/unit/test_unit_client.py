"""Tests for the Entrez client.

Every test here stubs HTTP with respx. Nothing in this file reaches NCBI: the
suite must not depend on a third-party service, nor spend the project's Entrez
rate budget on every push.
"""

from collections.abc import Iterator
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

from pmid_to_citation import (
    EFETCH_URL,
    EntrezClient,
    EntrezError,
    PubMedRecord,
    RecordNotFoundError,
    RecordParseError,
)
from pmid_to_citation.client import API_KEY_ENV_VAR
from tests.conftest import medline_text

TOOL = "pmid-to-citation-tests"
EMAIL = "tests@example.org"


def client(**kwargs: object) -> EntrezClient:
    """Build a client with the identification the Entrez guidelines require."""
    return EntrezClient(tool=TOOL, email=EMAIL, **kwargs)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def no_ambient_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep a developer's own NCBI_API_KEY out of the tests."""
    monkeypatch.delenv(API_KEY_ENV_VAR, raising=False)


@pytest.fixture
def efetch() -> Iterator[respx.Router]:
    """A respx router intercepting EFetch calls."""
    with respx.mock(assert_all_called=False) as router:
        yield router


def sent_params(route: respx.Route) -> dict[str, list[str]]:
    """Return the query parameters of the last request on a route."""
    return parse_qs(urlparse(str(route.calls.last.request.url)).query)


class TestGetRecord:
    async def test_a_record_is_fetched_and_parsed(self, efetch: respx.Router) -> None:
        efetch.get(EFETCH_URL).respond(200, text=medline_text("1.txt"))

        async with client() as entrez:
            record = await entrez.get_record(1)

        assert isinstance(record, PubMedRecord)
        assert record.pmid == 1
        assert record.title == "Formate assay in body fluids: application in methanol poisoning."
        assert [author.last_name for author in record.authors] == ["Makar", "McMartin", "Palese", "Tephly"]

    async def test_raw_text_is_returned_stripped(self, efetch: respx.Router) -> None:
        body = medline_text("26432245.txt")
        efetch.get(EFETCH_URL).respond(200, text=body)

        async with client() as entrez:
            assert await entrez.get_record_text(26432245) == body.strip()

    async def test_one_client_serves_several_requests(self, efetch: respx.Router) -> None:
        efetch.get(EFETCH_URL).side_effect = [
            httpx.Response(200, text=medline_text("1.txt")),
            httpx.Response(200, text=medline_text("26432245.txt")),
        ]

        async with client() as entrez:
            first = await entrez.get_record(1)
            second = await entrez.get_record(26432245)

        assert (first.pmid, second.pmid) == (1, 26432245)
        assert first.title != second.title

    @pytest.mark.parametrize("filename", ["1.txt", "11181995.txt", "26432245.txt", "35642643.txt", "37940764.txt"])
    async def test_every_recorded_response_round_trips(self, efetch: respx.Router, filename: str) -> None:
        efetch.get(EFETCH_URL).respond(200, text=medline_text(filename))

        async with client() as entrez:
            record = await entrez.get_record(int(filename.removesuffix(".txt")))

        assert record.title is not None
        assert record.authors


class TestRequestParameters:
    async def test_the_caller_is_identified_as_entrez_requires(self, efetch: respx.Router) -> None:
        route = efetch.get(EFETCH_URL).respond(200, text=medline_text("1.txt"))

        async with client() as entrez:
            await entrez.get_record_text(1)

        params = sent_params(route)
        assert params["tool"] == [TOOL]
        assert params["email"] == [EMAIL]
        assert params["db"] == ["pubmed"]
        assert params["id"] == ["1"]
        assert params["rettype"] == ["medline"]
        assert params["retmode"] == ["text"]

    async def test_an_explicit_api_key_is_sent(self, efetch: respx.Router) -> None:
        route = efetch.get(EFETCH_URL).respond(200, text=medline_text("1.txt"))

        async with client(api_key="test-key-123") as entrez:
            await entrez.get_record_text(1)

        assert sent_params(route)["api_key"] == ["test-key-123"]

    async def test_the_api_key_falls_back_to_the_environment(
        self, efetch: respx.Router, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(API_KEY_ENV_VAR, "key-from-env")
        route = efetch.get(EFETCH_URL).respond(200, text=medline_text("1.txt"))

        async with client() as entrez:
            await entrez.get_record_text(1)

        assert sent_params(route)["api_key"] == ["key-from-env"]

    async def test_an_empty_api_key_suppresses_the_environment_lookup(
        self, efetch: respx.Router, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(API_KEY_ENV_VAR, "key-from-env")
        route = efetch.get(EFETCH_URL).respond(200, text=medline_text("1.txt"))

        async with client(api_key="") as entrez:
            await entrez.get_record_text(1)

        assert "api_key" not in sent_params(route)

    async def test_no_api_key_is_sent_when_there_is_none(self, efetch: respx.Router) -> None:
        route = efetch.get(EFETCH_URL).respond(200, text=medline_text("1.txt"))

        async with client() as entrez:
            await entrez.get_record_text(1)

        assert "api_key" not in sent_params(route)

    async def test_the_endpoint_can_be_overridden(self, efetch: respx.Router) -> None:
        stand_in = "https://entrez.example.test/efetch.fcgi"
        route = efetch.get(stand_in).respond(200, text=medline_text("1.txt"))

        async with client(base_url=stand_in) as entrez:
            await entrez.get_record_text(1)

        assert route.called


class TestFailures:
    @pytest.mark.parametrize("status", [400, 404, 429, 500, 503])
    async def test_an_http_error_reports_the_status_and_the_pmid(self, efetch: respx.Router, status: int) -> None:
        efetch.get(EFETCH_URL).respond(status, text="failed")

        async with client() as entrez:
            with pytest.raises(EntrezError, match=f"HTTP {status} error") as excinfo:
                await entrez.get_record_text(999999)

        assert excinfo.value.pmid == 999999
        assert excinfo.value.status_code == status

    async def test_a_transport_failure_is_wrapped(self, efetch: respx.Router) -> None:
        efetch.get(EFETCH_URL).mock(side_effect=httpx.ConnectError("connection refused"))

        async with client() as entrez:
            with pytest.raises(EntrezError, match="request error fetching PMID 1") as excinfo:
                await entrez.get_record_text(1)

        assert excinfo.value.pmid == 1
        assert excinfo.value.status_code is None

    @pytest.mark.parametrize("body", ["", "   \n  "])
    async def test_an_empty_body_means_the_pmid_is_unknown(self, efetch: respx.Router, body: str) -> None:
        # Entrez answers an unknown PMID with an empty body, not an HTTP error.
        efetch.get(EFETCH_URL).respond(200, text=body)

        async with client() as entrez:
            with pytest.raises(RecordNotFoundError, match="no record for PMID 404404") as excinfo:
                await entrez.get_record_text(404404)

        assert excinfo.value.pmid == 404404

    async def test_a_record_not_found_error_is_also_an_entrez_error(self, efetch: respx.Router) -> None:
        efetch.get(EFETCH_URL).respond(200, text="")

        async with client() as entrez:
            with pytest.raises(EntrezError):
                await entrez.get_record(1)

    async def test_a_body_that_is_not_medline_raises_a_parse_error(self, efetch: respx.Router) -> None:
        efetch.get(EFETCH_URL).respond(200, text="This is not a MEDLINE record")

        async with client() as entrez:
            with pytest.raises(RecordParseError, match="malformed line"):
                await entrez.get_record(1)

    async def test_using_the_client_unopened_is_an_error(self) -> None:
        with pytest.raises(EntrezError, match="use it as an async context manager") as excinfo:
            await client().get_record_text(1)

        assert excinfo.value.pmid == 1


class TestLifecycle:
    async def test_the_client_closes_the_pool_it_opened(self) -> None:
        entrez = client()
        async with entrez as opened:
            assert opened is entrez
            assert entrez.is_open
        assert not entrez.is_open

    async def test_an_injected_client_is_left_open_for_its_owner(self, efetch: respx.Router) -> None:
        efetch.get(EFETCH_URL).respond(200, text=medline_text("1.txt"))
        http_client = httpx.AsyncClient()

        async with client(http_client=http_client) as entrez:
            await entrez.get_record_text(1)

        assert not http_client.is_closed
        await http_client.aclose()

    async def test_an_injected_client_works_without_the_context_manager(self, efetch: respx.Router) -> None:
        efetch.get(EFETCH_URL).respond(200, text=medline_text("1.txt"))

        async with httpx.AsyncClient() as http_client:
            entrez = client(http_client=http_client)
            assert (await entrez.get_record(1)).pmid == 1

    async def test_an_exception_in_the_body_still_closes_the_pool(self) -> None:
        entrez = client()
        with pytest.raises(RuntimeError, match="boom"):
            async with entrez:
                raise RuntimeError("boom")
        assert not entrez.is_open
