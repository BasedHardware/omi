#!/usr/bin/env bash
#
# Install each built artifact into a clean environment and run the console
# script.
#
# The editable dev install (`pip install -e ".[dev]"`) cannot catch a runtime
# dependency declaration that is missing or too loose, because the dev extras
# pull in packages the runtime does not declare. omi-cli 0.2.3 shipped that way:
# its metadata omitted `click` while `omi_cli/main.py` imports it, pip resolved
# typer 0.27.2 (which no longer depends on click), and every new user's first
# `omi --version` raised ModuleNotFoundError.
#
# Every artifact in the dist directory is verified, so a malformed sdist cannot
# pass `twine check` and reach PyPI without an installation test. The version
# the entry point prints is also cross-checked against the version declared in
# that same artifact's own metadata, so a stale or drifted declared version
# cannot ship silently.
#
# Usage: ./verify-clean-install.sh [dist-dir]   (default: dist)
set -euo pipefail

dist_dir="${1:-dist}"

shopt -s nullglob
artifacts=("$dist_dir"/*.whl "$dist_dir"/*.tar.gz)
shopt -u nullglob

if [ ${#artifacts[@]} -eq 0 ]; then
  echo "no wheel or sdist found in $dist_dir" >&2
  exit 1
fi

# Print the version an artifact declares in its own metadata: the wheel's
# *.dist-info/METADATA or the sdist's PKG-INFO.
artifact_version() {
  python - "$1" <<'PY'
import sys
import tarfile
import zipfile

path = sys.argv[1]
if path.endswith(".whl"):
    with zipfile.ZipFile(path) as archive:
        member = next(
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        )
        text = archive.read(member).decode("utf-8", "replace")
else:
    with tarfile.open(path) as archive:
        member = next(
            entry for entry in archive.getmembers() if entry.name.endswith("PKG-INFO")
        )
        text = archive.extractfile(member).read().decode("utf-8", "replace")

for line in text.splitlines():
    if line.startswith("Version:"):
        print(line.split(":", 1)[1].strip())
        break
PY
}

for artifact in "${artifacts[@]}"; do
  echo "=== $artifact ==="

  declared_version="$(artifact_version "$artifact")"
  if [ -z "$declared_version" ]; then
    echo "no declared version found in $artifact" >&2
    exit 1
  fi

  venv_dir="$(mktemp -d)"
  python -m venv "$venv_dir"

  # Detect the layout only after the venv exists: `mktemp -d` returns an empty
  # directory, so probing for bin/ before creating the venv always fell back to
  # Scripts/ and broke every Linux run.
  venv_bin="$venv_dir/bin"
  if [ ! -d "$venv_bin" ]; then
    venv_bin="$venv_dir/Scripts"
  fi

  venv_python="$venv_bin/python"
  if [ ! -x "$venv_python" ] && [ -x "$venv_bin/python.exe" ]; then
    venv_python="$venv_bin/python.exe"
  fi
  if [ ! -x "$venv_python" ]; then
    echo "no interpreter found in $venv_bin (venv creation failed?)" >&2
    rm -rf "$venv_dir"
    exit 1
  fi

  "$venv_python" -m pip install --upgrade pip > /dev/null
  "$venv_python" -m pip install "$artifact"

  echo "--- installed runtime dependencies ---"
  "$venv_python" -m pip list --format=freeze

  echo "--- console script ---"
  printed_version="$("$venv_bin/omi" --version)"
  echo "$printed_version"
  "$venv_bin/omi" --help > /dev/null

  expected_version="omi-cli $declared_version"
  if [ "$printed_version" != "$expected_version" ]; then
    echo "version drift: $artifact declares '$declared_version' but the CLI prints '$printed_version' (expected '$expected_version')" >&2
    rm -rf "$venv_dir"
    exit 1
  fi

  rm -rf "$venv_dir"
  echo "clean install smoke: ok ($artifact, version $declared_version)"
done
