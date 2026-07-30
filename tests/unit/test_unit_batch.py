"""Tests for multi-record parsing and for batched fetching.

Every test here stubs HTTP with respx, and none of them sleeps: the clients are
built with a rate high enough that the limiter never has to wait. The limiter's
own waiting is tested directly, with an injected clock.
"""

# The rate limiter and the record splitter are module-private, but they are where
# the logic that needs pinning down lives.
# pyright: reportPrivateUsage=false

import math
from collections.abc import Awaitable, Callable, Iterator

import httpx
import pytest
import respx

from pmid_to_citation import (
    EFETCH_URL,
    EntrezClient,
    EntrezError,
    RecordParseError,
    parse_medline_records,
)
from pmid_to_citation.client import (
    API_KEY_ENV_VAR,
    DEFAULT_BATCH_SIZE,
    REQUESTS_PER_SECOND,
    REQUESTS_PER_SECOND_WITH_API_KEY,
    _RateLimiter,
)
from tests.conftest import medline_text, multi_record_text

TOOL = "pmid-to-citation-tests"
EMAIL = "tests@example.org"

# High enough that the limiter never sleeps, keeping the tests instant.
UNLIMITED = math.inf


def client(**kwargs: object) -> EntrezClient:
    """Build a client that never waits on its own rate limiter."""
    kwargs.setdefault("requests_per_second", UNLIMITED)
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


class TestParseMedlineRecords:
    def test_a_single_record_payload(self) -> None:
        records = parse_medline_records(medline_text("1.txt"))
        assert [record.pmid for record in records] == [1]

    def test_an_empty_payload_gives_no_records(self) -> None:
        # This is how Entrez reports that it knew none of the PMIDs.
        assert parse_medline_records("") == []
        assert parse_medline_records("\n  \n") == []

    def test_several_records_keep_their_order(self) -> None:
        payload = multi_record_text("1.txt", "35642643.txt", "37940764.txt")
        assert [record.pmid for record in parse_medline_records(payload)] == [1, 35642643, 37940764]

    def test_each_record_is_parsed_in_full(self) -> None:
        payload = multi_record_text("1.txt", "35642643.txt")
        first, second = parse_medline_records(payload)
        assert first.title == "Formate assay in body fluids: application in methanol poisoning."
        assert [author.last_name for author in first.authors] == ["Makar", "McMartin", "Palese", "Tephly"]
        assert second.title is not None and second.title != first.title
        assert second.authors

    def test_a_batched_record_matches_the_same_record_fetched_alone(self) -> None:
        alone = parse_medline_records(medline_text("26432245.txt"))[0]
        batched = {r.pmid: r for r in parse_medline_records(multi_record_text("1.txt", "26432245.txt"))}
        assert batched[26432245] == alone

    def test_records_need_no_blank_line_between_them(self) -> None:
        payload = "PMID- 1\nTI  - First.\nPMID- 2\nTI  - Second."
        assert [record.pmid for record in parse_medline_records(payload)] == [1, 2]

    def test_a_blank_line_inside_a_record_does_not_split_it(self) -> None:
        # Blank lines are why the splitter keys on the PMID tag, not on them.
        payload = "\nPMID- 1\nTI  - First.\n\nAB  - Still record one.\n\nPMID- 2\nTI  - Second.\n"
        records = parse_medline_records(payload)
        assert [record.pmid for record in records] == [1, 2]
        assert records[0].abstract == "Still record one."

    def test_an_indented_pmid_line_is_a_continuation_not_a_new_record(self) -> None:
        payload = "PMID- 1\nCIN - Comment in J Med.\n      PMID- 2 is unrelated\n"
        records = parse_medline_records(payload)
        assert [record.pmid for record in records] == [1]
        assert records[0].comment_in[0].citation_text == "Comment in J Med. PMID- 2 is unrelated"

    def test_content_before_the_first_record_reports_its_line(self) -> None:
        with pytest.raises(RecordParseError, match="line 2: content before the first record") as excinfo:
            parse_medline_records("\nstray text\nPMID- 1\n")
        assert excinfo.value.line_number == 2

    def test_a_record_that_cannot_be_parsed_still_raises(self) -> None:
        with pytest.raises(RecordParseError, match="invalid PMID"):
            parse_medline_records("PMID- not-a-number\nTI  - x")


class TestRateLimiter:
    def test_a_non_positive_rate_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="requests_per_second must be positive"):
            _RateLimiter(0)

    async def test_the_first_request_does_not_wait(self) -> None:
        slept: list[float] = []
        limiter = _RateLimiter(3, clock=lambda: 1000.0, sleep=_recorder(slept))

        await limiter.acquire()

        assert slept == []

    async def test_later_requests_wait_out_the_interval(self) -> None:
        slept: list[float] = []
        now = 1000.0
        limiter = _RateLimiter(4, clock=lambda: now, sleep=_recorder(slept))

        await limiter.acquire()
        await limiter.acquire()
        await limiter.acquire()

        # A clock that never advances means every request after the first waits a
        # full interval, and each wait is measured from the previous one.
        assert slept == [0.25, 0.5]

    async def test_a_request_after_a_long_gap_does_not_wait(self) -> None:
        slept: list[float] = []
        now = 1000.0
        limiter = _RateLimiter(4, clock=lambda: now, sleep=_recorder(slept))

        await limiter.acquire()
        now += 10.0
        await limiter.acquire()

        assert slept == []

    async def test_an_infinite_rate_never_waits(self) -> None:
        slept: list[float] = []
        limiter = _RateLimiter(math.inf, clock=lambda: 0.0, sleep=_recorder(slept))

        for _ in range(5):
            await limiter.acquire()

        assert slept == []


def _recorder(into: list[float]) -> Callable[[float], Awaitable[None]]:
    """Build a stand-in for ``asyncio.sleep`` that records what it was asked to wait."""

    async def sleep(delay: float) -> None:
        into.append(delay)

    return sleep


class TestRateDefaults:
    def test_without_an_api_key_the_unauthenticated_limit_applies(self) -> None:
        entrez = EntrezClient(tool=TOOL, email=EMAIL)
        assert entrez.requests_per_second == REQUESTS_PER_SECOND

    def test_with_an_api_key_the_higher_limit_applies(self) -> None:
        entrez = EntrezClient(tool=TOOL, email=EMAIL, api_key="k")
        assert entrez.requests_per_second == REQUESTS_PER_SECOND_WITH_API_KEY

    def test_an_api_key_from_the_environment_also_raises_the_limit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(API_KEY_ENV_VAR, "k")
        entrez = EntrezClient(tool=TOOL, email=EMAIL)
        assert entrez.requests_per_second == REQUESTS_PER_SECOND_WITH_API_KEY

    def test_the_rate_can_be_overridden(self) -> None:
        assert EntrezClient(tool=TOOL, email=EMAIL, requests_per_second=1).requests_per_second == 1

    def test_a_non_positive_rate_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="requests_per_second must be positive"):
            EntrezClient(tool=TOOL, email=EMAIL, requests_per_second=0)

    def test_a_non_positive_batch_size_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="batch_size must be at least 1"):
            EntrezClient(tool=TOOL, email=EMAIL, batch_size=0)

    def test_the_default_batch_size(self) -> None:
        assert EntrezClient(tool=TOOL, email=EMAIL).batch_size == DEFAULT_BATCH_SIZE


class TestGetRecords:
    async def test_no_pmids_makes_no_request(self, efetch: respx.Router) -> None:
        route = efetch.get(EFETCH_URL).respond(200, text="")

        async with client() as entrez:
            assert await entrez.get_records([]) == {}

        assert not route.called

    async def test_many_pmids_take_one_request(self, efetch: respx.Router) -> None:
        route = efetch.get(EFETCH_URL).respond(200, text=multi_record_text("1.txt", "35642643.txt", "37940764.txt"))

        async with client() as entrez:
            records = await entrez.get_records([1, 35642643, 37940764])

        assert route.call_count == 1
        assert sorted(records) == [1, 35642643, 37940764]
        assert records[1].title == "Formate assay in body fluids: application in methanol poisoning."

    async def test_all_the_pmids_go_into_one_id_parameter(self, efetch: respx.Router) -> None:
        route = efetch.get(EFETCH_URL).respond(200, text=multi_record_text("1.txt", "35642643.txt"))

        async with client() as entrez:
            await entrez.get_records([1, 35642643])

        assert "id=1%2C35642643" in str(route.calls.last.request.url)

    async def test_duplicates_are_requested_once(self, efetch: respx.Router) -> None:
        route = efetch.get(EFETCH_URL).respond(200, text=medline_text("1.txt"))

        async with client() as entrez:
            records = await entrez.get_records([1, 1, 1])

        assert route.call_count == 1
        assert "id=1&" in str(route.calls.last.request.url)
        assert sorted(records) == [1]

    @pytest.mark.parametrize(
        ("count", "batch_size", "expected_requests"),
        [(3, 1, 3), (3, 2, 2), (3, 3, 1), (3, 10, 1), (10, 4, 3)],
    )
    async def test_the_request_count_is_the_number_of_batches(
        self, efetch: respx.Router, count: int, batch_size: int, expected_requests: int
    ) -> None:
        route = efetch.get(EFETCH_URL).respond(200, text="")

        async with client(batch_size=batch_size) as entrez:
            await entrez.get_records(range(1, count + 1))

        assert route.call_count == expected_requests

    async def test_records_from_several_batches_are_merged(self, efetch: respx.Router) -> None:
        efetch.get(EFETCH_URL).side_effect = [
            httpx.Response(200, text=medline_text("1.txt")),
            httpx.Response(200, text=medline_text("35642643.txt")),
        ]

        async with client(batch_size=1) as entrez:
            records = await entrez.get_records([1, 35642643])

        assert sorted(records) == [1, 35642643]

    async def test_a_long_batch_is_sent_by_post(self, efetch: respx.Router) -> None:
        # NCBI asks for POST above about 200 identifiers, because a longer list
        # makes a URL that intermediaries may truncate.
        get_route = efetch.get(EFETCH_URL).respond(200, text="")
        post_route = efetch.post(EFETCH_URL).respond(200, text=medline_text("1.txt"))
        pmids = range(1, 202)

        async with client(batch_size=250) as entrez:
            records = await entrez.get_records(pmids)

        assert post_route.call_count == 1
        assert not get_route.called
        assert sorted(records) == [1]
        assert b"id=1%2C2%2C3" in post_route.calls.last.request.content

    async def test_a_batch_at_the_get_limit_still_uses_get(self, efetch: respx.Router) -> None:
        get_route = efetch.get(EFETCH_URL).respond(200, text="")
        post_route = efetch.post(EFETCH_URL).respond(200, text="")

        async with client(batch_size=200) as entrez:
            await entrez.get_records(range(1, 201))

        assert get_route.call_count == 1
        assert not post_route.called


class TestGetRecordsPartialResults:
    async def test_pmids_entrez_does_not_know_are_absent(self, efetch: respx.Router) -> None:
        # Entrez returns the records it has and says nothing about the rest.
        efetch.get(EFETCH_URL).respond(200, text=multi_record_text("1.txt", "35642643.txt"))
        wanted = [1, 404404, 35642643]

        async with client() as entrez:
            records = await entrez.get_records(wanted)

        assert sorted(records) == [1, 35642643]
        assert [pmid for pmid in wanted if pmid not in records] == [404404]

    async def test_a_batch_that_matches_nothing_is_not_an_error(self, efetch: respx.Router) -> None:
        # Unlike the single-PMID path, an empty body here is a miss, not a failure.
        efetch.get(EFETCH_URL).respond(200, text="")

        async with client() as entrez:
            assert await entrez.get_records([404404, 404405]) == {}

    async def test_one_empty_batch_does_not_lose_the_others(self, efetch: respx.Router) -> None:
        efetch.get(EFETCH_URL).side_effect = [
            httpx.Response(200, text=""),
            httpx.Response(200, text=medline_text("1.txt")),
        ]

        async with client(batch_size=1) as entrez:
            records = await entrez.get_records([404404, 1])

        assert sorted(records) == [1]

    async def test_an_http_error_in_any_batch_fails_the_call(self, efetch: respx.Router) -> None:
        efetch.get(EFETCH_URL).side_effect = [
            httpx.Response(200, text=medline_text("1.txt")),
            httpx.Response(500, text="failed"),
        ]

        async with client(batch_size=1) as entrez:
            with pytest.raises(EntrezError, match="HTTP 500 error fetching PMID") as excinfo:
                await entrez.get_records([1, 35642643])

        assert excinfo.value.status_code == 500

    async def test_a_multi_pmid_failure_names_the_batch_not_a_pmid(self, efetch: respx.Router) -> None:
        efetch.get(EFETCH_URL).respond(503, text="failed")

        async with client() as entrez:
            with pytest.raises(EntrezError, match="HTTP 503 error fetching 3 PMIDs") as excinfo:
                await entrez.get_records([1, 2, 3])

        # No single identifier can be blamed for a batch failure.
        assert excinfo.value.pmid is None

    async def test_a_transport_failure_names_the_batch(self, efetch: respx.Router) -> None:
        efetch.get(EFETCH_URL).mock(side_effect=httpx.ConnectError("refused"))

        async with client() as entrez:
            with pytest.raises(EntrezError, match="request error fetching 2 PMIDs"):
                await entrez.get_records([1, 2])

    async def test_using_the_client_unopened_is_an_error(self) -> None:
        with pytest.raises(EntrezError, match="use it as an async context manager") as excinfo:
            await client().get_records([1, 2])

        assert excinfo.value.pmid is None

    async def test_an_unparseable_payload_raises(self, efetch: respx.Router) -> None:
        efetch.get(EFETCH_URL).respond(200, text="This is not a MEDLINE record")

        async with client() as entrez:
            with pytest.raises(RecordParseError, match="content before the first record"):
                await entrez.get_records([1, 2])
