from pathlib import Path
from typing import Union
from urllib import parse as urlparse

import inject
from jsonref import JsonRef
from openapi_orm.loader import JSONOrYAMLRefLoader
from openapi_orm.models import OpenAPI3Document


@inject.params(loader='jsonref_loader')
def load_doc(
    location: Union[str, Path],
    loader=None,
    load_on_repr: bool = False,
) -> OpenAPI3Document:
    """
    Load OpenAPI spec (as JSON or YAML) and use jsonref to replace
    all `$ref` elements with lazy proxies
    """
    if isinstance(location, Path):
        location = f"file://{location}"
    raw_doc = JsonRef.replace_refs(
        loader(location),
        base_uri=location,
        loader=loader,
        jsonschema=False,
        load_on_repr=load_on_repr,
    )
    return OpenAPI3Document.parse_obj(raw_doc)


class DiskCachedJSONOrYAMLRefLoader(JSONOrYAMLRefLoader):
    """
    Replacement for `jsonref.JsonLoader`

    - uses diskcache as its `store`
    - can load both json and yaml docs
    """
    @inject.params(_dc_cache='cache')
    def __init__(self, store=(), cache_results: bool = True, _dc_cache=None):
        self.store = _dc_cache
        self.cache_results = cache_results

    @inject.params(_dc_settings='settings')
    def __call__(self, uri: str, _dc_settings, **kwargs):
        """
        Return the loaded JSON referred to by `uri`
        :param uri: The URI of the JSON document to load
        :param kwargs: Keyword arguments passed to :func:`json.loads`
        """
        uri = urlparse.urlsplit(uri).geturl()  # normalize
        if uri in self.store:
            return self.store[uri]
        else:
            result = self.get_remote_json(uri, **kwargs)
            if self.cache_results:
                self.store.set(
                    key=uri, value=result, expire=_dc_settings.CACHE_EXPIRE
                )
            return result
