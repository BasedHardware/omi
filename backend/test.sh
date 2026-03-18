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
pytest tests/unit/test_firmware_pagination.py -v
pytest tests/unit/test_vad_gate.py -v
pytest tests/unit/test_log_sanitizer.py -v
pytest tests/unit/test_pusher_heartbeat.py -v
pytest tests/unit/test_pusher_conversation_retry.py -v
pytest tests/unit/test_desktop_updates.py -v
pytest tests/unit/test_translation_optimization.py -v
pytest tests/unit/test_conversation_source_unknown.py -v
pytest tests/unit/test_transcribe_conversation_cache.py -v
pytest tests/unit/test_pusher_private_cloud_data_protection.py -v
pytest tests/unit/test_pusher_batch_upload.py -v
pytest tests/unit/test_storage_upload_audio_chunk_data_protection.py -v
pytest tests/unit/test_storage_opus_encoding.py -v
pytest tests/unit/test_people_conversations_500s.py -v
pytest tests/unit/test_firestore_read_ops_cache.py -v
pytest tests/unit/test_ws_auth_handshake.py -v
pytest tests/unit/test_streaming_deepgram_backoff.py -v
pytest tests/unit/test_batch_upload_storage.py -v
pytest tests/unit/test_action_item_date_validation.py -v
pytest tests/unit/test_kg_user_type_mismatch.py -v
pytest tests/unit/test_kg_edge_id_sanitization.py -v
pytest tests/unit/test_listen_pipeline.py -v
pytest tests/unit/test_fair_use_models.py -v
pytest tests/unit/test_fair_use_engine.py -v
pytest tests/unit/test_fair_use_classifier.py -v
pytest tests/unit/test_fair_use_async.py -v

# Fair-use integration tests (require Redis; skip gracefully if unavailable)
if redis-cli ping >/dev/null 2>&1; then
  pytest tests/integration/test_fair_use_live.py -v
  pytest tests/integration/test_fair_use_api.py -v
else
  echo "SKIP: fair-use integration tests (Redis not available)"
fi
