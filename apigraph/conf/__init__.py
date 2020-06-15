import toml

from apigraph.conf.types import Settings

try:
    _config = toml.load("apigraph.toml")
except FileNotFoundError:
    _config = {}


_settings = Settings(**{key.upper(): val for key, val in _config.items()})
