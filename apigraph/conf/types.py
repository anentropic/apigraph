from enum import Enum
from typing import no_type_check, Optional

from pydantic import BaseSettings


class CoerceEnumSettings(BaseSettings):
    """
    Allow to set value via Enum member name rather than enum instance to fields
    having an Enum type, in conjunction with Config.validate_assignment = True
    """
    @no_type_check
    def __setattr__(self, name, value):
        field = self.__fields__[name]
        if (
            issubclass(field.type_, Enum)
            and not isinstance(value, Enum)
        ):
            value = field.type_[value]
        return super().__setattr__(name, value)


class Settings(CoerceEnumSettings):
    class Config:
        validate_assignment = True
        env_prefix = 'APIGRAPH_'

    CACHE_DIR: Optional[str] = ".apigraph"  # uses tmp if None, relative to exec dir
    CACHE_EXPIRE: Optional[float] = None

    BACKLINKS_ATTR: str = "x-apigraph-backlinks"
    LINK_CHAIN_ID_ATTR: str = "x-apigraph-chain-id"
    LINK_REQUEST_BODY_PARAMS_ATTR: str = "x-requestBodyParameters"
