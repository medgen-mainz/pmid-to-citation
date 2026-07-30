#!/usr/bin/env python3
"""Re-fetch the recorded MEDLINE fixtures from Entrez.

The fixtures under ``tests/data/medline`` are real Entrez responses, kept
byte-for-byte. Without this script they would be unmaintainable: nobody would
know how to regenerate one, and they would drift out of date silently.

Usage::

    NCBI_EMAIL=you@example.org uv run python scripts/refresh_medline_fixtures.py

Set ``NCBI_API_KEY`` too if you have one; it raises the rate limit from 3 to 10
requests per second.

Re-running this will change the recorded bytes if PubMed has revised a record.
That is the point — but it means the snapshots must then be reviewed, not blindly
re-recorded: a changed citation is a change in what this library promises.
"""

import asyncio
import os
import sys
from pathlib import Path

from pmid_to_citation import EntrezClient

FIXTURE_DIR = Path(__file__).parent.parent / "tests" / "data" / "medline"

TOOL = "pmid-to-citation-fixture-refresh"

# Requests per second permitted without an API key. One extra margin of safety
# beyond the documented 3/s, because being blocked affects the whole institution.
REQUESTS_PER_SECOND = 2


async def main() -> int:
    """Re-fetch every recorded fixture in place.

    Returns:
        A process exit status: 0 on success, 1 if the environment is incomplete.
    """
    email = os.environ.get("NCBI_EMAIL")
    if not email:
        print("set NCBI_EMAIL: the Entrez guidelines require a real contact address", file=sys.stderr)
        return 1

    pmids = sorted(int(path.stem) for path in FIXTURE_DIR.glob("*.txt"))
    if not pmids:
        print(f"no fixtures found in {FIXTURE_DIR}", file=sys.stderr)
        return 1

    async with EntrezClient(tool=TOOL, email=email) as client:
        for pmid in pmids:
            # `get_record_text` strips surrounding whitespace, but the fixtures are
            # stored with the single trailing newline a text file should end on.
            # Without restoring it, every refresh would rewrite every last byte.
            text = await client.get_record_text(pmid) + "\n"
            target = FIXTURE_DIR / f"{pmid}.txt"
            changed = not target.exists() or target.read_text(encoding="utf-8") != text
            target.write_text(text, encoding="utf-8")
            print(f"{pmid}: {'updated' if changed else 'unchanged'} ({len(text)} bytes)")
            await asyncio.sleep(1 / REQUESTS_PER_SECOND)

    print(f"\n{len(pmids)} fixtures refreshed. Review `git diff` and then `make test-snapshot`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
