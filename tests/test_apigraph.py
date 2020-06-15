from pathlib import Path
from typing import Dict

import inject
import pytest

from apigraph.graph import APIGraph
from apigraph.types import EdgeDetail, LinkType, NodeKey


@pytest.fixture(scope="session", autouse=True)
@inject.params(_dc_cache='cache')
def clear_cache(_dc_cache=None):
    _dc_cache.clear()


def fixture_uri(rel_path: str) -> str:
    path = Path(__file__).parent / Path("fixtures") / Path(rel_path)
    return f"file://{path}"


def str_doc_with_substitutions(rel_path: str, substitutions: Dict[str, str]) -> str:
    with open(rel_path) as f:
        content = f.read()
    return content.format(**substitutions)


@pytest.mark.parametrize("fixture,chain_id", [
    ("links.yaml", None),
    ("links-with-chain-id.yaml", "default"),
    ("links-local-ref.yaml", None),
])
def test_links(fixture, chain_id):
    """
    NOTE: these fixtures use within-doc $refs, so that is tested too
    links.yaml and links-with-chain-id.yaml use `operationId` while
    links-local-ref.yaml uses a relative (local) `operationRef`

    NOTE: these links all use `parameters` and not `requestBody`
    """
    doc_uri = fixture_uri(fixture)

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri}

    expected_nodes = [
        NodeKey(doc_uri, "/2.0/users/{username}", "get"),
        NodeKey(doc_uri, "/2.0/repositories/{username}", "get"),
    ]
    if chain_id:
        key = f"chain-id:{chain_id}"
    else:
        key = "response:{}"
    expected_edges = [
        (
            expected_nodes[0],
            expected_nodes[1],
            key.format("200"),
            {
                "response_id": "200",
                "chain_id": chain_id,
                "detail": EdgeDetail(
                    link_type=LinkType.LINK,
                    name="userRepositories",
                    description="Get list of repositories",
                    parameters={
                        "username": "$response.body#/username",
                    },
                    requestBody=None,
                    requestBodyParameters={},
                ),
            },
        ),
    ]
    assert [node for node in apigraph.graph.nodes] == expected_nodes
    assert [edge for edge in apigraph.graph.edges(data=True, keys=True)] == expected_edges


def test_cross_doc_links(httpx_mock):
    """
    NOTE: cross-doc-links.yaml links via `operationRef` URI to links.yaml
    So between this and `test_links` both `operationRef` and `operationId`
    links are tested
    """
    doc_uri = "https://fakeurl/cross-doc-links.yaml"
    other_doc_uri = fixture_uri("links.yaml")

    raw_doc = str_doc_with_substitutions(
        "tests/fixtures/cross-doc-links.yaml",
        {"fixture_uri": other_doc_uri},
    )
    httpx_mock.add_response(url=doc_uri, data=raw_doc)

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri, other_doc_uri}

    expected_nodes = [
        NodeKey(doc_uri, "/2.0/users", "post"),
        NodeKey(other_doc_uri, "/2.0/users/{username}", "get"),
        NodeKey(other_doc_uri, "/2.0/repositories/{username}", "get"),
    ]
    expected_edges = [
        (
            expected_nodes[0],
            expected_nodes[1],
            "response:201",
            {
                "response_id": "201",
                "chain_id": None,
                "detail": EdgeDetail(
                    link_type=LinkType.LINK,
                    name="userByUsername",
                    description="",
                    parameters={
                        "username": "$response.body#/username",
                    },
                    requestBody=None,
                    requestBodyParameters={},
                ),
            },
        ),
        (
            expected_nodes[1],
            expected_nodes[2],
            "response:200",
            {
                "response_id": "200",
                "chain_id": None,
                "detail": EdgeDetail(
                    link_type=LinkType.LINK,
                    name="userRepositories",
                    description="Get list of repositories",
                    parameters={
                        "username": "$response.body#/username",
                    },
                    requestBody=None,
                    requestBodyParameters={},
                ),
            },
        ),
    ]
    assert [node for node in apigraph.graph.nodes] == expected_nodes
    assert [edge for edge in apigraph.graph.edges(data=True, keys=True)] == expected_edges


def test_links_multiple_chains(httpx_mock):
    doc_uri = fixture_uri("links-with-multiple-chain-id.yaml")

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri}

    # sorted
    expected_nodes = [
        NodeKey(doc_uri, "/1.0/users/{username}", "get"),
        NodeKey(doc_uri, "/2.0/repositories/{username}", "get"),
        NodeKey(doc_uri, "/2.0/users/{username}", "get"),
    ]
    expected_edges = [
        (
            expected_nodes[0],
            expected_nodes[1],
            "chain-id:v1",
            {
                "response_id": "200",
                "chain_id": "v1",
                "detail": EdgeDetail(
                    link_type=LinkType.LINK,
                    name="userRepositories",
                    description="Get list of repositories",
                    parameters={
                        "username": "$response.body#/username",
                    },
                    requestBody=None,
                    requestBodyParameters={},
                ),
            },
        ),
        (
            expected_nodes[2],
            expected_nodes[1],
            "chain-id:default",
            {
                "response_id": "200",
                "chain_id": "default",
                "detail": EdgeDetail(
                    link_type=LinkType.LINK,
                    name="userRepositories",
                    description="Get list of repositories",
                    parameters={
                        "username": "$response.body#/username",
                    },
                    requestBody=None,
                    requestBodyParameters={},
                ),
            },
        ),
    ]
    assert sorted([node for node in apigraph.graph.nodes]) == expected_nodes
    assert [edge for edge in apigraph.graph.edges(data=True, keys=True)] == expected_edges


def test_links_request_body_params(httpx_mock):
    doc_uri = fixture_uri("links-request-body.yaml")

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri}

    expected_nodes = [
        NodeKey(doc_uri, "/users", "post"),
        NodeKey(doc_uri, "/pets", "post"),
    ]
    expected_edges = [
        (
            expected_nodes[0],
            expected_nodes[1],
            "chain-id:default",
            {
                "response_id": "201",
                "chain_id": "default",
                "detail": EdgeDetail(
                    link_type=LinkType.LINK,
                    name="Add Pet",
                    description="",
                    parameters={},
                    requestBody=None,
                    requestBodyParameters={
                        "/owner": "$response.body#/username",
                    },
                ),
            },
        ),
    ]
    assert [node for node in apigraph.graph.nodes] == expected_nodes
    assert [edge for edge in apigraph.graph.edges(data=True, keys=True)] == expected_edges


@pytest.mark.parametrize("fixture,chain_id", [
    ("backlinks.yaml", "default"),
    ("backlinks-local-ref.yaml", "default"),
    ("backlinks-response-ref.yaml", "default"),
])
def test_backlinks(fixture, chain_id):
    """
    NOTE: these links all use `parameters` and not `requestBody`
    """
    doc_uri = fixture_uri(fixture)

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri}

    expected_nodes = [
        NodeKey(doc_uri, "/2.0/users/{username}", "get"),
        NodeKey(doc_uri, "/2.0/repositories/{username}", "get"),
    ]
    expected_edges = [
        (
            expected_nodes[0],
            expected_nodes[1],
            f"chain-id:{chain_id}",
            {
                "response_id": "200",
                "chain_id": chain_id,
                "detail": EdgeDetail(
                    link_type=LinkType.BACKLINK,
                    name="Get User by Username",
                    description="",
                    parameters={
                        "username": "$response.body#/username",
                    },
                    requestBody=None,
                    requestBodyParameters={},
                ),
            },
        ),
    ]
    assert [node for node in apigraph.graph.nodes] == expected_nodes
    assert [edge for edge in apigraph.graph.edges(data=True, keys=True)] == expected_edges


def test_cross_doc_backlinks(httpx_mock):
    """
    NOTE: cross-doc-links.yaml links via `operationRef` URI to links.yaml
    So between this and `test_links` both `operationRef` and `operationId`
    links are tested
    """
    doc_uri = "https://fakeurl/cross-doc-backlinks.yaml"
    other_doc_uri = fixture_uri("cross-doc-backlinks-target.yaml")

    raw_doc = str_doc_with_substitutions(
        "tests/fixtures/cross-doc-backlinks.yaml",
        {"fixture_uri": other_doc_uri},
    )
    httpx_mock.add_response(url=doc_uri, data=raw_doc)

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri, other_doc_uri}

    # (sorted)
    expected_nodes = [
        NodeKey(other_doc_uri, "/2.0/users", "post"),
        NodeKey(doc_uri, "/2.0/repositories/{username}", "get"),
        NodeKey(doc_uri, "/2.0/users/{username}", "get"),
    ]
    expected_edges = [
        (
            expected_nodes[0],
            expected_nodes[2],
            "chain-id:default",
            {
                "response_id": "201",
                "chain_id": "default",
                "detail": EdgeDetail(
                    link_type=LinkType.BACKLINK,
                    name="Create User",
                    description="",
                    parameters={
                        "username": "$response.body#/username",
                    },
                    requestBody=None,
                    requestBodyParameters={},
                ),
            },
        ),
        (
            expected_nodes[2],
            expected_nodes[1],
            "chain-id:default",
            {
                "response_id": "200",
                "chain_id": "default",
                "detail": EdgeDetail(
                    link_type=LinkType.BACKLINK,
                    name="Get User by Username",
                    description="",
                    parameters={
                        "username": "$response.body#/username",
                    },
                    requestBody=None,
                    requestBodyParameters={},
                ),
            },
        ),
    ]
    assert sorted([node for node in apigraph.graph.nodes]) == expected_nodes
    assert sorted([edge for edge in apigraph.graph.edges(data=True, keys=True)]) == expected_edges


def test_backlinks_multiple_chains():
    doc_uri = fixture_uri("backlinks-multiple-chain-id.yaml")

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri}

    expected_nodes = [
        NodeKey(doc_uri, "/1.0/users/{username}", "get"),
        NodeKey(doc_uri, "/2.0/users/{username}", "get"),
        NodeKey(doc_uri, "/2.0/repositories/{username}", "get"),
    ]
    expected_edges = [
        (
            expected_nodes[0],
            expected_nodes[2],
            "chain-id:v1",
            {
                "response_id": "200",
                "chain_id": "v1",
                "detail": EdgeDetail(
                    link_type=LinkType.BACKLINK,
                    name="Get User by Username v1",
                    description="",
                    parameters={
                        "username": "$response.body#/username",
                    },
                    requestBody=None,
                    requestBodyParameters={},
                ),
            },
        ),
        (
            expected_nodes[1],
            expected_nodes[2],
            "chain-id:default",
            {
                "response_id": "200",
                "chain_id": "default",
                "detail": EdgeDetail(
                    link_type=LinkType.BACKLINK,
                    name="Get User by Username",
                    description="",
                    parameters={
                        "username": "$response.body#/username",
                    },
                    requestBody=None,
                    requestBodyParameters={},
                ),
            },
        ),
    ]
    assert [node for node in apigraph.graph.nodes] == expected_nodes
    assert [edge for edge in apigraph.graph.edges(data=True, keys=True)] == expected_edges


def test_backlinks_request_body_params():
    doc_uri = fixture_uri("backlinks-request-body.yaml")

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri}

    expected_nodes = [
        NodeKey(doc_uri, "/users", "post"),
        NodeKey(doc_uri, "/pets", "post"),
    ]
    expected_edges = [
        (
            expected_nodes[0],
            expected_nodes[1],
            "chain-id:default",
            {
                "response_id": "201",
                "chain_id": "default",
                "detail": EdgeDetail(
                    link_type=LinkType.BACKLINK,
                    name="New User",
                    description="",
                    parameters={},
                    requestBody=None,
                    requestBodyParameters={
                        "/owner": "$response.body#/username",
                    },
                ),
            },
        ),
    ]
    assert [node for node in apigraph.graph.nodes] == expected_nodes
    assert [edge for edge in apigraph.graph.edges(data=True, keys=True)] == expected_edges


def test_link_backlink_same_chain_consolidation():
    """
    last-write wins, in this case the backlink is crawled last and
    is the detail stored for the edge
    """
    doc_uri = fixture_uri("backlinks-with-links-same-chain-id.yaml")

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri}

    expected_nodes = [
        NodeKey(doc_uri, "/2.0/users/{username}", "get"),
        NodeKey(doc_uri, "/2.0/repositories/{username}", "get"),
    ]
    expected_edges = [
        (
            expected_nodes[0],
            expected_nodes[1],
            "chain-id:default",
            {
                "response_id": "200",
                "chain_id": "default",
                "detail": EdgeDetail(
                    link_type=LinkType.BACKLINK,
                    name="Get User by Username",
                    description="",
                    parameters={
                        "username": "$response.body#/username",
                    },
                    requestBody=None,
                    requestBodyParameters={},
                ),
            },
        ),
    ]
    assert [node for node in apigraph.graph.nodes] == expected_nodes
    assert [edge for edge in apigraph.graph.edges(data=True, keys=True)] == expected_edges


def test_security_resolution():
    """
    There are four possible cases:
    1. operation inherits global security options from OpenAPI element
    2. operation overrides with [] to remove all security requirements
    3. operation references a scheme from components that's not in global
    4. operation overrides with a subset of a global
    (there'd also be a 5th option combining 3+4, we'll assume supported due to
    implementation)
    """
    doc_uri = fixture_uri("security.yaml")

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri}

    assert apigraph.docs[doc_uri].security == [
        {"httpBearer": []}, {"oAuth2Password": ["read"]}
    ]
    assert (
        apigraph
        .docs[doc_uri]
        .paths["/2.0/users/{username}"]
        .get
        .security
    ) is None  # no override defined on operation

    # sorted
    expected_nodes = [
        (
            NodeKey(doc_uri, "/1.0/users/{username}", "get"),
            {
                # override: only httpBearer accepted
                "security": [{"httpBearer": []}],
            },
        ),
        (
            NodeKey(doc_uri, "/2.0/repositories/{username}", "get"),
            {
                # override: only apiKey accepted
                "security": [{"apiKey": []}],
            },
        ),
        (
            NodeKey(doc_uri, "/2.0/users", "post"),
            {
                # override: no security required
                "security": [],
            },
        ),
        (
            NodeKey(doc_uri, "/2.0/users/{username}", "get"),
            {
                # no security override, either httpBearer or oAuth2Password accepted
                "security": [{"httpBearer": []}, {"oAuth2Password": ["read"]}],
            },
        ),
    ]
    assert sorted([node for node in apigraph.graph.nodes(data=True)]) == expected_nodes
