"""Asynchronous client for the NCBI Entrez EFetch endpoint.

This layer knows about HTTP and about Entrez. It knows nothing about citations:
it returns raw MEDLINE text, or a record parsed from it.
"""

import asyncio
import os
from collections.abc import Awaitable, Callable, Iterable, Sequence
from types import TracebackType
from typing import Self

import httpx

from pmid_to_citation.exceptions import EntrezError, RecordNotFoundError
from pmid_to_citation.models import PubMedRecord
from pmid_to_citation.parser import parse_medline, parse_medline_records

__all__ = ["EFETCH_URL", "EntrezClient"]

EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

#: Environment variable consulted when no ``api_key`` is passed explicitly.
API_KEY_ENV_VAR = "NCBI_API_KEY"

#: PMIDs per request. EFetch accepts many identifiers in one call, and issuing one
#: request per PMID would spend the caller's rate budget for nothing.
DEFAULT_BATCH_SIZE = 200

#: Requests per second the Entrez guidelines permit without an API key.
REQUESTS_PER_SECOND = 3

#: Requests per second permitted with an API key.
REQUESTS_PER_SECOND_WITH_API_KEY = 10

# NCBI asks that identifier lists longer than about 200 be sent by POST, because a
# longer list makes for a URL that intermediaries may truncate.
_GET_ID_LIMIT = 200

_DEFAULT_TIMEOUT = 30.0


def _loop_time() -> float:
    """Return the running loop's monotonic clock."""
    return asyncio.get_running_loop().time()


class _RateLimiter:
    """Spaces out request starts so a burst cannot exceed a rate.

    Entrez blocks the caller's IP for ignoring its limits, so this bounds the rate
    at which requests *start* rather than how many are in flight: with a slow
    endpoint, waiting for each response in turn would come in well under the limit
    and be needlessly slow.

    Args:
        requests_per_second: The rate to hold to. ``math.inf`` disables spacing.
        clock: Monotonic time source, for tests.
        sleep: Coroutine used to wait, for tests.
    """

    def __init__(
        self,
        requests_per_second: float,
        *,
        clock: Callable[[], float] = _loop_time,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if requests_per_second <= 0:
            raise ValueError(f"requests_per_second must be positive, got {requests_per_second!r}")
        self._min_interval = 1.0 / requests_per_second
        self._clock = clock
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._next_start = float("-inf")

    async def acquire(self) -> None:
        """Wait until another request may start."""
        async with self._lock:
            now = self._clock()
            delay = self._next_start - now
            if delay > 0:
                await self._sleep(delay)
                now += delay
            self._next_start = now + self._min_interval


class EntrezClient:
    """Fetches PubMed records from Entrez.

    The client must be used as an async context manager, which owns the
    underlying connection pool::

        async with EntrezClient(tool="my-app", email="me@example.org") as client:
            record = await client.get_record(31341288)

    ``tool`` and ``email`` have no defaults on purpose. The `Entrez usage
    guidelines <https://www.ncbi.nlm.nih.gov/books/NBK25497/>`_ require every
    request to identify the caller, and a library cannot answer that question on
    its user's behalf — sending someone else's identity is worse than sending
    none.

    Args:
        tool: Short name of the application making the request.
        email: Address NCBI can use to reach whoever runs it.
        api_key: An NCBI API key, which raises the rate limit from 3 to 10
            requests per second. Defaults to the ``NCBI_API_KEY`` environment
            variable when that is set; pass ``""`` to suppress that lookup.
        timeout: Per-request timeout in seconds. Ignored when ``http_client`` is
            given, since that client carries its own.
        http_client: An existing client to send requests through, rather than
            creating one. Its lifetime stays the caller's responsibility.
        base_url: The EFetch endpoint. Exposed for testing against a stand-in.
        batch_size: PMIDs per request in :meth:`get_records`. Raising it above
            200 switches those requests to POST, as NCBI asks.
        requests_per_second: The rate to hold requests to. Defaults to what the
            Entrez guidelines permit — 10 with an API key, 3 without.

    Raises:
        ValueError: If ``batch_size`` or ``requests_per_second`` is not positive.
    """

    def __init__(
        self,
        *,
        tool: str,
        email: str,
        api_key: str | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
        http_client: httpx.AsyncClient | None = None,
        base_url: str = EFETCH_URL,
        batch_size: int = DEFAULT_BATCH_SIZE,
        requests_per_second: float | None = None,
    ) -> None:
        if batch_size < 1:
            raise ValueError(f"batch_size must be at least 1, got {batch_size!r}")

        self.tool = tool
        self.email = email
        self.api_key = os.environ.get(API_KEY_ENV_VAR) if api_key is None else api_key
        self.timeout = timeout
        self.base_url = base_url
        self.batch_size = batch_size
        if requests_per_second is None:
            requests_per_second = REQUESTS_PER_SECOND_WITH_API_KEY if self.api_key else REQUESTS_PER_SECOND
        self.requests_per_second = requests_per_second
        self._limiter = _RateLimiter(requests_per_second)
        self._http_client = http_client
        self._owns_client = http_client is None

    @property
    def is_open(self) -> bool:
        """Whether the client currently has a connection pool to send through."""
        return self._http_client is not None

    async def __aenter__(self) -> Self:
        """Open the connection pool, unless one was supplied.

        Returns:
            This client.
        """
        if self._owns_client:
            self._http_client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the connection pool, if this client opened it.

        Args:
            exc_type: Type of any exception raised in the ``async with`` body.
            exc: The exception raised, if any.
            traceback: Its traceback, if any.
        """
        if self._owns_client and self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    def _query(self, pmids: Sequence[int]) -> dict[str, str]:
        """Build the EFetch parameters for one request.

        Args:
            pmids: The PubMed identifiers to request together.

        Returns:
            The parameters, including the caller identification that the Entrez
            guidelines require.
        """
        params = {
            "db": "pubmed",
            "id": ",".join(str(pmid) for pmid in pmids),
            "rettype": "medline",
            "retmode": "text",
            "tool": self.tool,
            "email": self.email,
        }
        if self.api_key:
            params["api_key"] = self.api_key
        return params

    async def _fetch_text(self, pmids: Sequence[int]) -> str:
        """Make one EFetch request.

        Args:
            pmids: The PubMed identifiers to request together.

        Returns:
            The response body, stripped of surrounding whitespace. This is empty
            when Entrez knew none of ``pmids``; that is not an error here, because
            in a batch some hits and some misses is the normal case.

        Raises:
            EntrezError: If the client is not open, or Entrez returns an HTTP
                error, or the request fails at the transport level.
        """
        # Only a single-PMID request can attribute a failure to one identifier.
        subject = pmids[0] if len(pmids) == 1 else None
        described = f"PMID {subject}" if subject is not None else f"{len(pmids)} PMIDs"

        if self._http_client is None:
            raise EntrezError("client is not open; use it as an async context manager", pmid=subject)

        params = self._query(pmids)
        await self._limiter.acquire()
        try:
            if len(pmids) > _GET_ID_LIMIT:
                response = await self._http_client.post(self.base_url, data=params)
            else:
                response = await self._http_client.get(self.base_url, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as err:
            raise EntrezError(
                f"HTTP {err.response.status_code} error fetching {described}: {err}",
                pmid=subject,
                status_code=err.response.status_code,
            ) from err
        except httpx.RequestError as err:
            raise EntrezError(f"request error fetching {described}: {err}", pmid=subject) from err

        return response.text.strip()

    async def get_record_text(self, pmid: int) -> str:
        """Fetch the raw MEDLINE text for one PMID.

        Args:
            pmid: The PubMed identifier to request.

        Returns:
            The response body, stripped of surrounding whitespace.

        Raises:
            EntrezError: If the client is not open, or Entrez returns an HTTP
                error, or the request fails at the transport level.
            RecordNotFoundError: If Entrez answers with an empty body, which is
                how it reports a PMID it does not know.
        """
        content = await self._fetch_text([pmid])
        if not content:
            raise RecordNotFoundError(f"Entrez has no record for PMID {pmid}", pmid=pmid)
        return content

    async def get_record(self, pmid: int) -> PubMedRecord:
        """Fetch and parse the record for one PMID.

        Args:
            pmid: The PubMed identifier to request.

        Returns:
            The parsed record.

        Raises:
            EntrezError: As for :meth:`get_record_text`.
            RecordNotFoundError: As for :meth:`get_record_text`.
            RecordParseError: If the response is not a MEDLINE record.
        """
        return parse_medline(await self.get_record_text(pmid))

    async def get_records(self, pmids: Iterable[int]) -> dict[int, PubMedRecord]:
        """Fetch and parse records for many PMIDs, several per request.

        Duplicates are requested once. The PMIDs are split into batches of
        :attr:`batch_size`, so this makes ``ceil(len(pmids) / batch_size)``
        requests rather than one per PMID. Batches are fetched concurrently, at
        the rate the Entrez guidelines permit.

        Args:
            pmids: The PubMed identifiers to fetch, in any iterable.

        Returns:
            The records, keyed by the PMID of the record itself, in the order the
            batches came back.

            **PMIDs that Entrez does not know are absent from the result** rather
            than raising: Entrez omits them silently, and one retracted or
            mistyped identifier should not defeat a request for hundreds. Compare
            against what you asked for to find them::

                records = await client.get_records(wanted)
                missing = [pmid for pmid in wanted if pmid not in records]

        Raises:
            EntrezError: If the client is not open, or Entrez returns an HTTP
                error, or a request fails at the transport level. One failing
                batch fails the whole call.
            RecordParseError: If a response is not made of MEDLINE records.
        """
        # `dict.fromkeys` removes duplicates and keeps the caller's order.
        wanted = list(dict.fromkeys(pmids))
        if not wanted:
            return {}

        batches = [wanted[start : start + self.batch_size] for start in range(0, len(wanted), self.batch_size)]
        payloads = await asyncio.gather(*(self._fetch_text(batch) for batch in batches))

        # Keyed by the PMID in the record rather than by request order, because
        # Entrez guarantees neither the order nor that every PMID comes back.
        return {record.pmid: record for payload in payloads for record in parse_medline_records(payload)}
