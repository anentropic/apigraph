# apigraph
Derives a dependency graph from your OpenAPI 3.0 schema documents.

WIP, not published to PyPI yet.

See docs here:
https://apigraph.readthedocs.io/

## Introduction

For usage examples see [test_graph_building.py](https://github.com/anentropic/apigraph/blob/master/tests/test_graph_building.py) and [test_chains.py](https://github.com/anentropic/apigraph/blob/master/tests/test_chains.py).

This interface will likely change, but for now it looks like:

```python
from apigraph.graph import APIGraph
from apigraph.types import NodeKey

apigraph = APIGraph(openapi_yaml_doc_uri)
dependency_chain = apigraph.chain_for_node(
    node_key=NodeKey(doc_uri, "/2.0/repositories/{username}", "get"),
    chain_id="default",
    traverse_anonymous=traverse_anonymous,
)
```

Here `dependency_chain` will be a `networkx.MultiDiGraph` instance containing a graph of all the pre-requisite operations, the edges will have data attached detailing how values from the preceding response are used in the destination request.

## Development

Install https://pre-commit.com/ e.g.

```bash
brew install pre-commit
pre-commit install
```

To preview the .rst docs via a local webserver:

```bash
sphinx-reload docs/
```
