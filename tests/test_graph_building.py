import pytest
from openapi_orm.models import In, Parameter, RequestBody
from pydantic import ValidationError

from apigraph.graph import APIGraph, DuplicateOperationId
from apigraph.types import (
    HttpMethod,
    LinkDetail,
    LinkType,
    NodeKey,
    OperationDetail,
    ParamKey,
)

from .helpers import fixture_uri, str_doc_with_substitutions


@pytest.mark.parametrize(
    "fixture,chain_id",
    [
        ("links.yaml", None),
        ("links-with-chain-id.yaml", "v2"),
        ("links-local-operationref.yaml", None),
    ],
)
def test_links(fixture, chain_id):
    """
    NOTE: these fixtures use within-doc $refs, so that is tested too
    links.yaml and links-with-chain-id.yaml use `operationId` while
    links-local-operationref.yaml uses a relative (local) `operationRef`

    NOTE: these links all use `parameters` and not `requestBody` or
    `x-apigraph-requestBodyParameters`
    """
    doc_uri = fixture_uri(fixture)

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri}

    expected_nodes = [
        NodeKey(doc_uri, "/2.0/users/{username}", HttpMethod.GET),
        NodeKey(doc_uri, "/2.0/repositories/{username}", HttpMethod.GET),
    ]
    expected_edges = [
        (
            expected_nodes[0],
            expected_nodes[1],
            (chain_id, "200"),
            {
                "response_id": "200",
                "chain_id": chain_id,
                "detail": LinkDetail(
                    link_type=LinkType.LINK,
                    name="userRepositories",
                    description="Get list of repositories",
                    parameters={"username": "$response.body#/username"},
                    requestBody=None,
                    requestBodyParameters={},
                ),
            },
        ),
    ]
    assert [node for node in apigraph.graph.nodes] == expected_nodes
    assert [
        edge for edge in apigraph.graph.edges(data=True, keys=True)
    ] == expected_edges


def test_cross_doc_links(httpx_mock):
    """
    NOTE: cross-doc-links.yaml links via `operationRef` URI to links.yaml
    So between this and `test_links` both `operationRef` and `operationId`
    links are tested
    """
    doc_uri = "https://fakeurl/cross-doc-links.yaml"
    other_doc_uri = fixture_uri("links.yaml")

    raw_doc = str_doc_with_substitutions(
        "tests/fixtures/cross-doc-links.yaml", {"fixture_uri": other_doc_uri},
    )
    httpx_mock.add_response(url=doc_uri, data=raw_doc)

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri, other_doc_uri}

    expected_nodes = [
        NodeKey(doc_uri, "/2.0/users", HttpMethod.POST),
        NodeKey(other_doc_uri, "/2.0/users/{username}", HttpMethod.GET),
        NodeKey(other_doc_uri, "/2.0/repositories/{username}", HttpMethod.GET),
    ]
    expected_edges = [
        (
            expected_nodes[0],
            expected_nodes[1],
            (None, "201"),
            {
                "response_id": "201",
                "chain_id": None,
                "detail": LinkDetail(
                    link_type=LinkType.LINK,
                    name="userByUsername",
                    description="",
                    parameters={"username": "$response.body#/username"},
                    requestBody=None,
                    requestBodyParameters={},
                ),
            },
        ),
        (
            expected_nodes[1],
            expected_nodes[2],
            (None, "200"),
            {
                "response_id": "200",
                "chain_id": None,
                "detail": LinkDetail(
                    link_type=LinkType.LINK,
                    name="userRepositories",
                    description="Get list of repositories",
                    parameters={"username": "$response.body#/username"},
                    requestBody=None,
                    requestBodyParameters={},
                ),
            },
        ),
    ]
    assert [node for node in apigraph.graph.nodes] == expected_nodes
    assert [
        edge for edge in apigraph.graph.edges(data=True, keys=True)
    ] == expected_edges


def test_cross_doc_links_circular_ref(httpx_mock):
    """
    Test that we don't get stuck in infinite loop when resolving doc refs.

    NOTE:
    cross-doc-links.yaml and cross-doc-links-circular-ref.yaml together
    form a circular dependency in that both docs contain links to each other.
    This is via a mutual backlink and a link, since both edges are directed
    identically this should form a redundant edge. So we have a circular ref
    between docs, but not a circular dependency in the request graph.

    NOTE:
    since we are re-using cross-doc-links.yaml but with a different `fixture_uri`
    pre-parse substitution, this test relies on `clear_cache` auto fixture having
    `function` scope...
    """
    doc_uri = "https://fakeurl/cross-doc-links.yaml"
    other_doc_uri = fixture_uri("cross-doc-circular-ref.yaml")

    raw_doc = str_doc_with_substitutions(
        "tests/fixtures/cross-doc-links.yaml", {"fixture_uri": other_doc_uri},
    )
    httpx_mock.add_response(url=doc_uri, data=raw_doc)

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri, other_doc_uri}

    expected_nodes = [
        NodeKey(doc_uri, "/2.0/users", HttpMethod.POST),
        NodeKey(other_doc_uri, "/2.0/users/{username}", HttpMethod.GET),
    ]
    # the backlink+link edges in this case are redundant
    # we expect apigraph to take the backlink over the link
    expected_edges = [
        (
            expected_nodes[0],
            expected_nodes[1],
            (None, "201"),
            {
                "response_id": "201",
                "chain_id": None,
                "detail": LinkDetail(
                    link_type=LinkType.BACKLINK,
                    name="createUser",
                    description="",
                    parameters={},
                    requestBody=None,
                    requestBodyParameters={"/username": "$request.path.username"},
                ),
            },
        ),
    ]
    assert [node for node in apigraph.graph.nodes] == expected_nodes
    assert [
        edge for edge in apigraph.graph.edges(data=True, keys=True)
    ] == expected_edges


def test_links_multiple_chains(httpx_mock):
    doc_uri = fixture_uri("links-with-multiple-chain-id.yaml")

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri}

    # sorted
    expected_nodes = [
        NodeKey(doc_uri, "/1.0/users/{username}", HttpMethod.GET),
        NodeKey(doc_uri, "/2.0/repositories/{username}", HttpMethod.GET),
        NodeKey(doc_uri, "/2.0/users/{username}", HttpMethod.GET),
    ]
    expected_edges = [
        (
            expected_nodes[0],
            expected_nodes[1],
            ("v1", "200"),
            {
                "response_id": "200",
                "chain_id": "v1",
                "detail": LinkDetail(
                    link_type=LinkType.LINK,
                    name="userRepositories",
                    description="Get list of repositories",
                    parameters={"username": "$response.body#/username"},
                    requestBody=None,
                    requestBodyParameters={},
                ),
            },
        ),
        (
            expected_nodes[2],
            expected_nodes[1],
            ("default", "200"),
            {
                "response_id": "200",
                "chain_id": "default",
                "detail": LinkDetail(
                    link_type=LinkType.LINK,
                    name="userRepositories",
                    description="Get list of repositories",
                    parameters={"username": "$response.body#/username"},
                    requestBody=None,
                    requestBodyParameters={},
                ),
            },
        ),
    ]
    assert sorted([node for node in apigraph.graph.nodes]) == expected_nodes
    assert [
        edge for edge in apigraph.graph.edges(data=True, keys=True)
    ] == expected_edges


def test_links_request_body(httpx_mock):
    doc_uri = fixture_uri("links-request-body.yaml")

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri}

    expected_nodes = [
        NodeKey(doc_uri, "/users", HttpMethod.POST),
        NodeKey(doc_uri, "/pets/{id}/add-owner", HttpMethod.POST),
    ]
    expected_edges = [
        (
            expected_nodes[0],
            expected_nodes[1],
            (None, "201"),
            {
                "response_id": "201",
                "chain_id": None,
                "detail": LinkDetail(
                    link_type=LinkType.LINK,
                    name="Add Pet",
                    description="",
                    parameters={},
                    requestBody="$response.body",
                    requestBodyParameters={},
                ),
            },
        ),
    ]
    assert [node for node in apigraph.graph.nodes] == expected_nodes
    assert [
        edge for edge in apigraph.graph.edges(data=True, keys=True)
    ] == expected_edges


def test_links_request_body_params(httpx_mock):
    doc_uri = fixture_uri("links-request-body-params.yaml")

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri}

    expected_nodes = [
        NodeKey(doc_uri, "/users", HttpMethod.POST),
        NodeKey(doc_uri, "/pets", HttpMethod.POST),
    ]
    expected_edges = [
        (
            expected_nodes[0],
            expected_nodes[1],
            (None, "201"),
            {
                "response_id": "201",
                "chain_id": None,
                "detail": LinkDetail(
                    link_type=LinkType.LINK,
                    name="Add Pet",
                    description="",
                    parameters={},
                    requestBody=None,
                    requestBodyParameters={"/owner": "$response.body#/username"},
                ),
            },
        ),
    ]
    assert [node for node in apigraph.graph.nodes] == expected_nodes
    assert [
        edge for edge in apigraph.graph.edges(data=True, keys=True)
    ] == expected_edges


@pytest.mark.parametrize(
    "fixture,chain_id",
    [
        ("backlinks.yaml", None),
        ("backlinks-local-operationref.yaml", None),
        ("backlinks-response-ref.yaml", None),
    ],
)
def test_backlinks(fixture, chain_id):
    """
    NOTE: these links all use `parameters` and not `requestBody` or
    `x-apigraph-requestBodyParameters`
    """
    doc_uri = fixture_uri(fixture)

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri}

    expected_nodes = [
        NodeKey(doc_uri, "/2.0/users/{username}", HttpMethod.GET),
        NodeKey(doc_uri, "/2.0/repositories/{username}", HttpMethod.GET),
    ]
    expected_edges = [
        (
            expected_nodes[0],
            expected_nodes[1],
            (chain_id, "200"),
            {
                "response_id": "200",
                "chain_id": chain_id,
                "detail": LinkDetail(
                    link_type=LinkType.BACKLINK,
                    name="Get User by Username",
                    description="",
                    parameters={"username": "$response.body#/username"},
                    requestBody=None,
                    requestBodyParameters={},
                ),
            },
        ),
    ]
    assert [node for node in apigraph.graph.nodes] == expected_nodes
    assert [
        edge for edge in apigraph.graph.edges(data=True, keys=True)
    ] == expected_edges


def test_cross_doc_backlinks(httpx_mock):
    """
    NOTE: cross-doc-links.yaml links via `operationRef` URI to links.yaml
    So between this and `test_links` both `operationRef` and `operationId`
    links are tested
    """
    doc_uri = "https://fakeurl/cross-doc-backlinks.yaml"
    other_doc_uri = fixture_uri("cross-doc-backlinks-target.yaml")

    raw_doc = str_doc_with_substitutions(
        "tests/fixtures/cross-doc-backlinks.yaml", {"fixture_uri": other_doc_uri},
    )
    httpx_mock.add_response(url=doc_uri, data=raw_doc)

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri, other_doc_uri}

    # (sorted)
    expected_nodes = [
        NodeKey(other_doc_uri, "/2.0/users", HttpMethod.POST),
        NodeKey(doc_uri, "/2.0/repositories/{username}", HttpMethod.GET),
        NodeKey(doc_uri, "/2.0/users/{username}", HttpMethod.GET),
    ]
    expected_edges = [
        (
            expected_nodes[0],
            expected_nodes[2],
            (None, "201"),
            {
                "response_id": "201",
                "chain_id": None,
                "detail": LinkDetail(
                    link_type=LinkType.BACKLINK,
                    name="Create User",
                    description="",
                    parameters={"username": "$response.body#/username"},
                    requestBody=None,
                    requestBodyParameters={},
                ),
            },
        ),
        (
            expected_nodes[2],
            expected_nodes[1],
            (None, "200"),
            {
                "response_id": "200",
                "chain_id": None,
                "detail": LinkDetail(
                    link_type=LinkType.BACKLINK,
                    name="Get User by Username",
                    description="",
                    parameters={"username": "$response.body#/username"},
                    requestBody=None,
                    requestBodyParameters={},
                ),
            },
        ),
    ]
    assert sorted([node for node in apigraph.graph.nodes]) == expected_nodes
    assert (
        sorted([edge for edge in apigraph.graph.edges(data=True, keys=True)])
        == expected_edges
    )


def test_backlinks_multiple_chains():
    doc_uri = fixture_uri("backlinks-multiple-chain-id.yaml")

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri}

    expected_nodes = [
        NodeKey(doc_uri, "/1.0/users/{username}", HttpMethod.GET),
        NodeKey(doc_uri, "/2.0/users/{username}", HttpMethod.GET),
        NodeKey(doc_uri, "/2.0/repositories/{username}", HttpMethod.GET),
    ]
    expected_edges = [
        (
            expected_nodes[0],
            expected_nodes[2],
            ("v1", "200"),
            {
                "response_id": "200",
                "chain_id": "v1",
                "detail": LinkDetail(
                    link_type=LinkType.BACKLINK,
                    name="Get User by Username v1",
                    description="",
                    parameters={"username": "$response.body#/username"},
                    requestBody=None,
                    requestBodyParameters={},
                ),
            },
        ),
        (
            expected_nodes[1],
            expected_nodes[2],
            (None, "200"),
            {
                "response_id": "200",
                "chain_id": None,
                "detail": LinkDetail(
                    link_type=LinkType.BACKLINK,
                    name="Get User by Username",
                    description="",
                    parameters={"username": "$response.body#/username"},
                    requestBody=None,
                    requestBodyParameters={},
                ),
            },
        ),
    ]
    assert [node for node in apigraph.graph.nodes] == expected_nodes
    assert [
        edge for edge in apigraph.graph.edges(data=True, keys=True)
    ] == expected_edges


def test_backlinks_request_body():
    doc_uri = fixture_uri("backlinks-request-body.yaml")

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri}

    expected_nodes = [
        NodeKey(doc_uri, "/users", HttpMethod.POST),
        NodeKey(doc_uri, "/pets/{id}/add-owner", HttpMethod.POST),
    ]
    expected_edges = [
        (
            expected_nodes[0],
            expected_nodes[1],
            (None, "201"),
            {
                "response_id": "201",
                "chain_id": None,
                "detail": LinkDetail(
                    link_type=LinkType.BACKLINK,
                    name="New User",
                    description="",
                    parameters={},
                    requestBody="$response.body",
                    requestBodyParameters={},
                ),
            },
        ),
    ]
    assert [node for node in apigraph.graph.nodes] == expected_nodes
    assert [
        edge for edge in apigraph.graph.edges(data=True, keys=True)
    ] == expected_edges


def test_backlinks_request_body_params():
    doc_uri = fixture_uri("backlinks-request-body-params.yaml")

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri}

    expected_nodes = [
        NodeKey(doc_uri, "/users", HttpMethod.POST),
        NodeKey(doc_uri, "/pets", HttpMethod.POST),
    ]
    expected_edges = [
        (
            expected_nodes[0],
            expected_nodes[1],
            (None, "201"),
            {
                "response_id": "201",
                "chain_id": None,
                "detail": LinkDetail(
                    link_type=LinkType.BACKLINK,
                    name="New User",
                    description="",
                    parameters={},
                    requestBody=None,
                    requestBodyParameters={"/owner": "$response.body#/username"},
                ),
            },
        ),
    ]
    assert [node for node in apigraph.graph.nodes] == expected_nodes
    assert [
        edge for edge in apigraph.graph.edges(data=True, keys=True)
    ] == expected_edges


def test_link_backlink_same_chain_consolidation():
    """
    in case of redundant edge key defined as both link and backlink
    we should store a single edge with detail from the backlink
    (we expect backlinks to be more explicit as they are an apigraph
    extension to OpenAPI)
    """
    doc_uri = fixture_uri("backlinks-with-links-same-chain-id.yaml")

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri}

    expected_nodes = [
        NodeKey(doc_uri, "/2.0/users/{username}", HttpMethod.GET),
        NodeKey(doc_uri, "/2.0/repositories/{username}", HttpMethod.GET),
    ]
    expected_edges = [
        (
            expected_nodes[0],
            expected_nodes[1],
            ("default", "200"),
            {
                "response_id": "200",
                "chain_id": "default",
                "detail": LinkDetail(
                    link_type=LinkType.BACKLINK,
                    name="Get User by Username",
                    description="",
                    parameters={"username": "$response.body#/username"},
                    requestBody=None,
                    requestBodyParameters={},
                ),
            },
        ),
    ]
    assert [node for node in apigraph.graph.nodes] == expected_nodes
    assert [
        edge for edge in apigraph.graph.edges(data=True, keys=True)
    ] == expected_edges


def test_backlinks_via_components_ref():
    """
    We should be able to specify a backlink by using a $ref to refer to
    a shared backlink component.
    """
    doc_uri = fixture_uri("backlinks-components-ref.yaml")

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri}

    expected_nodes = [
        NodeKey(doc_uri, "/users", HttpMethod.POST),
        NodeKey(doc_uri, "/1.0/users/{username}", HttpMethod.GET),
        NodeKey(doc_uri, "/2.0/users/{username}", HttpMethod.GET),
    ]
    expected_edges = [
        (
            expected_nodes[0],
            expected_nodes[1],
            (None, "201"),
            {
                "response_id": "201",
                "chain_id": None,
                "detail": LinkDetail(
                    link_type=LinkType.BACKLINK,
                    name="CreateUser",
                    description="Create a new user that matches the username of current request url segment",
                    parameters={},
                    requestBody=None,
                    requestBodyParameters={"/username": "$request.path.username"},
                ),
            },
        ),
        (
            expected_nodes[0],
            expected_nodes[2],
            (None, "201"),
            {
                "response_id": "201",
                "chain_id": None,
                "detail": LinkDetail(
                    link_type=LinkType.BACKLINK,
                    name="CreateUser",
                    description="Create a new user that matches the username of current request url segment",
                    parameters={},
                    requestBody=None,
                    requestBodyParameters={"/username": "$request.path.username"},
                ),
            },
        ),
    ]
    assert [node for node in apigraph.graph.nodes] == expected_nodes
    assert [
        edge for edge in apigraph.graph.edges(data=True, keys=True)
    ] == expected_edges


@pytest.mark.parametrize(
    "fixture,exception",
    [
        ("invalid-doc-duplicate-operationid.yaml", DuplicateOperationId),
        ("invalid-link-no-operation-identifier.yaml", ValidationError),
        ("invalid-backlink-operationid-no-response-identifier.yaml", ValidationError),
        ("invalid-backlink-operationref-no-response-identifier.yaml", ValidationError),
        ("invalid-backlink-no-operation-identifier.yaml", ValidationError),
    ],
)
def test_invalid(fixture, exception):
    doc_uri = fixture_uri(fixture)

    with pytest.raises(exception):
        APIGraph(doc_uri)


def test_security_resolution():
    """
    OpenAPI allows to specify authentication (`security`) method and
    credentials at the document level, but with per-Operation overrides.

    There are four possible cases:
    1. operation inherits global security options from OpenAPI element
    2. operation overrides with [] to remove all security requirements
    3. operation references a scheme from components that's not in global
    4. operation overrides with a subset of a global
    (there'd also be a 5th option combining 3+4, we'll assume supported due to
    implementation)

    In Apigraph we want to resolve the overrides and attach the correct
    security scheme to each node, i.e. for later use in a request-plan.
    """
    doc_uri = fixture_uri("security.yaml")

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri}

    doc = apigraph.docs[doc_uri]

    assert doc.security == [
        {"httpBearer": []},
        {"OAuth2Password": ["read"]},
    ]
    assert (
        doc.paths["/2.0/users/{username}"].get.security is None
    )  # no override defined on operation

    # sorted (abitrarily in path order for sake of test)
    expected_nodes = [
        (
            NodeKey(doc_uri, "/1.0/users/{username}", HttpMethod.GET),
            {
                "detail": OperationDetail(
                    path="/1.0/users/{username}",
                    method=HttpMethod.GET,
                    summary="",
                    description="",
                    parameters={
                        ParamKey("username", In.PATH): Parameter(
                            **{
                                "name": "username",
                                "in": In.PATH,
                                "required": True,
                                "schema": {"type": "string"},
                            }
                        ),
                    },
                    requestBody=None,
                    # override: only httpBearer accepted
                    security_schemes={
                        frozenset({doc.components.securitySchemes["httpBearer"]}),
                    },
                )
            },
        ),
        (
            NodeKey(doc_uri, "/2.0/repositories/{username}", HttpMethod.GET),
            {
                "detail": OperationDetail(
                    path="/2.0/repositories/{username}",
                    method=HttpMethod.GET,
                    summary="",
                    description="",
                    parameters={
                        ParamKey("username", In.PATH): Parameter(
                            **{
                                "name": "username",
                                "in": In.PATH,
                                "required": True,
                                "schema": {"type": "string"},
                            }
                        ),
                    },
                    requestBody=None,
                    # override: only apiKey accepted
                    security_schemes={
                        frozenset({doc.components.securitySchemes["apiKey"]}),
                    },
                )
            },
        ),
        (
            NodeKey(doc_uri, "/2.0/users", HttpMethod.POST),
            {
                "detail": OperationDetail(
                    path="/2.0/users",
                    method=HttpMethod.POST,
                    summary="",
                    description="",
                    parameters={},
                    requestBody=RequestBody(
                        **{
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "username": {"type": "string"},
                                            "uuid": {"type": "string"},
                                        },
                                    },
                                },
                            },
                        }
                    ),
                    # override: no security required
                    security_schemes=set(),
                )
            },
        ),
        (
            NodeKey(doc_uri, "/2.0/users/{username}", HttpMethod.GET),
            {
                "detail": OperationDetail(
                    path="/2.0/users/{username}",
                    method=HttpMethod.GET,
                    summary="",
                    description="",
                    parameters={
                        ParamKey("username", In.PATH): Parameter(
                            **{
                                "name": "username",
                                "in": In.PATH,
                                "required": True,
                                "schema": {"type": "string"},
                            }
                        ),
                    },
                    requestBody=None,
                    # no security override, either httpBearer or OAuth2Password accepted
                    security_schemes={
                        frozenset({doc.components.securitySchemes["httpBearer"]}),
                        frozenset({doc.components.securitySchemes["OAuth2Password"]}),
                    },
                )
            },
        ),
    ]
    assert sorted([node for node in apigraph.graph.nodes(data=True)]) == expected_nodes


def test_parameter_merging():
    """
    OpenAPI allows to specify parameters at the PathItem level which apply
    to all Operations under that path.

    Operation parameters can override a PathItem param of the same name, but
    empty param list of operation does not remove path params.

    Use of a list rather than map structure means the yaml could contain
    duplicate params in either location with no override intended.
    "A unique parameter is defined by a combination of a name and location."
    OpenAPI docs say:
    > The list MUST NOT include duplicated parameters.
    ...so we can expect this to be validated at the model level.
    """
    doc_uri = fixture_uri("parameters.yaml")

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri}

    # sorted (abitrarily in path, method order for sake of test)
    expected_nodes = [
        (
            NodeKey(doc_uri, "/2.0/users/{username}", HttpMethod.DELETE),
            {
                "detail": OperationDetail(
                    path="/2.0/users/{username}",
                    method=HttpMethod.DELETE,
                    summary="",
                    description="",
                    parameters={
                        ParamKey("username", In.PATH): Parameter(
                            **{
                                "name": "username",
                                "in": In.PATH,
                                "required": True,
                                "schema": {"type": "string"},
                            }
                        ),
                        # additional param of same name, different `in` location
                        ParamKey("username", In.QUERY): Parameter(
                            **{
                                "name": "username",
                                "in": In.QUERY,
                                "required": False,
                                "schema": {"type": "string"},
                            }
                        ),
                        ParamKey("api-token", In.QUERY): Parameter(
                            **{
                                "name": "api-token",
                                "in": In.QUERY,
                                "required": True,  # overridden to true
                                "schema": {"type": "string"},
                            }
                        ),
                    },
                    requestBody=None,
                    security_schemes=set(),
                )
            },
        ),
        (
            NodeKey(doc_uri, "/2.0/users/{username}", HttpMethod.GET),
            {
                "detail": OperationDetail(
                    path="/2.0/users/{username}",
                    method=HttpMethod.GET,
                    summary="",
                    description="",
                    parameters={
                        # only has params inherited from PathItem
                        ParamKey("username", In.PATH): Parameter(
                            **{
                                "name": "username",
                                "in": In.PATH,
                                "required": True,
                                "schema": {"type": "string"},
                            }
                        ),
                        ParamKey("api-token", In.QUERY): Parameter(
                            **{
                                "name": "api-token",
                                "in": In.QUERY,
                                "required": False,
                                "schema": {"type": "string"},
                            }
                        ),
                    },
                    requestBody=None,
                    security_schemes=set(),
                )
            },
        ),
    ]
    assert sorted([node for node in apigraph.graph.nodes(data=True)]) == expected_nodes
