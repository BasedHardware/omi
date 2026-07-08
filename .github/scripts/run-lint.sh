#!/bin/bash
# run-lint.sh — Run all pre-commit hooks manually (no git commit needed)
#
# Usage:
#   ./github/scripts/run-lint.sh                  # all files (check only)
#   ./github/scripts/run-lint.sh --files a.py b.py # specific files
#
# Timing (warm cache, M2 MacBook):
#   black:           ~0.3s    ruff lint+format: ~0.5s
#   detect-secrets:  ~1.2s    pre-commit-hooks:  ~0.1s
#   Total:           ~2.1s

set -euo pipefail
# Script lives in .github/scripts/ — cd to repo root
cd "$(dirname "$0")/../.."

MODE="check"  # "check" or "fix"
FILES_ARG=""
FAIL=0

if [ "${1:-}" = "--fix" ]; then
  MODE="fix"
  shift
fi

if [ "${1:-}" = "--files" ]; then
  shift
  FILES_ARG="$*"
fi

if [ -n "$FILES_ARG" ]; then
  # Run on specific files
  echo "🔍 Running lints on specified files ($MODE)..."
  if command -v pre-commit &>/dev/null; then
    pre-commit run --files $FILES_ARG || FAIL=1
  else
    echo "⚠️  pre-commit not installed, running tools directly"
    for f in $FILES_ARG; do
      [ "${f##*.}" != "py" ] && continue
      if [ "$MODE" = "fix" ]; then
        echo "  black (fix) $f"
        if ! black --line-length=120 --skip-string-normalization "$f" 2>&1; then
          echo "    ❌ black failed on $f"
          FAIL=1
        fi
        echo "  ruff (fix) $f"
        if ! ruff check --fix --target-version py39 "$f" 2>&1; then
          echo "    ❌ ruff failed on $f"
          FAIL=1
        fi
      else
        echo "  black (check) $f"
        if ! black --check --line-length=120 --skip-string-normalization "$f" 2>&1; then
          echo "    ❌ black failed on $f"
          FAIL=1
        fi
        echo "  ruff (check) $f"
        if ! ruff check --target-version py39 "$f" 2>&1; then
          echo "    ❌ ruff failed on $f"
          FAIL=1
        fi
      fi
    done
  fi
else
  # Run on all files
  echo "🔍 Running lints on all files ($MODE)..."
  if command -v pre-commit &>/dev/null; then
    pre-commit run --all-files || FAIL=1
  else
    echo "⚠️  pre-commit not installed. Install with:"
    echo "   pip install pre-commit && pre-commit install"
    exit 1
  fi
fi

if [ "$FAIL" -ne 0 ]; then
  echo ""
  echo "❌ Lint errors found"
  exit 1
fi

echo "✅ Lint complete"
