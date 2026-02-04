#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

export ENCRYPTION_SECRET="omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv"

pytest tests/unit/test_transcript_segment.py -v
pytest tests/unit/test_text_similarity.py -v
pytest tests/unit/test_text_containment.py -v
pytest tests/unit/test_speaker_sample.py -v
pytest tests/unit/test_speaker_sample_migration.py -v
pytest tests/unit/test_users_add_sample_transaction.py -v
pytest tests/unit/test_voice_message_language.py -v
pytest tests/unit/test_speaker_assignment.py -v
pytest tests/unit/test_memory_leak_buffers.py -v
