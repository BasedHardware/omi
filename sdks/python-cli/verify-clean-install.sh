#!/usr/bin/env bash
# Clean-install smoke test for omi-cli.
#
# Installs BUILT omi-cli artifacts into throwaway virtual environments and runs
# the console script there. This is the guard the published 0.2.3 release
# needed: an editable/`-e .[dev]` install masks a missing runtime dependency
# (the dev extra pulls it in), and `twine check` only validates metadata —
# neither ever *imports* the artifact the way a fresh `pip install` + `omi`
# invocation does.
#
# Build-agnostic: works with whatever artifacts already sit in dist/ (or the
# path given as $1), so the publish workflow can run it right after
# `twine check`, and CI can run it right after `python -m build`.
#
# Coverage: the wheel is always smoked. If an sdist (omi_cli-*.tar.gz) sits in
# the same dist dir, it is smoked too — a malformed sdist must not be able to
# reach PyPI untested. For every artifact, the version the entry point prints
# is cross-checked against the version declared in THAT artifact's own
# metadata (wheel METADATA / sdist PKG-INFO), which rules out stale or
# duplicate builds where an older artifact lingers in dist/.
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
wheels=("$dist_dir"/omi_cli-*.whl)
sdists=("$dist_dir"/omi_cli-*.tar.gz)
shopt -u nullglob

if [ "${#wheels[@]}" -eq 0 ]; then
  fail "no omi_cli-*.whl found in '$dist_dir'. Build one first: python -m build"
fi
if [ "${#wheels[@]}" -ne 1 ]; then
  fail "multiple wheels in '$dist_dir' (${wheels[*]}); keep exactly one build"
fi
if [ "${#sdists[@]}" -gt 1 ]; then
  fail "multiple sdists in '$dist_dir' (${sdists[*]}); keep exactly one build"
fi
wheel="${wheels[0]}"
echo "verify-clean-install: wheel = $wheel"

artifact_version() {
  # $1 = path to a wheel or sdist; prints the version declared in its own
  # metadata (wheel: *.dist-info/METADATA, sdist: PKG-INFO).
  case "$1" in
    *.whl)
      "$PY" - "$1" <<'PYEOF'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as z:
    meta = next(n for n in z.namelist() if n.endswith(".dist-info/METADATA"))
    for line in z.read(meta).decode("utf-8", "replace").splitlines():
        if line.startswith("Version:"):
            print(line.split(":", 1)[1].strip())
            break
PYEOF
      ;;
    *.tar.gz)
      "$PY" - "$1" <<'PYEOF'
import sys, tarfile
with tarfile.open(sys.argv[1], "r:gz") as t:
    pkg = next(n for n in t.getnames() if n.endswith("/PKG-INFO"))
    for line in t.extractfile(pkg).read().decode("utf-8", "replace").splitlines():
        if line.startswith("Version:"):
            print(line.split(":", 1)[1].strip())
            break
PYEOF
      ;;
  esac
}

# Scratch dir allocated via Python so the path is valid for the SAME
# interpreter that creates the venvs (Git-Bash /tmp is not visible to Windows
# Python, which would otherwise create the venv in a phantom C:\tmp).
work="$("$PY" -c "import tempfile; print(tempfile.mkdtemp())")"
trap 'rm -rf "$work"' EXIT

VENV_BIN=""

run_omi() {
  # Windows: a freshly created venv .exe can transiently fail exec (defender /
  # indexer lock). Retry the direct launcher once. There is deliberately NO
  # `python -m omi_cli` fallback: this gate exists to prove the console entry
  # point users invoke works after a bare `pip install`, so a broken or
  # missing entry point must fail the smoke test, not route around it.
  "$VENV_BIN/omi" "$@" && return 0
  sleep 2
  "$VENV_BIN/omi" "$@"
}

smoke() {
  # $1 = artifact (wheel or sdist). Installs it into a fresh venv and runs the
  # console script with ONLY the artifact's declared dependencies.
  local artifact="$1"
  local declared expected version_out venv
  declared="$(artifact_version "$artifact")" || \
    fail "cannot read declared version from $artifact"
  [ -n "$declared" ] || fail "no 'Version:' header found in $artifact metadata"

  venv="$work/venv-$(basename "$artifact" | tr -c 'A-Za-z0-9._-' '_')"
  echo "verify-clean-install: creating clean venv at $venv"
  "$PY" -m venv "$venv"
  VENV_BIN="$venv/bin"
  [ -d "$VENV_BIN" ] || VENV_BIN="$venv/Scripts"   # Windows layout
  # Upgrade pip only inside the venv; the artifact's own dependencies must
  # resolve from its metadata alone (this is the whole point of the guard).
  "$VENV_BIN/python" -m pip install --quiet --upgrade pip
  "$VENV_BIN/python" -m pip install --quiet "$artifact"

  # The console script must exist and run with only the declared deps.
  echo "verify-clean-install: omi --version ($artifact)"
  version_out="$(run_omi --version)" || \
    fail "'omi' console script failed to execute after clean install of $artifact (entry point broken or missing)"
  echo "verify-clean-install: got: $version_out"
  case "$version_out" in
    omi-cli\ *) expected="${version_out#omi-cli }" ;;
    omi-cli*)   expected="${version_out#omi-cli}" ;;
    *) fail "unexpected 'omi --version' output: $version_out" ;;
  esac
  # Cross-check against the artifact's OWN metadata: catches stale or
  # duplicate builds whose printed version drifts from what they declare.
  if [ "$expected" != "$declared" ]; then
    fail "'omi --version' prints '$expected' but $artifact declares '$declared' (stale or duplicate build?)"
  fi

  echo "verify-clean-install: omi --help ($artifact)"
  run_omi --help > /dev/null || fail "'omi --help' exited non-zero ($artifact)"
  echo "verify-clean-install: PASS ($artifact: clean install + console script OK, version $expected matches metadata)"
}

smoke "$wheel"

if [ "${#sdists[@]}" -eq 1 ]; then
  echo "verify-clean-install: sdist present in '$dist_dir' - smoking it too"
  smoke "${sdists[0]}"
else
  echo "verify-clean-install: no sdist in '$dist_dir' - wheel-only smoke (build with 'python -m build' to cover both)"
fi

echo "verify-clean-install: PASS (clean install + console script OK)"
