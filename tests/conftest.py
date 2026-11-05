import pytest

from resource_platform.capture import Store
from resource_platform.catalog import Catalog
from resource_platform.sample import capture_sample


@pytest.fixture(scope="session")
def home(tmp_path_factory):
    home = tmp_path_factory.mktemp("platform")
    capture_sample(Store(home / "store"), home / "sample")
    return home


@pytest.fixture(scope="session")
def catalog(home):
    cat = Catalog.open(Store(home / "store"))
    cat.build()
    return cat
