#!/bin/bash
# run-pre-push.sh — Run pre-push tests manually (without actually pushing)
#
# Usage:
#   ./scripts/lint/run-pre-push.sh              # vs origin/main
#   ./scripts/lint/run-pre-push.sh upstream     # vs upstream/main
#
# Timing: ~5-30s depending on how many files changed

set -euo pipefail
cd "$(dirname "$0")/../.."

REMOTE="${1:-origin}"

echo "🔬 Running pre-push test check (simulated push to $REMOTE)..."
echo ""

# Export so the hook script sees it
export PRE_PUSH_DRY_RUN=1

# Run the same logic as the pre-push hook
MERGE_BASE=""
for candidate in main master; do
  if git rev-parse --verify "$REMOTE/$candidate" >/dev/null 2>&1; then
    MERGE_BASE="$($REMOTE/$candidate)"
    break
  fi
done

if [ -z "$MERGE_BASE" ]; then
  echo "⚠️  Cannot find $REMOTE/main or $REMOTE/master"
  exit 1
fi

CHANGED_FILES=$(git diff --name-only "$(git merge-base "$REMOTE/main" HEAD 2>/dev/null || echo HEAD)" HEAD -- 'backend/**/*.py' 2>/dev/null || true)

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

  if [[ "$REL_PATH" == tests/*/test_*.py ]]; then
    echo "$REL_PATH" >> "$TEST_TMP"
    continue
  fi

  for candidate in "tests/unit/test_${MODULE_NAME}.py" "tests/integration/test_${MODULE_NAME}.py"; do
    [ -f "backend/$candidate" ] && echo "$candidate" >> "$TEST_TMP"
  done
  find backend/tests/unit backend/tests/integration \
    -name "test_${MODULE_NAME}*.py" >> "$TEST_TMP" 2>/dev/null || true
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
python -m pytest -v --timeout=30 --tb=short $TEST_TARGETS
