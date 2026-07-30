# Security Policy

## Supported versions

Only the latest released version of `pmid-to-citation` receives security fixes.

## Reporting a vulnerability

Please **do not** open a public issue for a security problem.

Report it privately through GitHub's
[private vulnerability reporting](https://github.com/medgen-mainz/pmid-to-citation/security/advisories/new),
or by email to <manuel.holtgrewe@medgen-mainz.de>.

Please include a description of the issue, the affected version, and steps to
reproduce it. You can expect an acknowledgement within 14 days.

## Scope

`pmid-to-citation` is an HTTP client for a third-party API and a parser of its
responses. In scope:

- **Response handling.** Entrez responses are untrusted input. Crashes,
  unbounded resource consumption, or any escape from pure parsing behaviour
  triggered by a malformed or hostile response body — including XML entity
  expansion and external entity resolution — are in scope.
- **Request construction.** PMIDs and other arguments are caller-supplied and
  end up in a URL. Anything that lets a caller redirect a request to an
  unintended host or inject additional parameters is in scope.
- **Credential handling.** An `NCBI_API_KEY` must never be written to logs,
  exception messages, or tracebacks.
- **Rendered output.** Citation text is derived from remote data. If a style
  emits text that is unsafe in its documented target format, that is in scope.

Out of scope: the availability, correctness, or content of the NCBI Entrez API
itself, and rate limiting imposed by NCBI on your own requests.

## Release integrity

Releases are published to PyPI from GitHub Actions using
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/), and are signed with
[PEP 740](https://peps.python.org/pep-0740/) attestations. No long-lived API token
exists that could be used to publish this package.
