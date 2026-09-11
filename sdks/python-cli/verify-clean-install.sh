#!/usr/bin/env bash
# Clean-install smoke test for omi-cli.
#
# Installs each BUILT omi-cli artifact into a throwaway virtual environment
# and runs the console script there. This is the guard the published 0.2.3
# release needed: an editable/`-e .[dev]` install masks a missing runtime
# dependency (the dev extra pulls it in), and `twine check` only validates
# metadata — neither ever *imports* the artifact the way a fresh
# `pip install` + `omi` invocation does.
#
# Build-agnostic: works with whatever artifacts already sit in dist/ (or the
# path given as $1), so the publish workflow can run it right after
# `twine check`, and CI can run it right after `python -m build`.
#
# Every artifact in the dist dir is verified (wheel AND sdist): the publish
# job uploads both, so a malformed sdist must not reach PyPI untested. The
# installed package must also report the artifact's own declared version,
# ruling out accidental stale/duplicate builds.
#
# Usage:  bash verify-clean-install.sh [path/to/dist]
# Exit codes: 0 = smoke passed, 1 = artifact missing/ambiguous or smoke failed.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dist_dir="${1:-$here/dist}"

fail() { echo "verify-clean-install: FAIL: $*" >&2; exit 1; }

# Pick a Python launcher that actually runs (Git-Bash on Windows exposes an
# MS-Store `python3` stub that exists on PATH but prints an error and exits).
PY=""
for cand in python3 python py; do
  if command -v "$cand" > /dev/null 2>&1 && "$cand" -c "import sys" > /dev/null 2>&1; then
    PY="$cand"; break
  fi
done
[ -n "$PY" ] || fail "no working python3/python/py on PATH"

shopt -s nullglob
artifacts=("$dist_dir"/omi_cli-*.whl "$dist_dir"/omi_cli-*.tar.gz)
shopt -u nullglob

if [ "${#artifacts[@]}" -eq 0 ]; then
  fail "no omi_cli-*.whl or omi_cli-*.tar.gz found in '$dist_dir'. Build first: python -m build"
fi

# Print the version an artifact declares in its own metadata (wheel METADATA
# / sdist PKG-INFO) without installing it. Paths are passed through this
# helper so Windows Python never sees a Git-Bash-style /tmp/... argument.
declared_version() {
  "$PY" - "$1" <<'PYV'
import sys, tarfile, zipfile
from email.parser import Parser
path = sys.argv[1]
if path.endswith(".whl"):
    with zipfile.ZipFile(path) as zf:
        meta = next(n for n in zf.namelist() if n.endswith("METADATA"))
        print(Parser().parsestr(zf.read(meta).decode())["Version"])
else:
    with tarfile.open(path) as tf:
        meta = next(n for n in tf.getnames() if n.endswith("PKG-INFO"))
        print(Parser().parsestr(tf.extractfile(meta).read().decode())["Version"])
PYV
}

for artifact in "${artifacts[@]}"; do
  echo "verify-clean-install: artifact = $artifact"

  # Resolve the artifact path to something the interpreter can open (MSYS
  # /c/... paths are meaningless to Windows Python; no-op on Linux/macOS).
  case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) artifact_path="$(cygpath -w "$artifact")" ;;
    *) artifact_path="$artifact" ;;
  esac
  declared="$(declared_version "$artifact_path")"
  echo "verify-clean-install: declared version = $declared"

  # Allocate the scratch dir via Python so the path is valid for the SAME
  # interpreter that creates the venv (Git-Bash /tmp is not visible to Windows
  # Python, which would otherwise create the venv in a phantom C:\tmp).
  work="$("$PY" -c "import tempfile; print(tempfile.mkdtemp())")"
  trap 'rm -rf "$work"' EXIT

  echo "verify-clean-install: creating clean venv at $work/venv"
  "$PY" -m venv "$work/venv"
  VENV_BIN="$work/venv/bin"
  [ -d "$VENV_BIN" ] || VENV_BIN="$work/venv/Scripts"   # Windows layout
  "$VENV_BIN/python" -m pip install --quiet --upgrade pip
  "$VENV_BIN/python" -m pip install --quiet "$artifact_path"

  run_omi() {
    # Windows: a freshly created venv .exe can transiently fail exec (defender
    # / indexer lock). Retry the direct launcher once. There is deliberately NO
    # `python -m omi_cli` fallback: this gate exists to prove the console entry
    # point users invoke works after a bare `pip install`, so a broken or
    # missing entry point must fail the smoke test, not route around it.
    "$VENV_BIN/omi" "$@" && return 0
    sleep 2
    "$VENV_BIN/omi" "$@"
  }

  # The console script must exist and run with ONLY the artifact's declared
  # deps, and must report the artifact's own declared version.
  echo "verify-clean-install: omi --version"
  version_out="$(run_omi --version)" || \
    fail "'omi' console script failed to execute after clean install of $(basename "$artifact") (entry point broken or missing)"
  echo "verify-clean-install: got: $version_out"
  case "$version_out" in
    *"$declared"*) ;;                  # e.g. "omi-cli 0.3.0" with declared=0.3.0
    *) fail "unexpected 'omi --version' output for $(basename "$artifact"): '$version_out' (declared version is $declared)" ;;
  esac

  echo "verify-clean-install: omi --help"
  run_omi --help > /dev/null || fail "'omi --help' exited non-zero"

  rm -rf "$work"
  echo "verify-clean-install: PASS ($(basename "$artifact"))"
done

echo "verify-clean-install: PASS (all ${#artifacts[@]} artifact(s) clean-install and run)"
