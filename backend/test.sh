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
pytest tests/unit/test_short_audio_embedding.py -v
pytest tests/unit/test_users_add_sample_transaction.py -v
pytest tests/unit/test_voice_message_language.py -v
pytest tests/unit/test_speaker_assignment.py -v
pytest tests/unit/test_memory_leak_buffers.py -v
pytest tests/unit/test_llm_usage_tracker.py -v
pytest tests/unit/test_process_conversation_usage_context.py -v
pytest tests/unit/test_llm_usage_db.py -v
pytest tests/unit/test_llm_usage_endpoints.py -v
pytest tests/unit/test_app_uid_keyerror.py -v
pytest tests/unit/test_daily_summary_race_condition.py -v
pytest tests/unit/test_chat_tools_messages.py -v
pytest tests/unit/test_prompt_caching.py -v
pytest tests/unit/test_mentor_notifications.py -v
pytest tests/unit/test_conversations_to_string.py -v
pytest tests/unit/test_prompt_cache_optimization.py -v
pytest tests/unit/test_prompt_cache_integration.py -v
pytest tests/unit/test_task_sharing.py -v
