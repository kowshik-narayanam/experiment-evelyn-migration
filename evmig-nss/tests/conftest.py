import pytest

from evmig_nss.core import configuration, sdk


@pytest.fixture(autouse=True)
def clean_process_state(monkeypatch):
    """The library keeps two things per process (the configuration and the SDK); every test starts without them."""
    monkeypatch.delenv(sdk.LOCAL_BUCKET_DIR_ENV, raising=False)
    monkeypatch.delenv(sdk.LOCAL_DATAFABRIC_FILE_ENV, raising=False)
    monkeypatch.delenv("UIPATH_FOLDER_KEY", raising=False)
    configuration.reset_configuration_cache()
    sdk.set_sdk(None)
    yield
    configuration.reset_configuration_cache()
    sdk.set_sdk(None)
