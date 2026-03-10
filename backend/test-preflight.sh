#!/usr/bin/env bash
# test-preflight.sh — Verify environment is ready before running backend tests.
# Run this before backend/test.sh to catch missing tools, packages, and env vars.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass=0
warn=0
fail=0

ok()   { echo -e "  ${GREEN}✓${NC} $1"; pass=$((pass + 1)); }
skip() { echo -e "  ${YELLOW}⚠${NC} $1"; warn=$((warn + 1)); }
bad()  { echo -e "  ${RED}✗${NC} $1"; fail=$((fail + 1)); }

# ── Tools ──
echo "Tools:"

if command -v python3 &>/dev/null; then
  ok "python3 $(python3 --version 2>&1 | awk '{print $2}')"
else
  bad "python3 not found"
fi

if python3 -m pytest --version &>/dev/null 2>&1; then
  ok "pytest $(python3 -m pytest --version 2>&1 | awk '{print $2}')"
else
  bad "pytest not installed (pip install pytest)"
fi

if command -v black &>/dev/null; then
  ok "black (formatter)"
else
  skip "black not installed — pre-commit hook will fail (pip install black)"
fi

# ── Python packages ──
echo ""
echo "Python packages:"

missing_pkgs=()
for pkg in pydantic fastapi firebase_admin google.cloud.firestore redis deepgram_sdk openpipe; do
  if python3 -c "import $pkg" &>/dev/null 2>&1; then
    ok "$pkg"
  else
    missing_pkgs+=("$pkg")
    skip "$pkg not importable"
  fi
done

if [[ ${#missing_pkgs[@]} -gt 0 ]]; then
  echo -e "  ${YELLOW}→${NC} Run: pip install -r requirements.txt"
fi

# ── Environment variables (required for unit tests) ──
echo ""
echo "Env vars (unit tests):"

# ENCRYPTION_SECRET is set by test.sh, but check if it's already in env
if [[ -n "${ENCRYPTION_SECRET:-}" ]]; then
  ok "ENCRYPTION_SECRET (set in env)"
else
  ok "ENCRYPTION_SECRET (set by test.sh — no action needed)"
fi

# ── Environment variables (integration tests / optional) ──
echo ""
echo "Env vars (integration — optional):"

check_env() {
  local var=$1
  local desc=$2
  if [[ -n "${!var:-}" ]]; then
    ok "$var ($desc)"
  else
    skip "$var not set ($desc)"
  fi
}

check_env OPENAI_API_KEY "LLM calls — some integration tests skip without it"
check_env DEEPGRAM_API_KEY "STT streaming and pre-recorded transcription"
check_env ADMIN_KEY "admin endpoint tests"
check_env REDIS_DB_HOST "Redis connection (default: localhost)"
check_env REDIS_DB_PASSWORD "Redis auth"
check_env GOOGLE_APPLICATION_CREDENTIALS "Firebase/Firestore integration tests"

# ── Redis connectivity ──
echo ""
echo "Services:"

redis_host="${REDIS_DB_HOST:-localhost}"
redis_port="${REDIS_DB_PORT:-6379}"
if command -v redis-cli &>/dev/null; then
  if redis-cli -h "$redis_host" -p "$redis_port" ${REDIS_DB_PASSWORD:+-a "$REDIS_DB_PASSWORD"} ping &>/dev/null 2>&1; then
    ok "Redis ($redis_host:$redis_port) — connected"
  else
    skip "Redis ($redis_host:$redis_port) — not reachable (integration tests may fail)"
  fi
else
  skip "redis-cli not installed — cannot check Redis connectivity"
fi

# ── Test file sanity ──
echo ""
echo "Test files:"

test_count=$(find tests/unit -name 'test_*.py' 2>/dev/null | wc -l)
if [[ $test_count -gt 0 ]]; then
  ok "$test_count unit test files found"
else
  bad "No unit test files found in tests/unit/"
fi

# Check if test.sh test files all exist
missing_tests=()
while IFS= read -r line; do
  test_file=$(echo "$line" | sed 's/pytest //' | sed 's/ -v//')
  if [[ ! -f "$test_file" ]]; then
    missing_tests+=("$test_file")
  fi
done < <(grep '^pytest tests/' test.sh 2>/dev/null)

if [[ ${#missing_tests[@]} -gt 0 ]]; then
  bad "test.sh references missing files: ${missing_tests[*]}"
else
  ok "All test.sh references resolve to existing files"
fi

# ── Summary ──
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
total=$((pass + warn + fail))
echo -e "  ${GREEN}$pass passed${NC}  ${YELLOW}$warn warnings${NC}  ${RED}$fail failed${NC}  ($total checks)"

if [[ $fail -gt 0 ]]; then
  echo -e "  ${RED}Fix failures above before running test.sh${NC}"
  exit 1
elif [[ $warn -gt 0 ]]; then
  echo -e "  ${YELLOW}Warnings are optional — unit tests should still pass${NC}"
  exit 0
else
  echo -e "  ${GREEN}All clear — ready to run test.sh${NC}"
  exit 0
fi
