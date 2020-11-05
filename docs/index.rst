.. Apigraph documentation master file, created by
   sphinx-quickstart on Thu Jun 18 19:18:31 2020.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Apigraph
========

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   reference/index
   api-docs/modules


Introduction
~~~~~~~~~~~~

Derives a dependency graph from your OpenAPI 3.0 schema documents.

WIP, not published to PyPI yet.

For usage examples see `test_graph_building.py
<https://github.com/anentropic/apigraph/blob/master/tests/test_graph_building.py>`_  and `test_chains.py <https://github.com/anentropic/apigraph/blob/master/tests/test_chains.py>`_.

This interface will likely change, but for now it looks like:

.. code-block:: python

    from apigraph.graph import APIGraph
    from apigraph.types import NodeKey

    apigraph = APIGraph(doc_uri)
    dependency_chain = apigraph.chain_for_node(
        node_key=NodeKey(doc_uri, "/2.0/repositories/{username}", "get"),
        chain_id="default",
        traverse_anonymous=traverse_anonymous,
    )

Here ``dependency_chain`` will be a ``networkx.MultiDiGraph`` instance containing a graph of all the pre-requisite operations, the edges will have data attached detailing how values from the preceding response are used in the destination request.


Indices and tables
~~~~~~~~~~~~~~~~~~

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
