# All targets run through `uv` against the committed `uv.lock`, so local runs
# and CI resolve to byte-identical dependency sets.

SOURCES := src tests docs scripts

.PHONY: default
default: help

.PHONY: help
help:
	@echo "Available targets:"
	@echo "  help                   Show this help message"
	@echo "  sync                   Install the locked dev environment"
	@echo "  fix                    Format source code"
	@echo "  check                  Run lint and type checks"
	@echo "  test                   Run tests"
	@echo "  test-network           Run tests including those that call NCBI"
	@echo "  test-snapshot          Re-record syrupy snapshots"
	@echo "  docs                   Build documentation"
	@echo "  docs-clean             Clean documentation build"
	@echo "  build                  Build sdist and wheel"
	@echo "  check-package          Build and verify the distribution artifacts"

.PHONY: sync
sync:
	uv sync --locked --all-groups

.PHONY: fix
fix:
	uv run ruff format $(SOURCES)
	uv run ruff check --fix --unsafe-fixes $(SOURCES)
	$(MAKE) check

.PHONY: check
check:
	uv lock --check
	uv run ruff format --check --diff $(SOURCES)
	uv run ruff check $(SOURCES)
	uv run pyright $(SOURCES)

.PHONY: test
test:
	uv run pytest --cov --cov-report=term-missing --durations 5

# Deliberately separate from `test`: these hit the live Entrez API, so they are
# slow, rate-limited, and cannot run in CI. Needs NCBI_EMAIL set.
.PHONY: test-network
test-network:
	uv run pytest -m "network or not network" --durations 5

# Re-fetches the recorded Entrez responses under tests/data/medline. Needs
# NCBI_EMAIL set. Review `git diff` afterwards: a changed fixture may change a
# rendered citation, which is a change in what this library promises.
.PHONY: refresh-fixtures
refresh-fixtures:
	uv run python scripts/refresh_medline_fixtures.py

.PHONY: test-snapshot
test-snapshot:
	uv run pytest --cov --cov-report=term-missing --durations 5 --snapshot-update

.PHONY: docs
docs:
	uv run sphinx-build -b html docs docs/_build/html

.PHONY: docs-clean
docs-clean:
	rm -rf docs/_build

.PHONY: docs-serve
docs-serve:
	uv run python -m http.server 8000 --directory docs/_build/html

.PHONY: build
build:
	rm -rf dist
	uv build

# Guards against the class of packaging bug where the sdist is malformed and a
# wheel rebuilt from it is empty but still installable.
.PHONY: check-package
check-package: build
	rm -rf dist-from-sdist
	uv build --wheel --out-dir dist-from-sdist dist/*.tar.gz
	uvx twine check dist/* dist-from-sdist/*
	uvx check-wheel-contents dist-from-sdist/*.whl
	uv run --isolated --no-project --with dist-from-sdist/*.whl \
		python -c "import pmid_to_citation, pathlib; \
		root = pathlib.Path(pmid_to_citation.__file__).parent; \
		assert (root / 'py.typed').is_file(), 'py.typed missing from wheel'; \
		assert (root / 'styles' / 'nature.csl').is_file(), 'CSL styles missing from wheel'; \
		print(pmid_to_citation.CitationFormatter().format_citation(pmid_to_citation.PubMedRecord(pmid=1, title='A paper'))); \
		print('package OK:', pmid_to_citation.__version__)"
