# Own test of core/usecase.py (DEC-5).
import tomllib
from pathlib import Path

from evmig_nss.core import usecase


def test_the_dw_version_is_the_installed_library_version_and_the_model_version_is_evelyns():
    declared = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    assert usecase.dw_version() == declared  # no literal here: a version bump must not need a test edit
    assert usecase.MODEL_VERSION == "nss-classification-model-v5.3.0"
