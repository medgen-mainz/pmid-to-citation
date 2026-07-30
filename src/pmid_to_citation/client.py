"""Asynchronous client for the NCBI Entrez EFetch endpoint.

This layer knows about HTTP and about Entrez. It knows nothing about citations:
it returns raw MEDLINE text, or a record parsed from it.
"""

import os
from types import TracebackType
from typing import Self

import httpx

from pmid_to_citation.exceptions import EntrezError, RecordNotFoundError
from pmid_to_citation.models import PubMedRecord
from pmid_to_citation.parser import parse_medline

__all__ = ["EFETCH_URL", "EntrezClient"]

EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

#: Environment variable consulted when no ``api_key`` is passed explicitly.
API_KEY_ENV_VAR = "NCBI_API_KEY"

_DEFAULT_TIMEOUT = 30.0


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
    ) -> None:
        self.tool = tool
        self.email = email
        self.api_key = os.environ.get(API_KEY_ENV_VAR) if api_key is None else api_key
        self.timeout = timeout
        self.base_url = base_url
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

    def _query(self, pmid: int) -> dict[str, str]:
        """Build the EFetch query string parameters for one PMID.

        Args:
            pmid: The PubMed identifier to request.

        Returns:
            The query parameters, including the caller identification that the
            Entrez guidelines require.
        """
        params = {
            "db": "pubmed",
            "id": str(pmid),
            "rettype": "medline",
            "retmode": "text",
            "tool": self.tool,
            "email": self.email,
        }
        if self.api_key:
            params["api_key"] = self.api_key
        return params

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
        if self._http_client is None:
            raise EntrezError("client is not open; use it as an async context manager", pmid=pmid)

        try:
            response = await self._http_client.get(self.base_url, params=self._query(pmid))
            response.raise_for_status()
        except httpx.HTTPStatusError as err:
            raise EntrezError(
                f"HTTP {err.response.status_code} error fetching PMID {pmid}: {err}",
                pmid=pmid,
                status_code=err.response.status_code,
            ) from err
        except httpx.RequestError as err:
            raise EntrezError(f"request error fetching PMID {pmid}: {err}", pmid=pmid) from err

        content = response.text.strip()
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
