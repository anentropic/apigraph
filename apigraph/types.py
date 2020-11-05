from enum import Enum, auto
from typing import (
    Any,
    Dict,
    Final,
    FrozenSet,
    NamedTuple,
    Optional,
    Set,
    Tuple,
    TypedDict,
    Union,
)

from openapi_orm.models import In, Parameter, RequestBody, SecurityScheme


class NotSet(Enum):
    NOT_SET = auto()


NOT_SET: Final[NotSet] = NotSet.NOT_SET


class HttpMethod(str, Enum):
    GET = "get"
    PUT = "put"
    POST = "post"
    DELETE = "delete"
    OPTIONS = "options"
    HEAD = "head"
    PATCH = "patch"
    TRACE = "trace"


# {<operation id>: (<path>, <method>)}
OperationIdPathIndex = Dict[str, Tuple[str, HttpMethod]]


class LinkType(Enum):
    LINK = auto()
    BACKLINK = auto()


class NodeKey(NamedTuple):
    doc_uri: str
    path: str
    method: HttpMethod


class EdgeKey(NamedTuple):
    chain_id: Optional[str]
    response_id: str


JSONPointerStr = str
RuntimeExprStr = str

BacklinkParameter = TypedDict(
    "BacklinkParameter", {"from": JSONPointerStr, "select": RuntimeExprStr}
)

LinkParameters = Dict[str, RuntimeExprStr]
RequestBodyParams = Dict[JSONPointerStr, RuntimeExprStr]
BacklinkParameters = Dict[str, BacklinkParameter]
BacklinkRequestBodyParams = Dict[JSONPointerStr, BacklinkParameter]


class LinkDetail(NamedTuple):
    """
    Collates and normalises the relevant Link/Backlink details
    """

    link_type: LinkType
    name: str  # name of the Link/Backlink object

    description: str

    parameters: LinkParameters
    requestBody: Union[NotSet, RuntimeExprStr, Any]
    requestBodyParameters: RequestBodyParams


class ParamKey(NamedTuple):
    name: str
    location: In


class OperationDetail(NamedTuple):
    """
    Collates and normalises the relevant Operation details
    """

    # server: str  # not sure what to do about this yet
    path: str
    method: HttpMethod

    summary: str
    description: str

    parameters: Dict[
        ParamKey, Parameter
    ]  # all refs resolved and parent PathItem params merged
    requestBody: Optional[RequestBody]  # not all http methods support body
    security_schemes: Set[
        FrozenSet[SecurityScheme]
    ]  # resolved for operation vs doc components
