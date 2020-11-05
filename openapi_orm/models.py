import re
from enum import Enum
from functools import singledispatch
from typing import Any, Dict, List, Optional, Union

from pydantic import (
    BaseModel as PydanticBaseModel,
    EmailStr,
    Field,
    HttpUrl,
    PositiveInt,
    conint,
    constr,
    root_validator,
    validator,
)

# TODO: replace all Any with Optional[object] ?

# TODO: support extensions


"""
https://github.com/samuelcolvin/pydantic/issues/1223

class Model(base):
    a: Optional[int]  # this field is required but can be given None (to be CHANGED in v2)
    b: Optional[int] = None  # field is not required, can be given None or an int (current behaviour)
    c: int = None  # this field isn't required but must be an int if it is provided (current behaviour)
"""


@singledispatch
def _make_hashable(val):
    return val


@_make_hashable.register(dict)
def _(val):
    return tuple((_make_hashable(key), _make_hashable(val)) for key, val in val.items())


@_make_hashable.register(list)
def _(val):
    return tuple(_make_hashable(v) for v in val)


@_make_hashable.register(set)
def _(val):
    return frozenset(val)


@_make_hashable.register(PydanticBaseModel)
def _(val):
    return tuple((name, _make_hashable(getattr(val, name))) for name in val.__fields__)


def check_unique(val: List[Any]):
    seen = set()
    for item in val:
        key = _make_hashable(item)
        if key in seen:
            raise ValueError("values in list must be unique")
        seen.add(key)
    return val


class BaseModel(PydanticBaseModel):
    class Config:
        use_enum_values = True
        allow_mutation = False
        # TODO: auto CamelCase aliasing?


class Extensible:
    """
    Mark a model as allowing user-defined extensions, as per Open API spec

    (in Open API 3.0, any extension field names MUST be prefixed with `x-`
    ...apparently in Open API 3.1 this requirement will be removed)

    TODO: can we 'register' an extension model that delegates at runtime?
    or we should make all these models abstract and have a factory that
    constructs concrete OpenAPI3Document class with extensions baked in?
    """

    class Config:
        extra = "allow"


class SimpleHashable(PydanticBaseModel):
    def __hash__(self):
        return hash(_make_hashable(self))


class Contact(Extensible, BaseModel):
    name: Optional[str]
    url: HttpUrl
    email: EmailStr


class License(Extensible, BaseModel):
    name: str
    url: Optional[HttpUrl]


class Info(Extensible, BaseModel):
    title: str
    description: str = ""
    termsOfService: Optional[str]
    contact: Optional[Contact]
    license: Optional[License]
    version: str


class ServerVariable(Extensible, BaseModel):
    enum: Optional[List[str]]
    default: str
    description: str = ""

    _check_enum = validator("enum", allow_reuse=True)(check_unique)


class Server(Extensible, BaseModel):
    url: str  # NO VALIDATION: MAY be relative, MAY have { } for var substitutions
    description: str = ""
    variables: Optional[Dict[str, ServerVariable]]


class ExternalDocumentation(Extensible, BaseModel):
    description: str = ""
    url: HttpUrl


class Discriminator(BaseModel):
    propertyName: str
    mapping: Optional[Dict[str, str]]


class XMLObj(Extensible, BaseModel):
    name: Optional[str]
    namespace: Optional[HttpUrl]
    prefix: Optional[str]
    attribute: bool = False
    wrapped: bool = False  # takes effect only when defined alongside type being array (outside the items)


# `Reference` must come first!
# (pydantic tries to instantiate members of Union type from L-R
# and takes the first oen that succeeds)
SchemaOrRef = Union["Reference", "Schema"]


class Schema(Extensible, BaseModel):
    """
    This class is a combination of JSON Schema rules:
    https://tools.ietf.org/html/draft-wright-json-schema-validation-00

    With some overrides and extra fields as defined by Open API here:
    https://github.com/OAI/OpenAPI-Specification/blob/master/versions/3.0.2.md#schemaObject
    """

    class Config:
        # hopefully this allows these fields to remain unset?
        fields = {
            "type_": {"alias": "type"},
            "not_": {"alias": "not"},
            "format_": {"alias": "format"},
        }

    title: Optional[str]
    multipleOf: Optional[PositiveInt]
    maximum: Optional[float]
    exclusiveMaximum: bool = False
    minimum: Optional[float]
    exclusiveMinimum: bool = False
    maxLength: Optional[PositiveInt]
    minLength: Optional[conint(ge=0)]
    pattern: Optional[str]
    maxItems: Optional[conint(ge=0)]
    minItems: Optional[conint(ge=0)]
    uniqueItems: bool = False
    maxProperties: Optional[conint(ge=0)]
    minProperties: Optional[conint(ge=0)]
    required: Optional[List[str]]
    enum: Optional[List[Any]]

    type_: Optional[str]
    allOf: Optional[List[SchemaOrRef]]
    oneOf: Optional[List[SchemaOrRef]]
    anyOf: Optional[List[SchemaOrRef]]
    not_: Optional[List[SchemaOrRef]]
    items: Optional[SchemaOrRef]
    properties: Optional[Dict[str, Union["PropertySchema", "Reference"]]]
    additionalProperties: Union[bool, SchemaOrRef] = True
    description: str = ""
    format_: Optional[str]
    default: Any

    nullable: bool = False
    discriminator: Optional[Discriminator]
    externalDocs: Optional[ExternalDocumentation]
    example: Any
    deprecated: bool = False

    _check_uniques = validator("required", "enum", allow_reuse=True)(check_unique)

    @validator("required")
    def check_required(cls, v):
        assert len(v) > 0, "`required` must be non-empty if present"
        return v

    @validator("enum")
    def check_enum(cls, v):
        assert len(v) > 0, "`enum` must be non-empty if present"
        return v

    @root_validator
    def check_items(cls, values):
        if values.get("type") == "array":
            assert values.get("items"), "`items` must be present when `type='array'`"
        return values

    @root_validator
    def check_discriminator(cls, values):
        # The discriminator object is legal only when using one of the composite keywords oneOf, anyOf, allOf.
        if not any(key in values for key in {"oneOf", "anyOf", "allOf"}):
            raise ValueError(
                "`discriminator` is legal only when using one of the composite keywords `oneOf`, `anyOf`, `allOf`."
            )
        return values


class PropertySchema(Schema):
    readOnly: bool = False
    writeOnly: bool = False
    xml: Optional[XMLObj]


class Reference(BaseModel):
    ref: str = Field(..., alias="$ref")


class Example(Extensible, BaseModel):
    summary: Optional[str]
    description: str = ""
    value: Any
    externalValue: Optional[HttpUrl]

    @root_validator
    def check_value(cls, values):
        if values.get("value") and values.get("externalValue"):
            raise ValueError("`value` and `externalValue` are mutually-exclusive")
        return values


class Encoding(Extensible, BaseModel):
    contentType: Optional[str]
    headers: Optional[Dict[str, Union[Reference, "Header"]]]
    style: Optional[str]
    explode: bool = False
    allowReserved: bool = False

    @root_validator
    def default_explode(cls, values):
        if "explode" not in values and values.get("style") is Style.FORM:
            values["explode"] = True
        return values


class MediaType(Extensible, BaseModel):
    class Config:
        fields = {"schema_": {"alias": "schema"}}

    schema_: Optional[SchemaOrRef]
    example: Any
    examples: Optional[Dict[str, Union[Reference, Example]]]
    encoding: Optional[Dict[str, Encoding]]

    @root_validator
    def check_examples(cls, values):
        """
        In OpenAPI v3.1 the Schema Object example keyword is deprecated, so you
        should start using examples in your API description documents.
        """
        if values.get("example") and values.get("examples"):
            raise ValueError("`example` and `examples` are mutually-exclusive")
        return values


class In(str, Enum):
    QUERY = "query"
    HEADER = "header"
    PATH = "path"
    COOKIE = "cookie"


class Style(str, Enum):
    MATRIX = "matrix"
    LABEL = "label"
    FORM = "form"
    SIMPLE = "simple"
    SPACE_DELIMITED = "spaceDelimited"
    PIPE_DELIMITED = "pipeDelimited"
    DEEP_OBJECT = "deepObject"


IN_STYLES_MAP = {
    In.QUERY: {
        Style.FORM,
        Style.SPACE_DELIMITED,
        Style.PIPE_DELIMITED,
        Style.DEEP_OBJECT,
    },
    In.HEADER: {Style.SIMPLE},
    In.PATH: {Style.MATRIX, Style.LABEL, Style.SIMPLE},
    In.COOKIE: {Style.FORM},
}

IN_STYLE_DEFAULTS = {
    In.QUERY: Style.FORM,
    In.HEADER: Style.SIMPLE,
    In.PATH: Style.SIMPLE,
    In.COOKIE: Style.FORM,
}


class Header(BaseModel):
    class Config:
        fields = {"schema_": {"alias": "schema"}}

    description: str = ""
    required: bool = False
    deprecated: bool = False
    allowEmptyValue: bool = False

    style: Optional[Style]
    explode: bool = False
    allowReserved: bool = False
    schema_: Optional[SchemaOrRef]
    example: Any
    examples: Dict[str, Union[Reference, Example]] = Field({})

    content: Dict[str, MediaType] = Field({})

    @root_validator
    def check_allow_empty_value(cls, values):
        if values.get("allowEmptyValue"):
            raise ValueError("allowEmptyValue=True is not valid for Header")
        return values

    @root_validator
    def check_style_and_explode(cls, values):
        style = values.get("style")
        if style:
            assert style in IN_STYLES_MAP[In.HEADER]
        else:
            values["style"] = IN_STYLE_DEFAULTS[In.HEADER]
        return values

    @root_validator
    def check_allow_reserved(cls, values):
        if values.get("allowReserved"):
            raise ValueError("allowReserved=True is not valid for Header")
        return values

    @root_validator
    def check_examples(cls, values):
        """
        In OpenAPI v3.1 the Schema Object example keyword is deprecated, so you
        should start using examples in your API description documents.
        """
        if values.get("example") and values.get("examples"):
            raise ValueError("`example` and `examples` are mutually-exclusive")
        return values

    @validator("content")
    def check_content(cls, v):
        assert len(v) == 1
        return v


class Parameter(Extensible, BaseModel):
    """
    A unique parameter is defined by a combination of `name` and location (`in_`)
    """

    class Config:
        fields = {"schema_": {"alias": "schema"}}

    name: str
    in_: In = Field(..., alias="in")
    description: str = ""
    required: bool = False
    deprecated: bool = False
    allowEmptyValue: bool = False

    style: Optional[Style]
    explode: bool = False
    allowReserved: bool = False
    schema_: Optional[SchemaOrRef]
    example: Any
    examples: Dict[str, Union[Reference, Example]] = Field({})

    content: Dict[str, MediaType] = Field({})

    @root_validator
    def check_required(cls, values):
        if values["in_"] is In.PATH:
            assert values["required"] is True
        return values

    @root_validator
    def check_allow_empty_value(cls, values):
        if values.get("allowEmptyValue") and values["in_"] is not In.QUERY:
            raise ValueError("allowEmptyValue=True is only valid for in='query'")
        return values

    @root_validator
    def check_style_and_explode(cls, values):
        style = values.get("style")
        if style:
            assert style in IN_STYLES_MAP[values["in_"]]
        else:
            values["style"] = IN_STYLE_DEFAULTS[values["in_"]]

        if "explode" not in values and values.get("style") is Style.FORM:
            values["explode"] = True

        return values

    @root_validator
    def check_allow_reserved(cls, values):
        if values.get("allowReserved") and values["in_"] is not In.QUERY:
            raise ValueError("allowReserved=True is only valid for in='query'")
        return values

    @root_validator
    def check_examples(cls, values):
        """
        In OpenAPI v3.1 the Schema Object example keyword is deprecated, so you
        should start using examples in your API description documents.
        """
        if values.get("example") and values.get("examples"):
            raise ValueError("`example` and `examples` are mutually-exclusive")
        return values

    @validator("content")
    def check_content(cls, v):
        assert len(v) == 1
        return v


@_make_hashable.register(Parameter)
def _(val):
    return (val.name, val.in_)


class RequestBody(Extensible, BaseModel):
    description: str = ""
    content: Dict[str, MediaType]
    required: bool = False


def check_request_body(cls, values):
    requestBody = values.get("requestBody")
    requestBodyParameters = values.get("requestBodyParameters")
    if requestBody is not None and requestBodyParameters:
        raise ValueError(
            "`requestBody`, and `requestBodyParameters` are mutually-exclusive"
        )
    return values


class Link(Extensible, BaseModel):
    operationRef: Optional[str] = None
    operationId: Optional[str] = None
    parameters: Dict[str, Any] = Field({})
    requestBody: Optional[str] = None
    description: str = ""
    server: Optional[Server] = None

    chainId: Optional[str] = Field(None, alias="x-apigraph-chainId")
    requestBodyParameters: Dict[str, str] = Field(
        {}, alias="x-apigraph-requestBodyParameters"
    )

    check_request_body_ = root_validator(check_request_body, allow_reuse=True)

    @root_validator
    def check_operation_identifier(cls, values):
        operationRef = values.get("operationRef")
        operationId = values.get("operationId")
        if operationRef and operationId:
            raise ValueError("`operationRef` and `operationId` are mutually-exclusive")
        if not any((operationRef, operationId)):
            raise ValueError("One-of  `operationRef` or `operationId` are required")
        return values


class Backlink(Extensible, BaseModel):
    responseRef: Optional[str] = None
    operationRef: Optional[str] = None
    operationId: Optional[str] = None
    response: Optional[str] = None

    chainId: Optional[str] = None

    parameters: Dict[str, Any] = Field({})
    requestBody: Optional[str] = None
    requestBodyParameters: Dict[str, str] = Field({})

    description: str = ""
    server: Optional[Server] = None

    check_request_body_ = root_validator(check_request_body, allow_reuse=True)

    @root_validator
    def check_response_identifier(cls, values):
        responseRef = values.get("responseRef")
        operationRef = values.get("operationRef")
        operationId = values.get("operationId")
        response = values.get("response")
        if (
            responseRef
            and any((operationRef, operationId, response))
            or operationRef
            and any((responseRef, operationId))
            or operationId
            and any((responseRef, operationRef))
        ):
            raise ValueError(
                "`responseRef`, `operationRef`, `operationId` and `response` are mutually-exclusive"
            )
        if (operationId or operationRef) and not response:
            raise ValueError(
                "`response` is required when `operationRef` or `operationId` are specified"
            )
        if response and not (operationId or operationRef):
            raise ValueError(
                "`operationRef` or `operationId` are required when `response` is specified"
            )
        if not any((responseRef, operationRef, operationId)):
            raise ValueError(
                "One-of `responseRef`, `operationRef` or `operationId` are required"
            )
        return values


class Response(Extensible, BaseModel):
    description: str = ""
    headers: Dict[str, Union[Reference, Header]] = Field({})
    content: Dict[str, MediaType] = Field({})
    links: Dict[str, Union[Reference, Link]] = Field({})


HTTP_STATUS_RE = re.compile(r"^[1-5][X0-9]{2}|default$")


Responses = Dict[str, Union[Reference, Response]]
# TODO: Extensible


def check_responses(val):
    for key in val:
        if not HTTP_STATUS_RE.match(key):
            raise ValueError(f"{key} is not a valid Response key")
    return val


Callback = Dict[str, "PathItem"]
# TODO: Extensible


SecurityRequirement = Dict[str, List[str]]
# Each key MUST correspond to a named security scheme which is declared in the
# Security Schemes under the Components Object. (TODO: validation)
# If the requirement contains multiple schemes then ALL are required for the
# operation.
# If the security scheme is of type "oauth2" or "openIdConnect", then the value
# is a list of scope names which are required for the operation. For other
# security scheme types, the array MUST be empty.
# OpenAPI spec does not mandate that the dict must not be empty, but it seems
# useless to define such a requirement.


class Operation(Extensible, BaseModel):
    tags: List[str] = Field([])
    summary: str = ""
    description: str = ""
    externalDocs: Optional[ExternalDocumentation] = None
    operationId: Optional[str] = None
    parameters: List[Union[Reference, Parameter]] = Field(
        []
    )  # may override matching PathItem param, but not remove
    requestBody: Optional[Union[Reference, RequestBody]] = None
    responses: Responses
    callbacks: Dict[str, Union[Reference, Callback]] = Field({})
    deprecated: bool = False
    security: Optional[List[SecurityRequirement]] = None  # None means "no override"
    servers: Optional[List[Server]] = None  # None means "no override"

    backlinks: Dict[str, Union[Reference, Backlink]] = Field(
        {}, alias="x-apigraph-backlinks"
    )

    _check_parameters = validator("parameters", allow_reuse=True)(check_unique)
    _check_responses = validator("responses", allow_reuse=True)(check_responses)


class PathItem(Extensible, BaseModel):
    class Config:
        fields = {"ref": {"alias": "$ref"}}

    ref: Optional[str] = None
    summary: str = ""
    description: str = ""

    get: Optional[Operation]
    put: Optional[Operation]
    post: Optional[Operation]
    delete: Optional[Operation]
    options: Optional[Operation]
    head: Optional[Operation]
    patch: Optional[Operation]
    trace: Optional[Operation]

    servers: Optional[List[Server]] = None  # None means "no override"
    parameters: List[Union[Reference, Parameter]] = Field(
        []
    )  # added to individual operation params

    _check_parameters = validator("parameters", allow_reuse=True)(check_unique)


Paths = Dict[str, PathItem]
# TODO: Extensible


class _BaseOAuthFlow(Extensible, SimpleHashable, BaseModel):
    refreshUrl: Optional[HttpUrl]
    scopes: Dict[str, str]


class ImplicitOAuthFlow(_BaseOAuthFlow):
    authorizationUrl: HttpUrl


class AuthorizationCodeOAuthFlow(_BaseOAuthFlow):
    authorizationUrl: HttpUrl
    tokenUrl: HttpUrl


class PasswordOAuthFlow(_BaseOAuthFlow):
    tokenUrl: HttpUrl


class ClientCredentialsOAuthFlow(_BaseOAuthFlow):
    tokenUrl: HttpUrl


OAuthFlow = Union[
    ImplicitOAuthFlow,
    AuthorizationCodeOAuthFlow,
    PasswordOAuthFlow,
    ClientCredentialsOAuthFlow,
]


class OAuthFlows(Extensible, SimpleHashable, BaseModel):
    implicit: Optional[OAuthFlow]
    password: Optional[OAuthFlow]
    clientCredentials: Optional[OAuthFlow]
    authorizationCode: Optional[OAuthFlow]

    # TODO: require oneOf?


class Type_(str, Enum):
    API_KEY = "apiKey"
    HTTP = "http"
    OAUTH2 = "oauth2"
    OPENID_CONNECT = "openIdConnect"


class _BaseSecurityScheme(Extensible, SimpleHashable, BaseModel):
    type_: Type_ = Field(..., alias="type")
    description: str = ""


class HTTPAuthScheme(str, Enum):
    """
    "The name of the HTTP Authorization scheme to be used in the Authorization
    header as defined in RFC7235."
    https://tools.ietf.org/html/rfc7235#section-5.1
    ...points to:
    https://www.iana.org/assignments/http-authschemes/http-authschemes.xhtml

    NOTE: the IANA docs gives these schemes mostly in title case, the OpenAPI
    docs give an example value "basic" though... here we will match only
    all lower-case.
    """

    BASIC = "basic"
    BEARER = "bearer"
    DIGEST = "digest"
    HOBA = "hoba"
    MUTUAL = "mutual"
    NEGOTIATE = "negotiate"
    OAUTH = "oauth"
    SCRAM_SHA_1 = "scram-sha-1"
    SCRAM_SHA_256 = "scram-sha-256"
    VAPID = "vapid"


class APIKeySecurityScheme(_BaseSecurityScheme):
    name: str
    in_: In = Field(..., alias="in")

    @validator("in_")
    def check_in(cls, v):
        if v not in {In.QUERY, In.HEADER, In.COOKIE}:
            raise ValueError(f"{v} is not a valid `in` value")
        return v


class HTTPSecurityScheme(_BaseSecurityScheme):
    scheme: HTTPAuthScheme
    bearerFormat: Optional[str] = None


class OAuth2SecurityScheme(_BaseSecurityScheme):
    flows: OAuthFlows


class OpenIDConnectSecurityScheme(_BaseSecurityScheme):
    openIdConnectUrl: HttpUrl


SecurityScheme = Union[
    APIKeySecurityScheme,
    HTTPSecurityScheme,
    OAuth2SecurityScheme,
    OpenIDConnectSecurityScheme,
]


class Components(Extensible, BaseModel):
    r"""
    TODO:
    All the fixed fields declared below are objects that MUST use keys that
    match the regular expression: ^[a-zA-Z0-9\.\-_]+$
    """
    schemas: Dict[str, SchemaOrRef] = Field({})
    responses: Dict[str, Union[Reference, Response]] = Field({})
    parameters: Dict[str, Union[Reference, Parameter]] = Field({})
    examples: Dict[str, Union[Reference, Example]] = Field({})
    requestBodies: Dict[str, Union[Reference, RequestBody]] = Field({})
    headers: Dict[str, Union[Reference, Header]] = Field({})
    securitySchemes: Dict[str, Union[Reference, SecurityScheme]] = Field({})
    links: Dict[str, Union[Reference, Link]] = Field({})
    callbacks: Dict[str, Union[Reference, Callback]] = Field({})

    backlinks: Dict[str, Union[Reference, Link]] = Field(
        {}, alias="x-apigraph-backlinks"
    )


class Tag(Extensible, BaseModel):
    name: str
    description: str = ""
    externalDocs: Optional[ExternalDocumentation]


VersionStr = constr(regex=r"\d+\.\d+\.\d+")


class OpenAPI3Document(Extensible, BaseModel):
    """
    See:
    https://github.com/OAI/OpenAPI-Specification/blob/master/versions/3.0.2.md
    """

    openapi: VersionStr = "3.0.2"
    info: Info
    servers: List[Server] = Field([Server(url="/")])
    paths: Paths
    components: Optional[Components] = None
    security: List[SecurityRequirement] = Field([])
    tags: List[Tag] = Field([])
    externalDocs: Optional[ExternalDocumentation] = None
