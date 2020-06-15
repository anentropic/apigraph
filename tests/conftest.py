import inject
import pytest


@pytest.fixture(scope="session", autouse=True)
@inject.params(_dc_cache="cache")
def clear_cache(_dc_cache=None):
    _dc_cache.clear()
