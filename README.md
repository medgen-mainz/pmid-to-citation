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

> **Status: early development.** This commit bootstraps the repository —
> packaging, typing, linting, tests, docs, and the release pipeline. The Entrez
> client and the Nature-style formatter land in follow-up releases, so there is
> no usable API yet. Until 1.0.0 the public API may change between minor
> releases.

## Design

**Fetching and formatting are separate.** Three layers, each usable on its own:

1. **Client** — talks to Entrez over HTTP. Handles retries and rate limits, and
   knows nothing about citations.
2. **Record models** — validated, normalised models of a PubMed record. No
   knowledge of HTTP or of output formats.
3. **Styles** — pure functions turning a record into reference text. Nature style
   is the first target; the design does not assume it is the only one.

So you can format a record you obtained elsewhere, and fetch a record without
formatting it.

**Typed all the way through.** The package ships `py.typed` and is checked with
`pyright` in strict mode, so the annotations are part of the published contract.

**A well-behaved API client.** Requests identify themselves with `tool` and
`email` as the [Entrez usage guidelines][entrez-guidelines] require, honour the
rate limits, and support an `NCBI_API_KEY`. No test in the default suite touches
the network.

[entrez-guidelines]: https://www.ncbi.nlm.nih.gov/books/NBK25497/

## Installation

```bash
pip install pmid-to-citation
```

## Errors

Every failure raises a subclass of `PmidToCitationError`, so one `except` clause
catches anything this library reports:

```python
from pmid_to_citation import PmidToCitationError, RecordNotFoundError
```

| Exception              | Raised when                                            |
| ---------------------- | ------------------------------------------------------ |
| `EntrezError`          | Entrez is unreachable or reports a failure             |
| `RecordNotFoundError`  | Entrez holds no record for the requested PMID          |
| `RecordParseError`     | A response cannot be interpreted as a record           |
| `CitationFormatError`  | A record lacks fields the requested style requires      |

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for the
development setup, the commit message convention, and how releases are cut.

## Security

To report a vulnerability, see [SECURITY.md](SECURITY.md).
