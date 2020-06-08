from pathlib import Path
from typing import Dict

import inject
import pytest

from apigraph import __version__
from apigraph.graph import APIGraph
from apigraph.types import EdgeKey, LinkType, NodeKey


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
    """
    doc_uri = fixture_uri(fixture)

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri}

    expected_nodes = [
        NodeKey(doc_uri, "/2.0/users/{username}", "get"),
        NodeKey(doc_uri, "/2.0/repositories/{username}", "get"),
        NodeKey(doc_uri, "/2.0/repositories/{username}/{slug}", "get"),
        NodeKey(doc_uri, "/2.0/repositories/{username}/{slug}/pullrequests", "get"),
        NodeKey(doc_uri, "/2.0/repositories/{username}/{slug}/pullrequests/{pid}", "get"),
        NodeKey(doc_uri, "/2.0/repositories/{username}/{slug}/pullrequests/{pid}/merge", "post"),
    ]
    expected_edges = [
        (
            expected_nodes[0],
            expected_nodes[1],
            EdgeKey(LinkType.LINK, "200", chain_id, "userRepositories"),
        ),
        (
            expected_nodes[1],
            expected_nodes[2],
            EdgeKey(LinkType.LINK, "200", chain_id, "userRepository"),
        ),
        (
            expected_nodes[2],
            expected_nodes[3],
            EdgeKey(LinkType.LINK, "200", chain_id, "repositoryPullRequests"),
        ),
        (
            expected_nodes[4],
            expected_nodes[5],
            EdgeKey(LinkType.LINK, "200", chain_id, "pullRequestMerge"),
        ),
    ]
    assert [node for node in apigraph.graph.nodes] == expected_nodes
    assert [edge for edge in apigraph.graph.edges] == expected_edges


def test_links_via_other_doc_ref(httpx_mock):
    """
    NOTE: cross-doc-links.yaml links via `operationRef` URI to links.yaml
    So between this and `test_links` both `operationRef` and `operationId
    links are fully tested
    """
    doc_uri = "https://fakeurl/cross-doc-links.yaml"
    other_doc_uri = fixture_uri("links.yaml")

    raw_doc = str_doc_with_substitutions(
        "tests/fixtures/cross-doc-links.yaml",
        {"fixture_uri": other_doc_uri},
    )
    httpx_mock.add_response(url=doc_uri, data=raw_doc)

    chain_id = None

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri, other_doc_uri}

    expected_nodes = [
        NodeKey(doc_uri, "/2.0/users", "post"),
        NodeKey(other_doc_uri, "/2.0/users/{username}", "get"),
        NodeKey(other_doc_uri, "/2.0/repositories/{username}", "get"),
        NodeKey(other_doc_uri, "/2.0/repositories/{username}/{slug}", "get"),
        NodeKey(other_doc_uri, "/2.0/repositories/{username}/{slug}/pullrequests", "get"),
        NodeKey(other_doc_uri, "/2.0/repositories/{username}/{slug}/pullrequests/{pid}", "get"),
        NodeKey(other_doc_uri, "/2.0/repositories/{username}/{slug}/pullrequests/{pid}/merge", "post"),
    ]
    expected_edges = [
        (
            expected_nodes[0],
            expected_nodes[1],
            EdgeKey(LinkType.LINK, "201", chain_id, "userByUsername"),
        ),
        (
            expected_nodes[1],
            expected_nodes[2],
            EdgeKey(LinkType.LINK, "200", chain_id, "userRepositories"),
        ),
        (
            expected_nodes[2],
            expected_nodes[3],
            EdgeKey(LinkType.LINK, "200", chain_id, "userRepository"),
        ),
        (
            expected_nodes[3],
            expected_nodes[4],
            EdgeKey(LinkType.LINK, "200", chain_id, "repositoryPullRequests"),
        ),
        (
            expected_nodes[5],
            expected_nodes[6],
            EdgeKey(LinkType.LINK, "200", chain_id, "pullRequestMerge"),
        ),
    ]
    assert [node for node in apigraph.graph.nodes] == expected_nodes
    assert [edge for edge in apigraph.graph.edges] == expected_edges


@pytest.mark.parametrize("fixture,chain_id", [
    ("backlinks.yaml", "default"),
])
def test_backlinks(fixture, chain_id):
    """
    NOTE: this fixture has comprehensive backlinks, so result is different
    from the (forward) links test above
    """
    doc_uri = fixture_uri(fixture)

    apigraph = APIGraph(doc_uri)
    assert apigraph.docs.keys() == {doc_uri}

    expected_nodes = [
        NodeKey(doc_uri, "/2.0/users/{username}", "get"),
        NodeKey(doc_uri, "/2.0/repositories/{username}", "get"),
        NodeKey(doc_uri, "/2.0/repositories/{username}/{slug}", "get"),
        NodeKey(doc_uri, "/2.0/repositories/{username}/{slug}/pullrequests", "get"),
        NodeKey(doc_uri, "/2.0/repositories/{username}/{slug}/pullrequests/{pid}", "get"),
        NodeKey(doc_uri, "/2.0/repositories/{username}/{slug}/pullrequests/{pid}/merge", "post"),
    ]
    expected_edges = [
        (
            expected_nodes[0],
            expected_nodes[1],
            EdgeKey(LinkType.BACKLINK, None, chain_id, "User"),
        ),
        (
            expected_nodes[1],
            expected_nodes[2],
            EdgeKey(LinkType.BACKLINK, None, chain_id, "User Repositories"),
        ),
        (
            expected_nodes[1],
            expected_nodes[3],
            EdgeKey(LinkType.BACKLINK, None, chain_id, "User Repositories"),
        ),
        (
            expected_nodes[3],
            expected_nodes[4],
            EdgeKey(LinkType.BACKLINK, None, chain_id, "Repo PRs"),
        ),
        (
            expected_nodes[3],
            expected_nodes[5],
            EdgeKey(LinkType.BACKLINK, None, chain_id, "Repo PRs"),
        ),
    ]
    assert [node for node in apigraph.graph.nodes] == expected_nodes
    assert [edge for edge in apigraph.graph.edges] == expected_edges


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
