import pytest

from apigraph.graph import APIGraph
from apigraph.types import EdgeDetail, LinkType, NodeKey

from .helpers import fixture_uri


@pytest.mark.parametrize("traverse_anonymous", [True, False])
def test_get_ancestors(traverse_anonymous):
    """
    The test fixture contains three dependency chains, two of which end
    at `createUser` and `createUserv1` respectively and both beginning at
    `getRepository`.

    The third chain is the 'anonymous' link (no chainId specified) which
    extends the "default" chain to begin at /invite.

    We request dependencies of `getRepositoriesByOwner`, which is not at the
    end of either chain (is followed by `getRepository`) and check that we
    only select up to the requested node and no further.
    """
    doc_uri = fixture_uri("dependencies.yaml")

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri}

    default_deps = apigraph.get_ancestors(
        node_key=NodeKey(doc_uri, "/2.0/repositories/{username}", "get"),
        chain_id="default",
        traverse_anonymous=traverse_anonymous,
    )
    v1_deps = apigraph.get_ancestors(
        node_key=NodeKey(doc_uri, "/2.0/repositories/{username}", "get"),
        chain_id="v1",
        traverse_anonymous=traverse_anonymous,
    )

    # dependencies from the "default" chain
    # NOTE: subsequent op `/2.0/repositories/{username}/{slug}` is not included
    # (nodes here manually sorted in url order for test case)
    default_expected_nodes = [
        NodeKey(doc_uri, "/2.0/repositories/{username}", "get"),
        NodeKey(doc_uri, "/2.0/users", "post"),
        NodeKey(doc_uri, "/2.0/users/{username}", "get"),
    ]
    # the "invite" predecessor has no chainId and is only included when
    # `traverse_anonymous=True`
    if traverse_anonymous:
        default_expected_nodes.append(NodeKey(doc_uri, "/invite", "post",))
    assert sorted([node for node in default_deps.nodes]) == default_expected_nodes

    # (edges here manually sorted in from-node??? order for test case)
    default_expected_edges = [
        (
            default_expected_nodes[1],
            default_expected_nodes[2],
            ("default", "201"),
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
            ("default", "200"),
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
    # the "invite" predecessor has no chainId and is only included when
    # `traverse_anonymous=True`
    if traverse_anonymous:
        default_expected_edges.append(
            (
                default_expected_nodes[3],
                default_expected_nodes[1],
                (None, "201"),
                {
                    "response_id": "201",
                    "chain_id": None,
                    "detail": EdgeDetail(
                        link_type=LinkType.BACKLINK,
                        name="Redeem Invite",
                        description="Create a user by redeeming an invite id+token",
                        parameters={"invite-id": "$response.body#/id"},
                        requestBody=None,
                        requestBodyParameters={
                            "/invite-token": "$response.body#/token"
                        },
                    ),
                },
            ),
        )
    assert (
        sorted([edge for edge in default_deps.edges(data=True, keys=True)])
        == default_expected_edges
    )

    # dependencies from the "v1" chain
    v1_expected_nodes = [
        NodeKey(doc_uri, "/1.0/users", "post"),
        NodeKey(doc_uri, "/1.0/users/{username}", "get"),
        NodeKey(doc_uri, "/2.0/repositories/{username}", "get"),
    ]
    v1_expected_edges = [
        (
            v1_expected_nodes[0],
            v1_expected_nodes[1],
            ("v1", "201"),
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
            ("v1", "200"),
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
    assert (
        sorted([edge for edge in v1_deps.edges(data=True, keys=True)])
        == v1_expected_edges
    )
