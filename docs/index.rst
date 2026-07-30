pmid-to-citation
================

**pmid-to-citation** fetches PubMed records from the NCBI Entrez API by PMID and
renders them as citation/reference text. Nature style is the initial target.

.. warning::

   The project is in early development. Packaging, typing, and CI are in place;
   the Entrez client and the citation formatters land in follow-up releases.
   Until version 1.0.0 the public API may change between minor releases.

Installation
------------

.. code-block:: bash

   pip install pmid-to-citation

Requires Python 3.13 or newer.

Design goals
------------

* **Typed.** The package ships ``py.typed`` and is checked with pyright in
  strict mode, so the annotations are part of the published contract.
* **Separation of fetching and formatting.** Retrieving a record from Entrez and
  turning a record into reference text are independent steps; either can be used
  without the other.
* **Well-behaved API client.** Requests identify themselves and respect the
  Entrez rate limits, and no test in the default suite touches the network.

Errors
------

Every failure raises a subclass of
:class:`~pmid_to_citation.exceptions.PmidToCitationError`, so one ``except``
clause is enough to catch anything this library reports.

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
