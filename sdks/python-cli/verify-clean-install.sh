#!/usr/bin/env bash
# Clean-install smoke test for omi-cli.
#
# Installs a BUILT omi-cli wheel into a throwaway virtual environment and runs
# the console script there. This is the guard the published 0.2.3 release
# needed: an editable/`-e .[dev]` install masks a missing runtime dependency
# (the dev extra pulls it in), and `twine check` only validates metadata —
# neither ever *imports* the wheel the way a fresh `pip install` + `omi`
# invocation does.
#
# Build-agnostic: works with whatever wheel already sits in dist/ (or the path
# given as $1), so the publish workflow can run it right after `twine check`,
# and CI can run it right after `python -m build`.
#
# Usage:  bash verify-clean-install.sh [path/to/dist]
# Exit codes: 0 = smoke passed, 1 = wheel missing/ambiguous or smoke failed.

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
wheels=("$dist_dir"/omi_cli-*.whl)
shopt -u nullglob

if [ "${#wheels[@]}" -eq 0 ]; then
  fail "no omi_cli-*.whl found in '$dist_dir'. Build one first: python -m build"
fi
if [ "${#wheels[@]}" -ne 1 ]; then
  fail "multiple wheels in '$dist_dir' (${wheels[*]}); keep exactly one build"
fi
wheel="${wheels[0]}"
echo "verify-clean-install: wheel = $wheel"

# Allocate the scratch dir via Python so the path is valid for the SAME
# interpreter that creates the venv (Git-Bash /tmp is not visible to Windows
# Python, which would otherwise create the venv in a phantom C:\tmp).
work="$("$PY" -c "import tempfile; print(tempfile.mkdtemp())")"
trap 'rm -rf "$work"' EXIT

echo "verify-clean-install: creating clean venv at $work/venv"
"$PY" -m venv "$work/venv"
# Upgrade pip only inside the venv; the wheel's own dependencies must resolve
# from the wheel metadata alone (this is the whole point of the guard).
VENV_BIN="$work/venv/bin"
[ -d "$VENV_BIN" ] || VENV_BIN="$work/venv/Scripts"   # Windows layout
"$VENV_BIN/python" -m pip install --quiet --upgrade pip
"$VENV_BIN/python" -m pip install --quiet "$wheel"

run_omi() {
  # Windows: a freshly created venv .exe can transiently fail exec (defender /
  # indexer lock). Retry once, then fall back to `python -m omi_cli`.
  "$VENV_BIN/omi" "$@" && return 0
  sleep 2
  "$VENV_BIN/omi" "$@" && return 0
  echo "verify-clean-install: direct exe failed; retrying via python -m omi_cli" >&2
  "$VENV_BIN/python" -m omi_cli "$@"
}

# The console script must exist and run with ONLY the wheel's declared deps.
echo "verify-clean-install: omi --version"
version_out="$(run_omi --version)"
echo "verify-clean-install: got: $version_out"
case "$version_out" in
  omi-cli*) ;;                       # e.g. "omi-cli 0.3.0"
  *) fail "unexpected 'omi --version' output: $version_out" ;;
esac

echo "verify-clean-install: omi --help"
run_omi --help > /dev/null

echo "verify-clean-install: PASS (clean install + console script OK)"
