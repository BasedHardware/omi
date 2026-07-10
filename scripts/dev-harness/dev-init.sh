#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."

echo "Omi local dev harness — one-time setup"

secrets_file="backend/.env.local-dev"
template="backend/.env.local-dev.template"
if [ ! -f "$secrets_file" ]; then
  cp "$template" "$secrets_file"
  echo "Created $secrets_file from template"
else
  echo "Keeping existing $secrets_file (not overwritten)"
fi

if [ ! -d backend/venv ]; then
  python3 -m venv backend/venv
  echo "Created backend/venv"
fi

if [ ! -x backend/venv/bin/pip ]; then
  echo "backend/venv is incomplete; recreate it with: python3 -m venv backend/venv" >&2
  exit 1
fi

backend/venv/bin/pip install -q -r backend/requirements.txt
echo "Backend Python dependencies installed"

hook=".git/hooks/pre-commit"
if [ ! -f "$hook" ]; then
  ln -s -f ../../scripts/pre-commit "$hook"
  echo "Installed pre-commit hook"
else
  echo "Pre-commit hook already present"
fi

echo ""
echo "Next: add your four API keys to backend/.env.local-dev, then run:"
echo "  make dev-desktop"
