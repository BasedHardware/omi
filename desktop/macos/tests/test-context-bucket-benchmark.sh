#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../../.."
python3 desktop/macos/scripts/context-bucket-benchmark.py
