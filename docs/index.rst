pmid-to-citation
================

**pmid-to-citation** fetches PubMed records from the NCBI Entrez API by PMID and
renders them as citation/reference text. Nature style ships with it.

.. warning::

   The project is pre-1.0: the public API may change between minor releases.

Installation
------------

.. code-block:: bash

   pip install pmid-to-citation

Requires Python 3.13 or newer.

Quick start
-----------

``tool`` and ``email`` are required, and deliberately have no defaults: the
`Entrez usage guidelines <https://www.ncbi.nlm.nih.gov/books/NBK25497/>`_ require
every request to identify its caller, and a library must not answer that on its
user's behalf.

.. code-block:: python

   import asyncio
   from pmid_to_citation import fetch_citation

   citation = asyncio.run(fetch_citation(1, tool="my-app", email="me@example.org"))

The rendered text is an **HTML fragment**: the Nature style italicises journal
names, emboldens volume numbers, and ``&`` arrives as ``&amp;``. Treat it as
markup, not as plain text.

The three layers
----------------

Fetching and formatting are separate concerns, and each layer is usable on its own.

1. :class:`~pmid_to_citation.client.EntrezClient` talks to Entrez over HTTP and
   knows nothing about citations. Reuse one client across records, and use
   :meth:`~pmid_to_citation.client.EntrezClient.get_records` to fetch many PMIDs
   in a handful of requests rather than one each.
2. :func:`~pmid_to_citation.parser.parse_medline` turns MEDLINE text into a
   :class:`~pmid_to_citation.models.PubMedRecord`, with no knowledge of HTTP or
   of output formats.
3. :class:`~pmid_to_citation.formatter.CitationFormatter` renders a record. Pure
   functions over the models; no I/O.

:func:`~pmid_to_citation.facade.fetch_citation` composes all three for one PMID;
:func:`~pmid_to_citation.facade.fetch_citations` does it for many, batching the
requests and returning a mapping keyed by PMID. PMIDs Entrez does not know are
absent from that mapping rather than raising — it omits them silently, and one bad
identifier should not defeat a request for hundreds.

Rendering goes through `citeproc-py <https://github.com/citeproc-py/citeproc-py>`_
and a Citation Style Language definition, which is what will make further styles
cheap to add. That is an implementation detail: no CSL type appears in the public
API.

Rate limits
-----------

Entrez permits 3 requests per second without an API key and 10 with one. Set
``NCBI_API_KEY`` in the environment and the client will pick it up, and the client
will hold itself to whichever limit applies. Code that ignores these limits gets
the caller's IP blocked.

Batching matters for the same reason: fetching 200 PMIDs one at a time spends over
a minute of the caller's rate budget on work that takes a single request.

Errors
------

Every failure raises a subclass of
:class:`~pmid_to_citation.exceptions.PmidToCitationError`, so one ``except``
clause is enough to catch anything this library reports.

Typing
------

The package ships ``py.typed`` and is checked with ``pyright`` in strict mode, so
the annotations are part of the published contract.

Table of Contents
-----------------

.. toctree::
    :maxdepth: 1
    :caption: Contents

    self

.. toctree::
    :maxdepth: 1
    :caption: API Docs

    api

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
