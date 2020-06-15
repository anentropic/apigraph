import inject
from diskcache import Cache

from apigraph.conf import _settings
from apigraph.loader import DiskCachedJSONOrYAMLRefLoader

__version__ = "0.1.0"


def configuration_factory(settings):
    def configure(binder):
        binder.bind("settings", settings)
        binder.bind_to_constructor("cache", lambda: Cache(directory=settings.CACHE_DIR))
        binder.bind_to_constructor(
            "jsonref_loader", lambda: DiskCachedJSONOrYAMLRefLoader()
        )

    return configure


inject.configure(configuration_factory(_settings))
