# Copilot / AI assistant instructions

This repository is a small, strictly typed Python library: it fetches PubMed
records from the NCBI Entrez API by PMID and renders them as citation/reference
text (Nature style first). Suggestions must be reviewed against the rules below.

## Tooling — use these exact tools

| Concern         | Tool                                    |
| --------------- | --------------------------------------- |
| Environment     | `uv`, against the committed `uv.lock`   |
| Lint + format   | `ruff` (there is no black, no flake8)   |
| Types           | `pyright` in **strict** mode            |
| Tests           | `pytest`, `respx`, `syrupy`             |
| Docs            | Sphinx, Google-style docstrings         |
| Releases        | release-please → PyPI Trusted Publishing |

Do not suggest adding a second formatter, `mypy`, `setup.py`, `requirements.txt`,
`tox`, or `poetry`. Run `make check` and `make test`; `make fix` formats.

## Dependencies

The runtime set is **`citeproc-py`, `httpx`, and `pydantic`** — nothing else. A
dependency is declared in `pyproject.toml` in the same change that first imports
it, never ahead of use. Prefer the standard library where it is adequate, and when
a new dependency really is warranted, say so explicitly and justify it rather than
adding it silently. The same applies to the `dev` group.

Note that `citeproc-py` pulls in `lxml`, a compiled package, so this is no longer
a pure-Python dependency tree even though the wheel itself is pure Python.

## Types

- Annotate every parameter, return value, and attribute. `pyright` strict must
  report zero errors, so `Any` needs a reason, and `# type: ignore` needs a
  comment saying why.
- Data parsed out of Entrez responses belongs in Pydantic models that validate
  and normalise their fields (author name parts, page ranges, publication dates)
  — not in bare `dict`s passed around as `dict[str, Any]`.
- The package ships `py.typed`. Its annotations are a published contract:
  changing one is an API change.

## Network access

- **Never** call NCBI from a test unless it is marked `@pytest.mark.network`.
  Those tests are deselected by default (see `addopts`) and CI never runs them.
- Default tests stub HTTP with `respx` and run against response bodies recorded
  under `tests/data/medline/`. Recorded bodies are kept byte-for-byte as Entrez
  returned them; pre-commit is configured not to rewrite them, and
  `scripts/refresh_medline_fixtures.py` is how they are regenerated.
- Entrez has rules, and code that ignores them gets the caller's IP blocked:
  send a `tool` and `email` parameter, keep to at most 3 requests per second
  without an API key, and support `NCBI_API_KEY` where one is available.
- Batch requests where the API allows it. `EntrezClient.get_records` already
  does: it chunks at `batch_size`, switches to POST for long lists, and paces
  requests through `_RateLimiter`. Adding a code path that issues N single-PMID
  requests instead is a bug, not a style choice.
- Entrez omits PMIDs it does not know rather than reporting them, so a batch
  result is keyed by the PMID found in each record — never by request order.

## Structure

Fetching and formatting are separate concerns and must not be entangled:

1. **Client** — talks to Entrez, returns raw response bodies. Knows about HTTP,
   retries, and rate limits. Knows nothing about citations.
2. **Record models** — validated, normalised models of a PubMed record. Know
   nothing about HTTP or about output formats.
3. **Styles** — turn a record into reference text. Pure functions over the
   models; no I/O. Rendering goes through CSL and citeproc, which is an
   implementation detail: **no CSL type may appear in the public API**, so that
   the back end stays replaceable. `_csl.py` is private for that reason.

A caller must be able to format a record it obtained elsewhere, and to fetch a
record without formatting it.

## Errors

Raise the exceptions in `pmid_to_citation.exceptions`; every one derives from
`PmidToCitationError`. Add a new subclass rather than raising a bare `ValueError`
or `RuntimeError`, and never let a transport-level exception escape the client
unwrapped.

## Tests

- New behaviour needs new tests. Coverage is a ratchet at `fail_under = 100`.
- Cover the messy real cases: missing DOI, no page numbers, "et al." thresholds,
  collective/consortium authors, ahead-of-print articles, retractions, and
  non-ASCII author names.
- Use `syrupy` snapshots for rendered citation text, and `make test-snapshot` to
  re-record them. Review snapshot diffs; do not re-record to make a test pass.

## Docstrings and comments

Google style, on every public module, class, and function, with `Args:`,
`Returns:`, and `Raises:`. Comments explain *why*, not *what*. Where the code
follows a rule from a style guide or from the Entrez documentation, cite it.

## Commits

Conventional Commits; the PR title becomes the changelog entry and CI validates
it. Never edit `CHANGELOG.md` or the version by hand — release-please owns both.
