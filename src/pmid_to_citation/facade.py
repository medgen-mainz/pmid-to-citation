"""One-call entry points for the common cases.

These compose the three layers — client, models, styles — for callers who want
the whole job done. Each layer remains usable on its own: parse a record you
obtained elsewhere with :func:`~pmid_to_citation.parser.parse_medline`, or render
one with :class:`~pmid_to_citation.formatter.CitationFormatter`.
"""

from pmid_to_citation.client import EntrezClient
from pmid_to_citation.formatter import CitationFormatter, CitationStyle
from pmid_to_citation.models import PubMedRecord

__all__ = ["fetch_citation", "fetch_record"]


async def fetch_record(pmid: int, *, tool: str, email: str, api_key: str | None = None) -> PubMedRecord:
    """Fetch and parse one record from Entrez.

    Opens a connection for this one request. To fetch several records, construct
    an :class:`~pmid_to_citation.client.EntrezClient` and reuse it.

    Args:
        pmid: The PubMed identifier to fetch.
        tool: Short name of the application making the request.
        email: Address NCBI can use to reach whoever runs it.
        api_key: An NCBI API key. Defaults to the ``NCBI_API_KEY`` environment
            variable when that is set.

    Returns:
        The parsed record.

    Raises:
        EntrezError: If Entrez cannot be reached or reports a failure.
        RecordNotFoundError: If Entrez holds no record for ``pmid``.
        RecordParseError: If the response is not a MEDLINE record.
    """
    async with EntrezClient(tool=tool, email=email, api_key=api_key) as client:
        return await client.get_record(pmid)


async def fetch_citation(
    pmid: int,
    *,
    tool: str,
    email: str,
    api_key: str | None = None,
    style: CitationStyle = CitationStyle.NATURE,
) -> str:
    """Fetch one record and render it as a citation.

    Args:
        pmid: The PubMed identifier to fetch.
        tool: Short name of the application making the request.
        email: Address NCBI can use to reach whoever runs it.
        api_key: An NCBI API key. Defaults to the ``NCBI_API_KEY`` environment
            variable when that is set.
        style: The citation style to render in.

    Returns:
        The citation as an HTML fragment. See
        :class:`~pmid_to_citation.formatter.CitationFormatter` on the markup.

    Raises:
        EntrezError: If Entrez cannot be reached or reports a failure.
        RecordNotFoundError: If Entrez holds no record for ``pmid``.
        RecordParseError: If the response is not a MEDLINE record.
        UnknownStyleError: If no definition is installed for ``style``.
    """
    record = await fetch_record(pmid, tool=tool, email=email, api_key=api_key)
    return CitationFormatter(style).format_citation(record)
