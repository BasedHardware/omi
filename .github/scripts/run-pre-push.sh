#!/bin/bash
# run-pre-push.sh — Run pre-push tests manually (without actually pushing)
#
# Usage:
#   ./github/scripts/run-pre-push.sh              # vs origin/main
#   ./github/scripts/run-pre-push.sh upstream     # vs upstream/main
#
# Timing: ~5-30s depending on how many files changed

set -euo pipefail
# Script lives in .github/scripts/ — cd to repo root
cd "$(dirname "$0")/../.."

REMOTE="${1:-origin}"

echo "🔬 Running pre-push test check (simulated push to $REMOTE)..."
echo ""

# Export so the hook script sees it
export PRE_PUSH_DRY_RUN=1

# Detect the base branch (main or master)
BASE_REF=""
for candidate in main master; do
  if git rev-parse --verify "$REMOTE/$candidate" >/dev/null 2>&1; then
    BASE_REF="$REMOTE/$candidate"
    break
  fi
done

if [ -z "$BASE_REF" ]; then
  echo "⚠️  Cannot find $REMOTE/main or $REMOTE/master"
  exit 1
fi

MERGE_BASE=$(git merge-base "$BASE_REF" HEAD 2>/dev/null || echo "")
if [ -z "$MERGE_BASE" ]; then
  echo "⚠️  No merge-base with $BASE_REF"
  exit 1
fi

# Match both backend/*.py (root-level) and backend/**/*.py (subdirectories)
CHANGED_FILES=$(git diff --name-only "$MERGE_BASE" HEAD -- 'backend/*.py' 'backend/**/*.py' 2>/dev/null || true)

if [ -z "$CHANGED_FILES" ]; then
  echo "ℹ️  No backend Python files changed"
  exit 0
fi

echo "Changed files:"
echo "$CHANGED_FILES" | sed 's/^/  /'
echo ""

# Find and run matching tests
TEST_TMP=$(mktemp)
trap "rm -f $TEST_TMP" EXIT

while IFS= read -r f; do
  [ -z "$f" ] && continue
  REL_PATH="${f#backend/}"
  MODULE_NAME=$(basename "$f" .py)

  # If the changed file IS a test file, run it directly
  if [[ "$REL_PATH" == tests/*/test_*.py ]]; then
    echo "$REL_PATH" >> "$TEST_TMP"
    continue
  fi

  # Strategy 1: exact match — test_<module>.py in unit or integration
  for candidate in "tests/unit/test_${MODULE_NAME}.py" "tests/integration/test_${MODULE_NAME}.py"; do
    [ -f "backend/$candidate" ] && echo "$candidate" >> "$TEST_TMP"
  done

  # Strategy 2: prefix glob — test_<module_prefix>*.py
  # Note: find outputs paths relative to cwd (repo root), so strip
  # the leading "backend/" prefix to get test-relative paths
  while IFS= read -r match; do
    [ -z "$match" ] && continue
    # Strip "backend/" prefix from find output
    local_path="${match#backend/}"
    echo "$local_path" >> "$TEST_TMP"
  done < <(find backend/tests/unit backend/tests/integration \
    -name "test_${MODULE_NAME}*.py" 2>/dev/null || true)
done <<< "$CHANGED_FILES"

TEST_TARGETS=$(sort -u "$TEST_TMP" | while read t; do
  [ -f "backend/$t" ] && echo "$t" || true
done | tr '\n' ' ')

if [ -z "$TEST_TARGETS" ]; then
  echo "ℹ️  No matching test files found"
  exit 0
fi

COUNT=$(echo "$TEST_TARGETS" | wc -w | tr -d ' ')
echo "Running: $COUNT test file(s)"
echo ""

cd backend

# Build pytest args — only include --timeout if plugin is available
PYTEST_ARGS="-v --tb=short"
if python -m pytest --timeout-version >/dev/null 2>&1; then
  PYTEST_ARGS="$PYTEST_ARGS --timeout=30"
else
  echo "ℹ️  pytest-timeout not installed, running without timeout"
fi

python -m pytest $PYTEST_ARGS $TEST_TARGETS
