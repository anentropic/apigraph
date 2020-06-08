from pathlib import Path

from apigraph import __version__
from apigraph.graph import APIGraph
from apigraph.types import EdgeKey, LinkType, NodeKey


def fixture_uri(rel_path: str):
    path = Path(__file__).parent / Path("fixtures") / Path(rel_path)
    return f"file://{path}"


def test_links():
    doc_uri = fixture_uri("links.yaml")

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri}

    expected_nodes = (
        NodeKey(doc_uri, "/2.0/users/{username}", "get"),
        NodeKey(doc_uri, "/2.0/repositories/{username}", "get"),
        NodeKey(doc_uri, "/2.0/repositories/{username}/{slug}", "get"),
        NodeKey(doc_uri, "/2.0/repositories/{username}/{slug}/pullrequests", "get"),
        NodeKey(doc_uri, "/2.0/repositories/{username}/{slug}/pullrequests/{pid}", "get"),
        NodeKey(doc_uri, "/2.0/repositories/{username}/{slug}/pullrequests/{pid}/merge", "post"),
    )
    expected_edges = (
        (expected_nodes[0], expected_nodes[1], EdgeKey(LinkType.LINK, "200", None, "userRepositories")),
        (expected_nodes[1], expected_nodes[2], EdgeKey(LinkType.LINK, "200", None, "userRepository")),
        (expected_nodes[2], expected_nodes[3], EdgeKey(LinkType.LINK, "200", None, "repositoryPullRequests")),
        (expected_nodes[4], expected_nodes[5], EdgeKey(LinkType.LINK, "200", None, "pullRequestMerge")),
    )
    assert tuple(node for node in apigraph.graph.nodes) == expected_nodes
    assert tuple(edge for edge in apigraph.graph.edges) == expected_edges


def test_links_via_within_doc_ref():
    assert __version__ == '0.1.0'


def test_links_via_other_doc_ref():
    assert __version__ == '0.1.0'


def test_backlinks():
    assert __version__ == '0.1.0'


def test_backlinks_via_within_doc_ref():
    assert __version__ == '0.1.0'


def test_backlinks_via_other_doc_ref():
    assert __version__ == '0.1.0'


def test_auth_local_only():
    assert __version__ == '0.1.0'


def test_global_only():
    assert __version__ == '0.1.0'


def test_local_override_with_different():
    assert __version__ == '0.1.0'


def test_local_override_with_none():
    assert __version__ == '0.1.0'


def test_local_override_narrowing():
    assert __version__ == '0.1.0'
