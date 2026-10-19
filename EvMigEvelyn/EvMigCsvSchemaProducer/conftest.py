"""pytest runs this before the tests. The wheel keeps two things per process (the SDK and the configuration), so every
test starts without them, as evmig-nss/tests/conftest.py does, and gets a fresh in-memory Data Fabric."""
from types import SimpleNamespace

import pytest

from evmig_nss.core import configuration, sdk
from evmig_nss.testing import FakeEntities


@pytest.fixture(autouse=True)
def clean_process_state(monkeypatch):
    monkeypatch.delenv(sdk.LOCAL_BUCKET_DIR_ENV, raising=False)
    monkeypatch.delenv(sdk.LOCAL_DATAFABRIC_FILE_ENV, raising=False)
    monkeypatch.delenv("UIPATH_FOLDER_KEY", raising=False)
    configuration.reset_configuration_cache()
    sdk.set_sdk(None)
    yield
    configuration.reset_configuration_cache()
    sdk.set_sdk(None)


@pytest.fixture
def entities():
    """The fake Data Fabric `main` writes to (a test reads its `.rows` and `.calls`). This function uses no bucket."""
    fake = FakeEntities()
    sdk.set_sdk(SimpleNamespace(entities=fake))
    return fake
