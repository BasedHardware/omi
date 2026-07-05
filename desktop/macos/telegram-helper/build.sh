#!/usr/bin/env bash
# Build the Omi Telegram helper into a single self-contained binary (no system
# Python needed at runtime) via PyInstaller. Output: dist/omi-telegram-helper.
#
# The macOS app bundles dist/omi-telegram-helper into its Resources and launches
# it as a subprocess (see TelegramClientService.swift). Codemagic runs this in CI
# and signs/notarizes the binary with the app.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

VENV=".venv-build"
PYTHON_BIN="${PYTHON:-python3}"

"$PYTHON_BIN" -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install --upgrade pip >/dev/null
pip install -r requirements.txt pyinstaller >/dev/null

pyinstaller \
  --onefile \
  --name omi-telegram-helper \
  --clean \
  --noconfirm \
  omi_telegram_helper.py

echo "Built: $ROOT_DIR/dist/omi-telegram-helper"
