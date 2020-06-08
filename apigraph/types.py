from enum import Enum
from typing import NamedTuple, Optional


class LinkType(str, Enum):
    LINK = "link"
    BACKLINK = "backlink"


class NodeKey(NamedTuple):
    doc_uri: str
    path: str
    method: str


class EdgeKey(NamedTuple):
    link_type: LinkType
    response_id: Optional[str]  # (forward) Links only: "default" or "100".."599", identifies src of link
    chain_id: Optional[str]  # apigraph extension feature (to support declarest)
    name: str
