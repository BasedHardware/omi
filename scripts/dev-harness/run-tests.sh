#!/usr/bin/env bash
# Deterministic dev-harness unit-test lane (checks-manifest: dev-harness-unit-tests).
# Uses uv for a pinned, project-independent pytest environment in CI; falls back
# to the ambient python3 (which must already have pytest + python-dotenv) for
# machines without uv.
set -euo pipefail

cd "$(dirname "$0")/../.."

if command -v uv >/dev/null 2>&1; then
  exec uv run --no-project \
    --with 'pytest==8.4.1' \
    --with 'python-dotenv==1.1.0' \
    python -m pytest scripts/dev-harness/tests -q
fi

exec python3 -m pytest scripts/dev-harness/tests -q
