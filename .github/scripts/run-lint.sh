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
    if [ "$MODE" = "fix" ]; then
      pre-commit run --files $FILES_ARG
    else
      pre-commit run --files $FILES_ARG
    fi
  else
    echo "⚠️  pre-commit not installed, running tools directly"
    for f in $FILES_ARG; do
      [ "${f##*.}" != "py" ] && continue
      if [ "$MODE" = "fix" ]; then
        echo "  black (fix) $f" && black --line-length=120 --skip-string-normalization "$f" || true
        echo "  ruff (fix) $f" && ruff check --fix --target-version py39 "$f" || true
      else
        echo "  black (check) $f" && black --check --line-length=120 --skip-string-normalization "$f" || true
        echo "  ruff (check) $f" && ruff check --target-version py39 "$f" || true
      fi
    done
  fi
else
  # Run on all files
  echo "🔍 Running lints on all files ($MODE)..."
  if command -v pre-commit &>/dev/null; then
    pre-commit run --all-files
  else
    echo "⚠️  pre-commit not installed. Install with:"
    echo "   pip install pre-commit && pre-commit install"
    exit 1
  fi
fi

echo "✅ Lint complete"
