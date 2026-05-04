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
pytest tests/unit/test_speaker_id_pipeline.py -v
pytest tests/unit/test_user_speaker_embedding.py -v
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
pytest tests/unit/test_conversation_render_factory.py -v
pytest tests/unit/test_conversation_redact_enrich.py -v
pytest tests/unit/test_folder_name_enrichment.py -v
pytest tests/unit/test_conversations_count.py -v
pytest tests/unit/test_prompt_cache_optimization.py -v
pytest tests/unit/test_prompt_cache_integration.py -v
pytest tests/unit/test_task_sharing.py -v
pytest tests/unit/test_firmware_pagination.py -v
pytest tests/unit/test_vad_gate.py -v
pytest tests/unit/test_vad_onnx.py -v
pytest tests/unit/test_log_sanitizer.py -v
pytest tests/unit/test_auth_redirect_uri.py -v
pytest tests/unit/test_pusher_heartbeat.py -v
pytest tests/unit/test_pusher_conversation_retry.py -v
pytest tests/unit/test_listen_fallback_removal.py -v
pytest tests/unit/test_desktop_updates.py -v
pytest tests/unit/test_translation_optimization.py -v
pytest tests/unit/test_translation_cost_optimization.py -v
pytest tests/unit/test_conversation_source_unknown.py -v
pytest tests/unit/test_conversation_model_split.py -v
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
pytest tests/unit/test_action_item_dedup.py -v
pytest tests/unit/test_tools_router.py -v
pytest tests/unit/test_kg_user_type_mismatch.py -v
pytest tests/unit/test_kg_edge_id_sanitization.py -v
pytest tests/unit/test_listen_pipeline.py -v
pytest tests/unit/test_fair_use_models.py -v
pytest tests/unit/test_fair_use_engine.py -v
pytest tests/unit/test_fair_use_classifier.py -v
pytest tests/unit/test_fair_use_async.py -v
pytest tests/unit/test_dg_usage_batch.py -v
pytest tests/unit/test_sync_fair_use_gate.py -v
pytest tests/unit/test_sync_pcm_decode.py -v
pytest tests/unit/test_sync_opus_decode.py -v
pytest tests/unit/test_sync_silent_failure.py -v
pytest tests/unit/test_fair_use_free_tier.py -v
pytest tests/unit/test_fair_use_upgrade.py -v
pytest tests/unit/test_skip_classifier_restrict.py -v
pytest tests/unit/test_timeout_middleware.py -v
pytest tests/unit/test_pusher_circuit_breaker.py -v
pytest tests/unit/test_lock_bypass_fixes.py -v
pytest tests/unit/test_dev_api_lock_bypass.py -v
pytest tests/unit/test_dev_api_folder_filters.py -v
pytest tests/unit/test_rate_limiting.py -v
pytest tests/unit/test_memories_batch.py -v
pytest tests/unit/test_memories_create.py -v
pytest tests/unit/test_sync_v2.py -v
pytest tests/unit/test_sync_transcription_prefs.py -v
pytest tests/unit/test_sync_record_usage.py -v
pytest tests/unit/test_vision_stream_async.py -v
pytest tests/unit/test_desktop_transcribe.py -v
pytest tests/unit/test_desktop_migration.py -v
pytest tests/unit/test_staged_tasks_batch_scores.py -v
pytest tests/unit/test_dg_start_guard.py -v
pytest tests/unit/test_available_plans_resilience.py -v
pytest tests/unit/test_subscription_restructure.py -v
pytest tests/unit/test_chat_quota.py -v
pytest tests/unit/test_subscription_plans.py -v
pytest tests/unit/test_payment_available_plans_source.py -v
pytest tests/unit/test_voice_duration_limiter.py -v
pytest tests/unit/test_async_webhooks.py -v
pytest tests/unit/test_async_app_integrations.py -v
pytest tests/unit/test_async_geocoding.py -v
pytest tests/unit/test_geocoding_cache.py -v
pytest tests/unit/test_realtime_integrations_usage_tracking.py -v
pytest tests/unit/test_async_auth.py -v
pytest tests/unit/test_auth_redirect_uri.py -v
pytest tests/unit/test_thread_join_elimination.py -v
pytest tests/unit/test_async_http_infrastructure.py -v
pytest tests/unit/test_clean_sweep_migrations.py -v
pytest tests/unit/test_omi_qos_tiers.py -v
pytest tests/unit/test_byok_security.py -v
pytest tests/unit/test_vertex_ai_system_role.py -v
pytest tests/unit/test_tts.py -v

# Fair-use integration tests (require Redis; skip gracefully if unavailable)
if redis-cli ping >/dev/null 2>&1; then
  pytest tests/integration/test_fair_use_live.py -v
  pytest tests/integration/test_fair_use_api.py -v
else
  echo "SKIP: fair-use integration tests (Redis not available)"
fi
