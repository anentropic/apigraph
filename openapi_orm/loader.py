import json
from pathlib import Path
from typing import Union
from urllib import parse as urlparse
from urllib.request import urlopen

import httpx
import yaml
from jsonref import JsonLoader, JsonRef


class JSONOrYAMLRefLoader(JsonLoader):
    """
    Replacement for `jsonref.JsonLoader`

    Can load both json and yaml docs, allowing us to resolve $ref in
    OpenAPI yaml docs.
    """

    def get_remote_json(self, uri: str, **kwargs):
        scheme = urlparse.urlsplit(uri).scheme

        if scheme in ("http", "https"):
            response = httpx.get(uri)
            response.raise_for_status()
            data = response.content
        else:
            # Otherwise, pass off to urllib and assume utf-8
            data = urlopen(uri).read().decode("utf-8")

        try:
            doc = json.loads(data)
        except json.JSONDecodeError:
            doc = yaml.safe_load(data)

        return doc


def load_doc(
    location: Union[str, Path],
    loader_cls=JSONOrYAMLRefLoader,
    load_on_repr: bool = False,
):
    """
    Load OpenAPI spec (as JSON or YAML) and use jsonref to replace
    all `$ref` elements with lazy proxies.
    """
    if isinstance(location, Path):
        location = f"file://{location}"
    return JsonRef.replace_refs(
        loader_cls()(location),
        base_uri=location,
        loader=loader_cls,
        jsonschema=False,
        load_on_repr=load_on_repr,
    )
