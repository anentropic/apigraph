from enum import auto, Enum
from typing import Any, Dict, NamedTuple, Union
from typing_extensions import Final, TypedDict


class NotSet(Enum):
    NOT_SET = auto()


NOT_SET: Final = NotSet.NOT_SET


class LinkType(str, Enum):
    LINK = "link"
    BACKLINK = "backlink"


class NodeKey(NamedTuple):
    doc_uri: str
    path: str
    method: str


JSONPointerStr = str
RuntimeExprStr = str

BacklinkParameter = TypedDict(
    "BacklinkParameter",
    {
        "from": JSONPointerStr,
        "select": RuntimeExprStr,
    }
)

LinkParameters = Dict[str, RuntimeExprStr]
RequestBodyParams = Dict[JSONPointerStr, RuntimeExprStr]
BacklinkRequestBodyParams = Dict[JSONPointerStr, BacklinkParameter]


class EdgeDetail(NamedTuple):
    link_type: LinkType
    name: str  # NOTE: for links `name` identifies the target, for backlinks the source
    description: str
    parameters: LinkParameters
    requestBody: Union[NotSet, RuntimeExprStr, Any]
    requestBodyParameters: RequestBodyParams
