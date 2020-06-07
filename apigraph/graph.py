from typing import Dict, Tuple
from urllib.parse import urlsplit, urlunsplit

import inject
import networkx as nx
from jsonspec.pointer import Pointer
from openapi_orm.models import OpenAPI3Document

from apigraph.loader import load_doc
from apigraph.types import EdgeKey, LinkType, NodeKey


class InvalidLinkError(Exception):
    pass


class DuplicateOperationId(Exception):
    pass


METHODS = {
    "get",
    "put",
    "post",
    "delete",
    "options",
    "head",
    "patch",
    "trace",
}

OperationIdPathIndex = Dict[str, Tuple[str, str]]

DOCUMENT_INDEXES: Dict[str, OperationIdPathIndex] = {}


def _build_operation_id_path_index(doc: OpenAPI3Document):
    index = {}
    for path, path_item in doc.paths.items():
        for method in METHODS:
            operation = getattr(path_item, method)
            operation_id = getattr(operation, "operationId", None)
            if operation_id is not None:
                if operation_id in index:
                    raise DuplicateOperationId(operation_id)
                index[operation_id] = (path, method)
    return index


def get_operation_id_path_index(doc_uri: str, doc: OpenAPI3Document):
    if doc_uri not in DOCUMENT_INDEXES:
        DOCUMENT_INDEXES[doc_uri] = _build_operation_id_path_index(doc)
    return DOCUMENT_INDEXES[doc_uri]


class APIGraph:
    # using a multi-graph for now due to possibility of redundant
    # link + backlink i.e. directed edge defined in same direction
    # from both ends (...or should we consolidate them?)
    graph: nx.MultiDiGraph
    docs: Dict[str, OpenAPI3Document]

    def __init__(self, start_uri: str):
        self.graph = nx.MultiDiGraph()
        self.docs = {}
        self.build(start_uri)

    @inject.params(_dc_settings='settings')
    def build(self, start_uri: str, _dc_settings=None):
        doc = load_doc(start_uri)
        doc_index = get_operation_id_path_index(start_uri, doc)

        uris_to_crawl = set()

        def edge_args_for_links(links):
            for name, link in links.items():
                operation_id = getattr(link, "operationId", None)
                operation_ref = getattr(link, "operationRef", None)
                if operation_id is not None:
                    path, method = doc_index[operation_id]
                elif operation_ref is not None:
                    url = urlsplit(operation_ref)
                    if url.scheme:
                        doc_uri = urlunsplit(url[:-1] + ("",))
                        # add bare node, remote doc into queue
                        # (later we can fill in the operation)
                        uris_to_crawl.add(doc_uri)
                    # we can assume that operationRef is like: `/paths/{path}/{method}`
                    _, path, method = Pointer(url.fragment)
                else:
                    raise InvalidLinkError(link)
                yield (path, method), name, link

        def add_backlinks(to_node, backlinks):
            # NOTE: to/from nodes are not in graph they will be added with no attrs
            for (path, method), name, link in edge_args_for_links(backlinks):
                self.graph.add_edge(
                    NodeKey(start_uri, path, method),
                    to_node,
                    key=EdgeKey(
                        link_type=LinkType.BACKLINK,
                        response_id=None,
                        name=name,
                    ),
                    link=link,
                )

        def add_links(from_node, response_id, links):
            # NOTE: to/from nodes are not in graph they will be added with no attrs
            for (path, method), name, link in edge_args_for_links(links):
                self.graph.add_edge(
                    from_node,
                    NodeKey(start_uri, path, method),
                    key=EdgeKey(
                        link_type=LinkType.LINK,
                        response_id=response_id,
                        name=name,
                    ),
                    link=link,
                )

        for path, path_item in doc.paths.items():
            for method in METHODS:
                operation = getattr(path_item, method)
                if operation is not None:
                    node_key = NodeKey(
                        doc_uri=start_uri,
                        path=path,
                        method=method,
                    )
                    try:
                        existing_op = self.graph.nodes(data='operation')[node_key]
                    except KeyError:
                        existing_op = None

                    if existing_op is None:
                        # either did not exist or was added as placeholder
                        # pending crawl of its doc
                        self.graph.add_node(node_key, operation=operation)

                    backlinks = getattr(operation, _dc_settings.BACKLINKS_ATTR, None)
                    if backlinks is not None:
                        add_backlinks(node_key, backlinks)

                    for response_id, response in operation.responses.items():
                        links = getattr(response, "links", None)
                        if links is not None:
                            add_links(node_key, response_id, links)

        self.docs[start_uri] = doc

        uris_to_crawl -= self.docs.keys()

        for uri in uris_to_crawl:
            self.build(uri)
