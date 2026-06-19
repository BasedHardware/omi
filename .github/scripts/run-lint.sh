#!/bin/bash
# run-lint.sh — Run all pre-commit hooks manually (no git commit needed)
#
# Usage:
#   ./scripts/lint/run-lint.sh                  # all files
#   ./scripts/lint/run-lint.sh --files a.py b.py  # specific files
#   ./scripts/lint/run-lint.sh --fix             # auto-fix where possible
#
# Timing (warm cache, M2 MacBook):
#   black:           ~0.3s    ruff lint+format: ~0.5s
#   detect-secrets:  ~1.2s    pre-commit-hooks:  ~0.1s
#   Total:           ~2.1s

set -euo pipefail
cd "$(dirname "$0")/../.."

ARGS=""
if [ "${1:-}" = "--fix" ]; then
  ARGS="--fix"
  shift
fi

if [ "${1:-}" = "--files" ]; then
  shift
  # Run on specific files
  FILES="$*"
  echo "🔍 Running lints on specified files..."
  if command -v pre-commit &>/dev/null; then
    pre-commit run $ARGS --files $FILES
  else
    echo "⚠️  pre-commit not installed, running tools directly"
    for f in $FILES; do
      [ "${f##*.}" != "py" ] && continue
      echo "  black $f" && black --line-length=120 --skip-string-normalization ${ARGS:+--check} "$f" || true
      echo "  ruff $f" && ruff check ${ARGS:+--fix} --target-version py39 "$f" || true
    done
  fi
else
  # Run on all files
  echo "🔍 Running lints on all files..."
  if command -v pre-commit &>/dev/null; then
    pre-commit run --all-files $ARGS
  else
    echo "⚠️  pre-commit not installed. Install with:"
    echo "   pip install pre-commit && pre-commit install"
    exit 1
  fi
fi

echo "✅ Lint complete"
