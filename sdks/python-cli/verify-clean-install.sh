#!/usr/bin/env bash
# verify-clean-install.sh — release-blocking install smoke test for omi-cli.
#
# Guards against the omi-cli 0.2.3 incident: the published wheel omitted
# `click` from its declared requirements, so EVERY fresh `pip install omi-cli`
# crashed with `ModuleNotFoundError: No module named 'click'`. Editable/dev
# installs and `twine check` (metadata-only) both mask that class of breakage.
#
# What this does (build-agnostic — pass an already-built dist dir):
#   1. Creates a throwaway virtual environment OUTSIDE the repo.
#   2. Installs ONLY the built wheel into it (no extras, no dev deps, no
#      editable source tree) — exactly what an end user gets from PyPI.
#   3. Runs the console script: `omi --version` must print the packaged
#      version and `omi --help` must exit 0.
#
# Usage: verify-clean-install.sh [dist-dir]   (default: ./dist)
set -euo pipefail

DIST_DIR="${1:-dist}"
PKG_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="$(cd "$PKG_DIR" && cd "$DIST_DIR" && pwd)"

WHEEL="$(ls "$DIST_DIR"/omi_cli-*.whl 2>/dev/null | head -n 1)"
if [ -z "$WHEEL" ]; then
    echo "ERROR: no omi_cli-*.whl found in $DIST_DIR (run 'python -m build' first)" >&2
    exit 1
fi
echo "== install smoke on $(basename "$WHEEL")"

# Normalize the wheel path for the interpreter (MSYS/git-bash needs a
# Windows path; no-op on Linux/macOS).
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) WHEEL="$(cygpath -w "$WHEEL")" ;;
esac

# Read the version straight out of the wheel metadata — not the source tree —
# so the check compares the artifact against itself.
WHEEL_VERSION="$(python - "$WHEEL" <<'PY'
import sys, zipfile
from email.parser import Parser
with zipfile.ZipFile(sys.argv[1]) as zf:
    meta = next(n for n in zf.namelist() if n.endswith("METADATA"))
    print(Parser().parsestr(zf.read(meta).decode())["Version"])
PY
)"
echo "wheel version: $WHEEL_VERSION"

SMOKE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/omi-cli-smoke.XXXXXX")"
trap 'rm -rf "$SMOKE_DIR"' EXIT

python -m venv "$SMOKE_DIR/venv"
# shellcheck disable=SC1091
PIP="$SMOKE_DIR/venv/bin/pip"
OMI="$SMOKE_DIR/venv/bin/omi"
if [ ! -f "$PIP" ]; then
    # Windows-style venvs
    PIP="$SMOKE_DIR/venv/Scripts/pip.exe"
    OMI="$SMOKE_DIR/venv/Scripts/omi.exe"
fi

echo "== clean install (wheel only, no extras)"
"$PIP" install --no-cache-dir --no-input "$WHEEL" 1>&2

echo "== import + console-script check"
VERSION_OUT="$("$OMI" --version)"
echo "omi --version -> $VERSION_OUT"
case "$VERSION_OUT" in
    *"$WHEEL_VERSION"*) ;;
    *)
        echo "::error::install smoke FAILED: 'omi --version' printed '$VERSION_OUT' (expected it to contain wheel version $WHEEL_VERSION). The wheel's dependency declaration is likely broken — do not publish." >&2
        exit 1
        ;;
esac

"$OMI" --help > /dev/null 2>&1
echo "== install smoke PASSED (clean install -> omi --version + omi --help OK)"
