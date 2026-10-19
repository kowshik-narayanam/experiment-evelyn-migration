"""The project's own files: the vendored wheel (DEC-2), the lock (DEC-9), the bucket binding (DEC-7) and the generated schema."""
import hashlib
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

from helpers import FUNCTION_DIR, REPO

LIBRARY_DIST = REPO / "evmig-nss" / "dist"


def one_wheel(folder: Path) -> Path:
    wheels = sorted(folder.glob("evmig_nss-*.whl"))
    assert len(wheels) == 1, f"expected one evmig_nss wheel in {folder}, found {[w.name for w in wheels]}"
    return wheels[0]


def test_the_vendored_wheel_is_the_librarys_wheel():  # DEC-2: a library change means a new version and a new copy
    vendored, built = one_wheel(FUNCTION_DIR / "wheels"), one_wheel(LIBRARY_DIST)

    assert vendored.name == built.name
    assert hashlib.sha256(vendored.read_bytes()).hexdigest() == hashlib.sha256(built.read_bytes()).hexdigest()


def test_uv_lock_pins_uipath_2_14_27_and_the_wheel_in_this_folder():
    lock = tomllib.loads((FUNCTION_DIR / "uv.lock").read_text(encoding="utf-8"))
    packages = {package["name"]: package for package in lock["package"]}
    wheel = one_wheel(FUNCTION_DIR / "wheels")

    assert packages["uipath"]["version"] == "2.14.27"  # DEC-9
    assert packages["evmig-nss"]["source"] == {"path": f"wheels/{wheel.name}"}
    assert packages["evmig-nss"]["wheels"][0]["hash"] == "sha256:" + hashlib.sha256(wheel.read_bytes()).hexdigest()


def test_bindings_json_declares_the_one_bucket():
    # Hand-written: `uipath init` cannot see the bucket calls, which are inside the wheel (DEC-7).
    bindings = json.loads((FUNCTION_DIR / "bindings.json").read_text(encoding="utf-8"))

    assert bindings["version"] == "2.0"
    assert bindings["resources"] == [
        {
            "resource": "bucket",
            "key": "EvMigFiles",
            "value": {
                "name": {"defaultValue": "EvMigFiles", "isExpression": False, "displayName": "Name"},
                "folderPath": {"defaultValue": "", "isExpression": False, "displayName": "Folder Path"},
            },
            "metadata": {"ActivityName": "download", "BindingsVersion": "2.2", "DisplayLabel": "FullName"},
        }
    ]


def test_the_generated_schema_has_what_the_flow_nodes_read():
    # entry-points.json is written by `uv run uipath init` (generated: not edited by hand).
    entry = json.loads((FUNCTION_DIR / "entry-points.json").read_text(encoding="utf-8"))["entryPoints"][0]

    assert entry["filePath"] == "main"
    assert set(entry["input"]["properties"]) == {"format_file_location", "data_file_location"}
    assert entry["input"]["required"] == ["format_file_location", "data_file_location"]
    row = entry["output"]["properties"]["rows"]["items"]
    assert set(row["properties"]) == {"screened_data", "wle_list", "request_id", "stop"}
    assert row["properties"]["screened_data"]["type"] == "object"
    assert row["properties"]["wle_list"]["type"] == "array"
    assert row["properties"]["stop"]["type"] == "string"


def test_importing_main_needs_no_login_and_creates_no_sdk_client():
    # `uipath init` imports main.py with no login (the library's get_sdk() is lazy). A fresh interpreter, no UIPATH_* variables.
    env = {key: value for key, value in os.environ.items() if not key.startswith(("UIPATH", "EVMIG"))}
    code = "import main; from evmig_nss.core import sdk; assert sdk._sdk is None; print('imported')"

    result = subprocess.run([sys.executable, "-c", code], cwd=FUNCTION_DIR, env=env, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "imported"
