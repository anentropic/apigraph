from typing import Dict, FrozenSet, Optional, Tuple
from urllib.parse import unquote, urlsplit, urlunsplit

import inject
import networkx as nx
from jsonspec.pointer import Pointer
from openapi_orm.models import Link, OpenAPI3Document, Operation

from apigraph.loader import load_doc
from apigraph.types import (
    HTTP_METHODS,
    EdgeDetail,
    EdgeKey,
    LinkType,
    NodeKey,
    OperationIdPathIndex,
)


class InvalidDocumentError(Exception):
    pass


class InvalidLinkError(InvalidDocumentError):
    pass


class InvalidBacklinkError(InvalidDocumentError):
    pass


class DuplicateOperationId(InvalidDocumentError):
    pass


class CircularDependencyError(InvalidDocumentError):
    pass


def _build_operation_id_path_index(doc: OpenAPI3Document) -> OperationIdPathIndex:
    """
    OpenAPI spec allows to refer to an Operation by its name, using the
    `operationId` attribute (in links etc). To ease fetching an
    operation by its name we build an index of id -> (path, method)
    It's then trivial to fetch an Operation from doc by (path, method).
    """
    index: OperationIdPathIndex = {}
    for path, path_item in doc.paths.items():
        for method in HTTP_METHODS:
            operation = getattr(path_item, method)
            operation_id = getattr(operation, "operationId", None)
            if operation_id is not None:
                if operation_id in index:
                    raise DuplicateOperationId(operation_id)
                index[operation_id] = (path, method)
    return index


class APIGraph:
    # We are using a multi-graph because it's possible to have multiple
    # links or backlinks between same endpoints i.e. multiple edges
    # having the same direction but with different chainIds.
    # In cases where they share a chainId then apigraph will consolidate
    # the redundant edges into one by preferring backlinks over links, and
    # arbitrarily in case of link+link or backlink+backlink redundancy.
    graph: nx.MultiDiGraph
    docs: Dict[str, OpenAPI3Document]  # {<doc_uri>: <doc>}
    _indexes: Dict[str, OperationIdPathIndex]  # {<doc_uri>: <index>}
    _chains: Dict[FrozenSet[str], nx.DiGraph]  # {<matched chainIds>: <sub-graph>}

    def __init__(self, start_uri: str):
        self.graph = nx.MultiDiGraph()
        self.docs = {}
        self._indexes = {}
        self._chains = {}
        self._build(start_uri)
        self.graph = nx.freeze(self.graph)

    def get_operation(self, node_key: NodeKey) -> Operation:
        """
        Get operation element specified by `node_key` from relevant api doc.
        """
        doc = self.docs[node_key.doc_uri]
        path = doc.paths[node_key.path]
        return getattr(path, node_key.method)

    def chain_for_node(
        self, node_key: NodeKey, chain_id: str, traverse_anonymous: bool = True
    ) -> nx.MultiDiGraph:
        """
        Get a subgraph view containing ancestors of `node_key` which
        are related via edges having this `chain_id`.

        NOTE: Includes the node identified by `node_key` itself.

        If `traverse_anonymous=True` then will return ancestors with no chain_id
        in additional to the requested chain_id (this is because chainId is an
        extension to OpenAPI and you may reach documents which do not use it, also
        it allows to avoid creating redundant links for multiple chains, null chain
        can be used as a default link).

        Raises:
            CircularDependencyError
        """
        if traverse_anonymous:
            chain_key = frozenset([chain_id, None])
        else:
            chain_key = frozenset([chain_id])

        if chain_id not in self._chains:
            # materialize a view
            chain_view = nx.subgraph_view(
                self.graph, filter_edge=lambda _u, _v, key: key.chain_id in chain_key,
            )
            # check for cycles...
            # if not nx.is_directed_acyclic_graph(chain_view):
            #     raise CircularDependencyError(
            #         node_key,
            #         chain_id,
            #         nx.simple_cycles(chain_view),  # (generator)
            #     )
            # memoize
            self._chains[chain_key] = nx.freeze(chain_view)
        chain = self._chains[chain_key]

        # filter chain for ancestors of node_key
        dependencies = nx.ancestors(chain, node_key) | {node_key}
        return chain.subgraph(dependencies)

    def _get_operation_id_path_index(
        self, doc_uri: str, doc: OpenAPI3Document
    ) -> OperationIdPathIndex:
        if doc_uri not in self._indexes:
            self._indexes[doc_uri] = _build_operation_id_path_index(doc)
        return self._indexes[doc_uri]

    @inject.params(_dc_settings="settings")
    def _build(self, start_uri: str, _dc_settings=None):
        doc = load_doc(start_uri)
        doc_index = self._get_operation_id_path_index(start_uri, doc)

        uris_to_crawl = set()

        def _pointer_from_ref(ref: str) -> Tuple[Pointer, str]:
            url = urlsplit(ref)
            if url.scheme:
                doc_uri = urlunsplit(url[:-1] + ("",))
                # add remote doc into queue
                uris_to_crawl.add(doc_uri)
            else:
                # relative ref
                doc_uri = start_uri
            return Pointer(url.fragment), doc_uri

        def _decode_operation_ref(operation_ref: str) -> Tuple[str, str, str]:
            # we can assume that operationRef is like: `/paths/{path}/{method}`
            (_, path, method), doc_uri = _pointer_from_ref(operation_ref)
            path = unquote(path)
            return doc_uri, path, method

        def _decode_response_ref(response_ref: str) -> Tuple[str, str, str, str]:
            # we can assume that responseRef is like: `/paths/{path}/{method}/responses/{response_id}`
            (_, path, method, _, response_id), doc_uri = _pointer_from_ref(response_ref)
            path = unquote(path)
            return doc_uri, path, method, response_id

        def edge_args_for_backlink(
            backlink: Dict[str, Dict]
        ) -> Tuple[NodeKey, Optional[str], str]:
            response_ref = backlink.responseRef
            operation_id = backlink.operationId
            operation_ref = backlink.operationRef
            response_id = backlink.response
            chain_id = backlink.chainId
            if response_ref is not None:
                doc_uri, path, method, response_id = _decode_response_ref(response_ref)
            elif operation_id is not None and response_id is not None:
                path, method = doc_index[operation_id]
                doc_uri = start_uri
            elif operation_ref is not None and response_id is not None:
                doc_uri, path, method = _decode_operation_ref(operation_ref)
            else:
                raise InvalidBacklinkError(backlink)
            return NodeKey(doc_uri, path, method), chain_id, response_id

        def add_backlinks(to_node: NodeKey, backlinks):
            # NOTE: to/from nodes which are not in graph will be added with no attrs
            # (such nodes will have attrs filled when we get round to crawling their doc)
            for name, backlink in backlinks.items():
                from_node, chain_id, response_id = edge_args_for_backlink(backlink)
                key = EdgeKey(chain_id, response_id)
                self.graph.add_edge(
                    from_node,
                    to_node,
                    key=key,
                    response_id=response_id,
                    chain_id=chain_id,
                    detail=EdgeDetail(
                        link_type=LinkType.BACKLINK,
                        name=name,
                        description=backlink.description,
                        parameters=backlink.parameters,
                        requestBody=backlink.requestBody,
                        requestBodyParameters=backlink.requestBodyParameters,
                    ),
                )

        def edge_args_for_link(link: Link) -> Tuple[NodeKey, str, Link]:
            operation_id = link.operationId
            operation_ref = link.operationRef
            chain_id = link.chainId
            if operation_id is not None:
                path, method = doc_index[operation_id]
                doc_uri = start_uri
            elif operation_ref is not None:
                doc_uri, path, method = _decode_operation_ref(operation_ref)
            else:
                raise InvalidLinkError(link)
            return NodeKey(doc_uri, path, method), chain_id

        def add_links(from_node: NodeKey, response_id: str, links):
            # NOTE: to/from nodes which are not in graph will be added with no attrs
            # (such nodes will have attrs filled when we get round to crawling their doc)
            for name, link in links.items():
                to_node, chain_id = edge_args_for_link(link)
                key = EdgeKey(chain_id, response_id)
                # in case of redundant edges, backlinks win
                # (and otherwise last-write wins)
                if (
                    from_node in self.graph
                    and to_node in self.graph[from_node]
                    and key in self.graph[from_node][to_node]
                    and self.graph[from_node][to_node][key]["detail"].link_type
                    is LinkType.BACKLINK
                ):
                    continue
                self.graph.add_edge(
                    from_node,
                    to_node,
                    key=key,
                    response_id=response_id,
                    chain_id=chain_id,
                    detail=EdgeDetail(
                        link_type=LinkType.LINK,
                        name=name,
                        description=link.description,
                        parameters=link.parameters,
                        requestBody=link.requestBody,
                        requestBodyParameters=link.requestBodyParameters,
                    ),
                )

        for path, path_item in doc.paths.items():
            for method in HTTP_METHODS:
                operation = getattr(path_item, method)
                if operation is not None:
                    node_key = NodeKey(doc_uri=start_uri, path=path, method=method,)
                    self.graph.add_node(
                        node_key,
                        security=(
                            operation.security
                            if operation.security is not None
                            else doc.security
                        ),
                    )

                    for response_id, response in operation.responses.items():
                        add_links(node_key, response_id, response.links)

                    add_backlinks(node_key, operation.backlinks)

        self.docs[start_uri] = doc

        # remove any docs we already crawled
        uris_to_crawl -= self.docs.keys()

        for uri in uris_to_crawl:
            self._build(uri)
