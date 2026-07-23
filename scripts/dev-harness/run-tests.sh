#!/usr/bin/env bash
# Deterministic dev-harness unit-test lane (checks-manifest: dev-harness-unit-tests).
#
# Prefers an interpreter that ALREADY has pytest + python-dotenv (the repo's
# backend venv, then the ambient python3) so the check needs no uv cache,
# network, or ~/.cache write — keeping `make preflight` green in restricted
# local/agent environments. Only a truly bare environment falls back to uv,
# and even then the cache is redirected to a writable temp dir. Real pytest
# failures still fail the lane in every path.
set -euo pipefail

cd "$(dirname "$0")/../.."

run_pytest() {
  exec "$@" -m pytest scripts/dev-harness/tests -q
}

for py in backend/.venv/bin/python backend/venv/bin/python python3; do
  if [ -x "$py" ] || command -v "$py" >/dev/null 2>&1; then
    if "$py" -c 'import pytest, dotenv' >/dev/null 2>&1; then
      run_pytest "$py"
    fi
  fi
done

if command -v uv >/dev/null 2>&1; then
  # Redirect the cache off the default ~/.cache/uv, which is not always writable
  # in sandboxed preflight environments; a temp dir always is.
  export UV_CACHE_DIR="${UV_CACHE_DIR:-${TMPDIR:-/tmp}/omi-dev-harness-uv-cache}"
  exec uv run --no-project \
    --with 'pytest==8.4.1' \
    --with 'python-dotenv==1.1.0' \
    python -m pytest scripts/dev-harness/tests -q
fi

echo "dev-harness tests require pytest + python-dotenv via a backend venv, python3, or uv; none available" >&2
exit 1
