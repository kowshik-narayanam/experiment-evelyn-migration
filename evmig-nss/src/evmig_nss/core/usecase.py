"""The two build properties Evelyn stamps on every transaction (DEC-5).

Java: usecase.properties through NssProperties (JR:usecase.properties:3 version, :5 ml-model).
"""
from importlib.metadata import version

# E:pom.xml:21, the model Evelyn ships. No model runs in this port yet.
MODEL_VERSION = "nss-classification-model-v5.3.0"


def dw_version() -> str:
    """This library's version, as installed (the `version` of evmig-nss/pyproject.toml of the wheel)."""
    return version("evmig-nss")
