import pytest

from resource_platform.capture import Store
from resource_platform.catalog import Catalog, load_datasets
from resource_platform.sample import generate


@pytest.fixture(scope="session")
def home(tmp_path_factory):
    home = tmp_path_factory.mktemp("platform")
    store = Store(home / "store")
    datasets = load_datasets()
    for ds_id, path in generate(home / "sample").items():
        store.capture(path, ds_id, f"synthetic://{path.name}", datasets[ds_id].publisher,
                      synthetic=True)
    return home


@pytest.fixture(scope="session")
def catalog(home):
    cat = Catalog.open(Store(home / "store"))
    cat.build()
    return cat
