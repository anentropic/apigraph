from typing import Dict, Tuple
from urllib.parse import unquote, urlsplit, urlunsplit

import inject
import networkx as nx
from jsonspec.pointer import Pointer
from openapi_orm.models import OpenAPI3Document, Link, Operation

from apigraph.loader import load_doc
from apigraph.types import (
    BacklinkRequestBodyParams,
    EdgeDetail,
    RequestBodyParams,
    LinkType,
    NodeKey,
)


class InvalidLinkError(Exception):
    pass


class InvalidBacklinkOperationError(Exception):
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


# TODO: pre-validate params `from`, can pre-filter too
# also validate that `default` chain id exists
def _backlink_params_for_operation(
    operation_name: str, parameters: BacklinkRequestBodyParams
) -> RequestBodyParams:
    return {
        key: value['select']
        for key, value in parameters.items()
        if value['from'] == operation_name
    }


class APIGraph:
    # using a multi-graph because it's possible to have redundant
    # link + backlink i.e. directed edge defined in same direction
    # but from both ends
    # if they share a chain-id then declarest won't know what to do
    # TODO: consolidate redundant links (fwd+backlink of same chain-id)
    # ...not sure there's any sense in trying to merge, we should just
    # give precedence to one (maybe backlinks?)
    graph: nx.MultiDiGraph
    docs: Dict[str, OpenAPI3Document]

    def __init__(self, start_uri: str):
        self.graph = nx.MultiDiGraph()
        self.docs = {}
        self._build(start_uri)
        # TODO: maybe the indexes should be in here

    def get_operation(self, node_key: NodeKey) -> Operation:
        doc = self.docs[node_key.doc_uri]
        path = doc.paths[node_key.path]
        return getattr(path, node_key.method)

    @inject.params(_dc_settings='settings')
    def _build(self, start_uri: str, _dc_settings=None):
        doc = load_doc(start_uri)
        doc_index = get_operation_id_path_index(start_uri, doc)

        uris_to_crawl = set()

        def _decode_operation_ref(operation_ref: str) -> Tuple[str, str, str]:
            url = urlsplit(operation_ref)
            if url.scheme:
                doc_uri = urlunsplit(url[:-1] + ("",))
                # add remote doc into queue
                uris_to_crawl.add(doc_uri)
            else:
                # relative ref
                doc_uri = start_uri
            # we can assume that operationRef is like: `/paths/{path}/{method}`
            _, path, method = Pointer(url.fragment)
            path = unquote(path)
            return doc_uri, path, method

        def _decode_response_ref(response_ref: str) -> Tuple[str, str, str, str]:
            url = urlsplit(response_ref)
            if url.scheme:
                doc_uri = urlunsplit(url[:-1] + ("",))
                # add remote doc into queue
                uris_to_crawl.add(doc_uri)
            else:
                # relative ref
                doc_uri = start_uri
            # we can assume that responseRef is like: `/paths/{path}/{method}/responses/{response_id}`
            _, path, method, _, response_id = Pointer(url.fragment)
            path = unquote(path)
            return doc_uri, path, method, response_id

        def edge_args_for_backlink_operations(operations: Dict[str, Dict]) -> Tuple[NodeKey, str, str]:
            for name, operation in operations.items():
                response_ref = operation.get("responseRef")
                operation_id = operation.get("operationId")
                operation_ref = operation.get("operationRef")
                if response_ref is not None:
                    doc_uri, path, method, response_id = _decode_response_ref(response_ref)
                elif operation_id is not None:
                    path, method = doc_index[operation_id]
                    doc_uri = start_uri
                    response_id = operation["response"]
                elif operation_ref is not None:
                    doc_uri, path, method = _decode_operation_ref(operation_ref)
                    response_id = operation["response"]
                else:
                    raise InvalidBacklinkOperationError(operation)
                yield NodeKey(doc_uri, path, method), name, response_id

        def add_backlinks(to_node: NodeKey, backlinks):
            # NOTE: to/from nodes which are not in graph will be added with no attrs
            # (such nodes will have attrs filled when we get round to crawling their doc)
            for chain_id, backlink in backlinks.items():
                operations = backlink['operations']
                parameters = backlink.get("parameters", {})
                request_body = backlink.get("requestBody", {})
                request_body_parameters = backlink.get("requestBodyParameters", {})
                for from_node, name, response_id in edge_args_for_backlink_operations(operations):
                    self.graph.add_edge(
                        from_node,
                        to_node,
                        key=f"chain-id:{chain_id}",
                        response_id=response_id,
                        chain_id=chain_id,
                        detail=EdgeDetail(
                            link_type=LinkType.BACKLINK,
                            name=name,
                            description=backlink.get('description', ''),
                            parameters=_backlink_params_for_operation(
                                name, parameters
                            ),
                            requestBody=(
                                request_body['select']
                                if request_body and request_body['from'] == name
                                else None
                            ),
                            requestBodyParameters=_backlink_params_for_operation(
                                name, request_body_parameters
                            ),
                        ),
                    )

        def edge_args_for_links(links: Dict[str, Link]) -> Tuple[NodeKey, str, str, object]:
            for name, link in links.items():
                operation_id = getattr(link, "operationId", None)
                operation_ref = getattr(link, "operationRef", None)
                chain_id = getattr(link, _dc_settings.LINK_CHAIN_ID_ATTR, None)
                if operation_id is not None:
                    path, method = doc_index[operation_id]
                    doc_uri = start_uri
                elif operation_ref is not None:
                    doc_uri, path, method = _decode_operation_ref(operation_ref)
                else:
                    raise InvalidLinkError(link)
                yield NodeKey(doc_uri, path, method), chain_id, name, link

        def add_links(from_node: NodeKey, response_id: str, links):
            # NOTE: to/from nodes which are not in graph will be added with no attrs
            # (such nodes will have attrs filled when we get round to crawling their doc)
            for to_node, chain_id, name, link in edge_args_for_links(links):
                if chain_id is not None:
                    key = f"chain-id:{chain_id}"
                else:
                    key = f"response:{response_id}"
                self.graph.add_edge(
                    from_node,
                    to_node,
                    key=key,
                    response_id=response_id,
                    chain_id=chain_id,
                    detail=EdgeDetail(
                        link_type=LinkType.LINK,
                        name=name,
                        description=link.description or "",
                        parameters=link.parameters or {},
                        requestBody=link.requestBody or None,
                        requestBodyParameters=getattr(
                            link, _dc_settings.LINK_REQUEST_BODY_PARAMS_ATTR, {}
                        ),
                    ),
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
                    self.graph.add_node(node_key)

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
            self._build(uri)
