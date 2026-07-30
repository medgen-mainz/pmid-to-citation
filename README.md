[![PyPI - Version](https://img.shields.io/pypi/v/pmid-to-citation)](http://pypi.org/project/pmid-to-citation/)
[![PyPI - Types](https://img.shields.io/pypi/types/pmid-to-citation)](http://pypi.org/project/pmid-to-citation/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/pmid-to-citation)](http://pypi.org/project/pmid-to-citation/)
[![CI](https://github.com/medgen-mainz/pmid-to-citation/actions/workflows/main.yml/badge.svg)](https://github.com/medgen-mainz/pmid-to-citation/actions/workflows/main.yml)
[![docs](https://app.readthedocs.org/projects/pmid-to-citation/badge/?version=latest)](https://pmid-to-citation.readthedocs.io/en/latest/)

# pmid-to-citation

Fetch PubMed records from the NCBI Entrez API by PMID and render them as
citation/reference text.

- Python: 3.13+
- License: MIT
- [Documentation at ReadTheDocs](https://pmid-to-citation.readthedocs.io/en/latest/)

> **Status: pre-1.0.** The public API may change between minor releases.

## Installation

```bash
pip install pmid-to-citation
```

## Quick start

`tool` and `email` are required, and deliberately have no defaults: the
[Entrez usage guidelines][entrez-guidelines] require every request to identify
its caller, and a library must not answer that on its user's behalf.

```python
import asyncio
from pmid_to_citation import fetch_citation

citation = asyncio.run(fetch_citation(1, tool="my-app", email="me@example.org"))
# 'Makar, A. B., McMartin, K. E., Palese, M. &amp; Tephly, T. R. Formate assay in
#  body fluids: application in methanol poisoning. <i>Biochem Med</i>
#  <b>13</b>, 117–26 (1975).'
```

The rendered text is an **HTML fragment** — the Nature style italicises journal
names, emboldens volume numbers, and `&` arrives as `&amp;`. Treat it as markup,
not as plain text.

[entrez-guidelines]: https://www.ncbi.nlm.nih.gov/books/NBK25497/

## The three layers

Fetching and formatting are separate, and each layer is usable on its own.

**1. Client** — talks to Entrez over HTTP, and knows nothing about citations.
Reuse one client for several records rather than reconnecting per PMID:

```python
from pmid_to_citation import EntrezClient

async with EntrezClient(tool="my-app", email="me@example.org") as client:
    record = await client.get_record(31341288)
    raw = await client.get_record_text(31341288)  # unparsed MEDLINE text
```

An `NCBI_API_KEY` in the environment is picked up automatically; it raises the
rate limit from 3 to 10 requests per second.

### Many PMIDs at once

EFetch accepts many identifiers per call, so fetching a reference list costs a
handful of requests rather than one per PMID:

```python
from pmid_to_citation import fetch_citations

wanted = [1, 31341288, 35642643]
citations = await fetch_citations(wanted, tool="my-app", email="me@example.org")
```

`fetch_records` and `EntrezClient.get_records` do the same for records. All three
return a **mapping keyed by PMID**, and batch requests concurrently at the rate
the Entrez guidelines permit.

**PMIDs that Entrez does not know are absent from the result rather than raising.**
Entrez omits them silently, and one retracted or mistyped identifier should not
defeat a request for hundreds:

```python
records = await fetch_records(wanted, tool="my-app", email="me@example.org")
missing = [pmid for pmid in wanted if pmid not in records]
```

Identifiers are split into batches of `batch_size` (200 by default); raising it
switches those requests to POST, as NCBI asks for long lists. Duplicates are
requested once.

**2. Record models** — validated, normalised models of a PubMed record, with no
knowledge of HTTP or of output formats. Parse text you obtained anywhere:

```python
from pmid_to_citation import parse_medline, parse_medline_file

record = parse_medline(raw)
record = parse_medline_file("record.txt")
records = parse_medline_records(multi_record_text)  # a multi-PMID response

record.title       # 'Formate assay in body fluids: application in methanol poisoning.'
record.authors[0]  # Author(last_name='Makar', initials='AB', ...)
record.other_fields  # any MEDLINE tag this library does not model, kept verbatim
```

**3. Styles** — pure functions from a record to text, with no I/O. Compiling a
style is expensive, so reuse a formatter:

```python
from pmid_to_citation import CitationFormatter, CitationStyle

formatter = CitationFormatter(CitationStyle.NATURE)
formatter.format_citation(record)
formatter.format_citations([record, other_record])  # reuses the compiled style
```

Rendering goes through [citeproc-py][citeproc] and a Citation Style Language
definition, which is what will make further styles cheap to add. That is an
implementation detail: no CSL type appears in the public API.

[citeproc]: https://github.com/citeproc-py/citeproc-py

## Errors

Every failure raises a subclass of `PmidToCitationError`, so one `except` clause
catches anything this library reports:

| Exception              | Raised when                                             |
| ---------------------- | ------------------------------------------------------- |
| `EntrezError`          | Entrez is unreachable or reports an HTTP error           |
| `RecordNotFoundError`  | Entrez holds no record for the requested PMID            |
| `RecordParseError`     | A response cannot be interpreted as a MEDLINE record     |
| `CitationFormatError`  | A record cannot be rendered in the requested style       |
| `UnknownStyleError`    | No definition is installed for the requested style       |

`RecordNotFoundError` is an `EntrezError`; `UnknownStyleError` is a
`CitationFormatError`.

## Typing

The package ships `py.typed` and is checked with `pyright` in strict mode, so the
annotations are part of the published contract.

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for the
development setup, the commit message convention, and how releases are cut.

## Security

To report a vulnerability, see [SECURITY.md](SECURITY.md).
