# Contributing

Thanks for your interest in improving `pmid-to-citation`.

## Development setup

The project uses [uv](https://docs.astral.sh/uv/) for dependency management. Every
task runs against the committed `uv.lock`, so local runs and CI resolve to identical
dependency sets.

```bash
git clone https://github.com/medgen-mainz/pmid-to-citation.git
cd pmid-to-citation
make sync
```

## Everyday commands

| Command              | What it does                                                    |
| -------------------- | --------------------------------------------------------------- |
| `make fix`           | Format with `ruff format` and apply safe lint fixes             |
| `make check`         | Verify the lockfile, formatting, lint, and types                |
| `make test`          | Run the test suite with coverage (no network access)            |
| `make test-network`  | Also run the tests that call the live Entrez API (needs `NCBI_EMAIL`) |
| `make refresh-fixtures` | Re-fetch the recorded Entrez responses (needs `NCBI_EMAIL`)   |
| `make test-snapshot` | Re-record [syrupy](https://github.com/syrupy-project/syrupy) snapshots |
| `make docs`          | Build the Sphinx documentation                                  |
| `make check-package` | Build and verify the distribution artifacts                     |

Run `make check test` before opening a pull request.

## Standards

- **Types.** The package ships `py.typed`, so its public API is a typing contract.
  `pyright` runs in strict mode and must report zero errors.
- **Coverage.** `fail_under = 100` with branch coverage enabled. Treat it as a
  ratchet: new code needs new tests, and the floor only ever goes up.
- **Formatting.** `ruff format` with a 120 character line length, and `ruff check`
  for lint. There is no second formatter and no `mypy`; do not add one.
- **Docstrings.** Google style on every public module, class, and function.
- **Dependencies.** Declare one in the same change that first imports it, never
  ahead of use, and justify it in the pull request. Prefer the standard library
  where it is adequate. The runtime set is `citeproc-py`, `httpx`, and `pydantic`.

## Network access in tests

Tests that talk to NCBI must be marked `@pytest.mark.network`. That marker is
deselected by default via `addopts`, and CI never runs it — the suite must not
depend on a third-party service being up, and must not spend the project's
Entrez rate budget on every push.

Everything else stubs HTTP with [respx](https://lundberg.github.io/respx/) and
runs against response bodies recorded under `tests/data/medline/`. Keep recorded
bodies byte-for-byte as Entrez returned them; pre-commit is configured not to
rewrite them. `make refresh-fixtures` re-fetches them when a record has been
revised upstream — review the resulting diff rather than re-recording snapshots
blindly, because a changed citation is a change in what this library promises.

If you do run `make test-network`, be aware of the
[Entrez usage guidelines](https://www.ncbi.nlm.nih.gov/books/NBK25497/): at most
3 requests per second without an API key, and every request must identify itself.

## Adding a citation style

A style is a pure function from a record model to text — no I/O, no fetching.
When proposing one, link the publisher's author guidelines in the pull request and
add snapshot tests covering the awkward cases: missing DOI, absent page numbers,
the "et al." threshold, consortium authors, ahead-of-print articles, and non-ASCII
author names.

## Commit messages and pull requests

The project uses [Conventional Commits](https://www.conventionalcommits.org/), which
[release-please](https://github.com/googleapis/release-please) turns into the changelog
and version bumps. **The pull request title is what lands in the changelog**, and CI
validates its format.

- `fix: ...` — patch release
- `feat: ...` — minor release
- `chore: ...`, `docs: ...`, `refactor: ...`, `test: ...` — no release
- append `!` (e.g. `feat!: ...`) for a breaking change

## Releases

Releases are automated; do not bump versions or edit `CHANGELOG.md` by hand.

1. Merging to `main` makes release-please open or update a release pull request.
2. Merging that pull request tags the release and updates
   `src/pmid_to_citation/version.py`, which is the single source of the version —
   `pyproject.toml` reads it dynamically.
3. CI then rebuilds and re-verifies the artifacts, and publishes to PyPI through
   Trusted Publishing after the `pypi` environment is approved.
