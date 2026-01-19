#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

pytest tests/unit/test_transcript_segment.py -v
pytest tests/unit/test_text_similarity.py -v
