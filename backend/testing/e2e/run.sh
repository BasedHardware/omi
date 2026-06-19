#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Hermetic E2E Harness — One-command entry point
#
# Usage:
#   bash backend/testing/e2e/run.sh
#   cd backend && bash testing/e2e/run.sh -v
#   cd backend && bash testing/e2e/run.sh -k test_crud
#
# Exit code:
#   0 — all tests passed
#   1 — one or more tests failed (pytest exit code propagated)
# ---------------------------------------------------------------------------

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPO_ROOT="$(cd "$BACKEND_DIR/.." && pwd)"
cd "$BACKEND_DIR"

echo "=== Omi Hermetic E2E Harness ==="
echo "Working dir: $(pwd)"

# ─── Detect / activate virtual environment ──────────────────────────────
for venv_dir in "$REPO_ROOT/.venv" "$BACKEND_DIR/.venv" "$REPO_ROOT/venv" "$BACKEND_DIR/venv"; do
    if [ -f "$venv_dir/bin/activate" ]; then
        echo "Activating ${venv_dir}..."
        # shellcheck disable=SC1090
        source "$venv_dir/bin/activate"
        break
    fi
done

if ! command -v python >/dev/null 2>&1; then
    echo "ERROR: python not found on PATH"
    exit 1
fi

# ─── Verify fake dependencies are installed ───────────────────────────
python -c "import fake_firestore; import fakeredis; import pytest_httpserver; import aioresponses" 2>/dev/null || {
    echo "ERROR: E2E test dependencies are not installed."
    echo "Run: python -m pip install -r testing/e2e/requirements.txt"
    echo "Then retry: bash testing/e2e/run.sh"
    exit 1
}

# ─── Verify core backend deps are installed ────────────────────────────
python -c "import fastapi; import firebase_admin; import google.cloud.firestore" 2>/dev/null || {
    echo "ERROR: Backend dependencies not installed."
    echo "Run: python -m pip install -r requirements.txt"
    exit 1
}

# ─── Create temp dirs that main.py expects ─────────────────────────────
for d in _temp _samples _segments _speech_profiles; do
    mkdir -p "$d" 2>/dev/null || true
done

# ─── Run pytest ────────────────────────────────────────────────────────
echo ""
echo "Running e2e tests..."
echo "================================"

if [ "$#" -eq 0 ]; then
    set -- -v --tb=short
fi

# WebSocket/provider-seam regressions should fail instead of hanging forever.
# Override with E2E_PYTEST_TIMEOUT=300s when deliberately debugging a slow run.
PYTEST_TIMEOUT="${E2E_PYTEST_TIMEOUT:-120s}"

# tiktoken lazily downloads tokenizer data the first time a clean environment calls
# encoding_for_model(). Do this before pytest imports the hermetic socket guard so
# a cold cache does not fail as an accidental outbound network attempt.
echo "Prewarming tokenizer cache..."
python - <<'PY'
import tiktoken

tiktoken.encoding_for_model('gpt-4')
PY

set +e
if command -v timeout >/dev/null 2>&1; then
    timeout --preserve-status --kill-after=5s "$PYTEST_TIMEOUT" python -m pytest testing/e2e/ "$@"
    PYTEST_EXIT_CODE=$?
    if [ $PYTEST_EXIT_CODE -eq 143 ] || [ $PYTEST_EXIT_CODE -eq 124 ]; then
        echo "ERROR: e2e pytest exceeded timeout ${PYTEST_TIMEOUT}"
    fi
else
    echo "ERROR: GNU timeout is required so E2E_PYTEST_TIMEOUT=${PYTEST_TIMEOUT} is enforced"
    PYTEST_EXIT_CODE=1
fi
set -e

echo ""
echo "================================"
if [ $PYTEST_EXIT_CODE -eq 0 ]; then
    echo "✅ All e2e tests passed!"
else
    echo "❌ Some e2e tests failed (exit code ${PYTEST_EXIT_CODE})"
fi

exit $PYTEST_EXIT_CODE
