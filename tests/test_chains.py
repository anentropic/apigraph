from apigraph.graph import APIGraph
from apigraph.types import EdgeDetail, LinkType, NodeKey

from .helpers import fixture_uri


def test_get_prerequisites():
    """
    The test fixture contains three dependency chains, two of which begin
    at `createUser` and `createUserv1` respectively and both ending at
    `getRepository`.

    We test that the third chain (which links to the starts of the other two
    but with a distinct chain-id) is not selected.

    We request dependencies of `getRepositoriesByOwner`, which is not at the
    end of either chain (is followed by `getRepository`) and check that we
    only select up to the requested node and no further.
    """
    doc_uri = fixture_uri("dependencies.yaml")

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri}

    default_deps = apigraph.get_prerequisites(
        node_key=NodeKey(doc_uri, "/2.0/repositories/{username}", "get"),
        chain_id="default",
    )
    v1_deps = apigraph.get_prerequisites(
        node_key=NodeKey(doc_uri, "/2.0/repositories/{username}", "get"), chain_id="v1",
    )

    # dependencies from the "default" chain
    # NOTE: the "invite" predecessor is not included due to different chain id
    # NOTE: subsequent op `/2.0/repositories/{username}/{slug}` is not include
    # (sorted)
    default_expected_nodes = [
        NodeKey(doc_uri, "/2.0/repositories/{username}", "get"),
        NodeKey(doc_uri, "/2.0/users", "post"),
        NodeKey(doc_uri, "/2.0/users/{username}", "get"),
    ]
    # NOTE: edges don't have edge-keys because the view is not a MultiGraph
    default_expected_edges = [
        (
            default_expected_nodes[1],
            default_expected_nodes[2],
            {
                "response_id": "201",
                "chain_id": "default",
                "detail": EdgeDetail(
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
            default_expected_nodes[2],
            default_expected_nodes[0],
            {
                "response_id": "200",
                "chain_id": "default",
                "detail": EdgeDetail(
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
    assert sorted([node for node in default_deps.nodes]) == default_expected_nodes
    assert (
        sorted([edge for edge in default_deps.edges(data=True)])
        == default_expected_edges
    )

    # dependencies from the "v1" chain
    # NOTE: the "invite" predecessor is not included due to different chain id
    v1_expected_nodes = [
        NodeKey(doc_uri, "/1.0/users", "post"),
        NodeKey(doc_uri, "/1.0/users/{username}", "get"),
        NodeKey(doc_uri, "/2.0/repositories/{username}", "get"),
    ]
    # NOTE: edges don't have edge-keys because the view is not a MultiGraph
    v1_expected_edges = [
        (
            v1_expected_nodes[0],
            v1_expected_nodes[1],
            {
                "response_id": "201",
                "chain_id": "v1",
                "detail": EdgeDetail(
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
            v1_expected_nodes[1],
            v1_expected_nodes[2],
            {
                "response_id": "200",
                "chain_id": "v1",
                "detail": EdgeDetail(
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
    assert sorted([node for node in v1_deps.nodes]) == v1_expected_nodes
    assert sorted([edge for edge in v1_deps.edges(data=True)]) == v1_expected_edges
