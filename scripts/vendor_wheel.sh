#!/usr/bin/env bash
# Build evmig-nss and vendor the wheel into the function folders (default: the three EvMigEvelyn functions).
# Usage: scripts/vendor_wheel.sh [function folder ...]    Every library change needs a new version in evmig-nss/pyproject.toml first.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ "$#" -eq 0 ]; then
  set -- "$ROOT"/EvMigEvelyn/EvMigCsvMonitorTask "$ROOT"/EvMigEvelyn/EvMigCsvTask "$ROOT"/EvMigEvelyn/EvMigCsvSchemaProducer
fi
# uv writes dist/.gitignore ("*"); it goes, so the wheel can be committed (each function tests its copy against this one).
(cd "$ROOT/evmig-nss" && rm -rf dist && uv build --wheel && rm -f dist/.gitignore)
WHEEL="$(ls "$ROOT"/evmig-nss/dist/evmig_nss-*.whl)"
for fn in "$@"; do
  mkdir -p "$fn/wheels" && rm -f "$fn"/wheels/evmig_nss-*.whl && cp "$WHEEL" "$fn/wheels/"
  (cd "$fn" && uv add "./wheels/$(basename "$WHEEL")")
done
shasum -a 256 "$WHEEL"
