#!/bin/bash
# run-lint.sh — Run all pre-commit hooks manually (no git commit needed)
#
# Usage:
#   ./github/scripts/run-lint.sh                  # all files (check only)
#   ./github/scripts/run-lint.sh --files a.py b.py # specific files
#
# Timing (warm cache, M2 MacBook):
#   ruff format:     ~0.3s    ruff lint:        ~0.4s
#   detect-secrets:  ~1.2s    pre-commit-hooks:  ~0.1s
#   Total:           ~2.1s

set -euo pipefail
# Script lives in .github/scripts/ — cd to repo root
cd "$(dirname "$0")/../.."

MODE="check"  # "check" or "fix"
FILES_ARG=""
FAIL=0
RUFF_BIN="ruff"
if [ -x backend/.venv/bin/ruff ]; then
  RUFF_BIN="backend/.venv/bin/ruff"
fi

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
    # shellcheck disable=SC2086
    pre-commit run --files $FILES_ARG || FAIL=1
  else
    echo "⚠️  pre-commit not installed, running tools directly"
    for f in $FILES_ARG; do
      [ "${f##*.}" != "py" ] && continue
      if [ "$MODE" = "fix" ]; then
        echo "  ruff format (fix) $f"
        if ! "$RUFF_BIN" format --config backend/pyproject.toml "$f" 2>&1; then
          echo "    ❌ ruff format failed on $f"
          FAIL=1
        fi
        echo "  ruff check (fix) $f"
        if ! "$RUFF_BIN" check --fix --config backend/pyproject.toml "$f" 2>&1; then
          echo "    ❌ ruff check failed on $f"
          FAIL=1
        fi
      else
        echo "  ruff format (check) $f"
        if ! "$RUFF_BIN" format --check --config backend/pyproject.toml "$f" 2>&1; then
          echo "    ❌ ruff format failed on $f"
          FAIL=1
        fi
        echo "  ruff check $f"
        if ! "$RUFF_BIN" check --config backend/pyproject.toml "$f" 2>&1; then
          echo "    ❌ ruff check failed on $f"
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
