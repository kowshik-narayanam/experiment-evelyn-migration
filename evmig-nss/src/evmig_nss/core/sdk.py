"""The one place a function gets the UiPath SDK from, with the switch for a run without a tenant.

  get_sdk()   the SDK client, created on first use and then reused by the process.
              Normally `UiPath()` (it needs a login, so it is imported and created only here, never at import time:
              `uipath init` imports main.py without one).
              With env EVMIG_LOCAL_BUCKET_DIR set it is a local, SDK-shaped object instead (testing.local_sdk):
                .buckets   serves the files under that folder (keys = paths relative to it, like the bucket's keys),
                .entities  is the in-memory FakeEntities; with env EVMIG_LOCAL_DATAFABRIC_FILE also set, its rows are
                           loaded from that JSON file at start and saved to it after every write, so one function's
                           rows are visible to the next process and can be read after the run.
              No login and no network in that mode.
  set_sdk(x)  tests: use `x` (anything with .buckets and .entities) from now on; set_sdk(None) forgets it, so the
              next get_sdk() starts again from the environment.
"""
import logging
import os

logger = logging.getLogger(__name__)

LOCAL_BUCKET_DIR_ENV = "EVMIG_LOCAL_BUCKET_DIR"
LOCAL_DATAFABRIC_FILE_ENV = "EVMIG_LOCAL_DATAFABRIC_FILE"

_sdk = None


def get_sdk():
    global _sdk
    if _sdk is None:
        bucket_dir = os.environ.get(LOCAL_BUCKET_DIR_ENV)
        if bucket_dir:
            from evmig_nss.testing import local_sdk  # the fakes live in the wheel, loaded only for a local run

            datafabric_file = os.environ.get(LOCAL_DATAFABRIC_FILE_ENV) or None
            logger.info("Local run: bucket files from %s, Data Fabric rows in %s", bucket_dir, datafabric_file or "memory")
            _sdk = local_sdk(bucket_dir, datafabric_file)
        else:
            from uipath.platform import UiPath

            _sdk = UiPath()
    return _sdk


def set_sdk(sdk) -> None:
    global _sdk
    _sdk = sdk
