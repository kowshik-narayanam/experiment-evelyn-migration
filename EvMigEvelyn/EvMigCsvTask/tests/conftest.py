import pytest

from evmig_nss.core import configuration, sdk


@pytest.fixture(autouse=True)
def clean_process_state(monkeypatch):
    """The library keeps two things per process (the configuration and the SDK); every test starts without them.

    Same fixture as evmig-nss/tests/conftest.py. Without it, one test's configuration file would be served to the next.
    """
    monkeypatch.delenv(sdk.LOCAL_BUCKET_DIR_ENV, raising=False)
    monkeypatch.delenv(sdk.LOCAL_DATAFABRIC_FILE_ENV, raising=False)
    configuration.reset_configuration_cache()
    sdk.set_sdk(None)
    yield
    configuration.reset_configuration_cache()
    sdk.set_sdk(None)
