#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

export ENCRYPTION_SECRET="omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv"

failed_tests=()

run_pytest() {
  local test_path="$1"
  shift

  echo
  echo "----------------------------------------"
  echo "Running $test_path"
  echo "----------------------------------------"

  if ! pytest "$test_path" "$@"; then
    failed_tests+=("$test_path")
  fi
}

finish_test_run() {
  echo
  echo "----------------------------------------"
  if [[ ${#failed_tests[@]} -eq 0 ]]; then
    echo "All backend tests passed."
    exit 0
  fi

  echo "Backend test failures (${#failed_tests[@]}):"
  printf '  - %s\n' "${failed_tests[@]}"
  exit 1
}

run_pytest tests/unit/test_transcript_segment.py -v
run_pytest tests/unit/test_import_job_status_detail_enum.py -v
run_pytest tests/unit/test_text_similarity.py -v
run_pytest tests/unit/test_text_containment.py -v
run_pytest tests/unit/test_speaker_sample.py -v
run_pytest tests/unit/test_speaker_sample_migration.py -v
run_pytest tests/unit/test_short_audio_embedding.py -v
run_pytest tests/unit/test_users_add_sample_transaction.py -v
run_pytest tests/unit/test_users_webhook_url_validation.py -v
run_pytest tests/unit/test_users_missing_doc_guards.py -v
run_pytest tests/unit/test_voice_message_language.py -v
run_pytest tests/unit/test_speaker_assignment.py -v
run_pytest tests/unit/test_speaker_id_pipeline.py -v
run_pytest tests/unit/test_user_speaker_embedding.py -v
run_pytest tests/unit/test_parakeet_diarization.py -v
run_pytest tests/unit/test_diarizer_embedding_decoder_bypass.py -v
run_pytest tests/unit/test_parakeet_prerecorded.py -v
run_pytest tests/unit/test_parakeet_nim.py -v
run_pytest tests/unit/test_parakeet_stream_session.py -v
run_pytest tests/unit/test_parakeet_gpu_worker.py -v
run_pytest tests/unit/test_parakeet_batch_engine.py -v
run_pytest tests/unit/test_parakeet_batch_routing.py -v
run_pytest tests/unit/test_parakeet_builtin_embedding.py -v
run_pytest tests/unit/test_parakeet_endpoints.py -v
run_pytest tests/unit/test_audiobuffer_guard.py -v
run_pytest tests/unit/test_memory_leak_buffers.py -v
run_pytest tests/unit/test_hermetic_network.py -v
run_pytest tests/unit/test_hermetic_network_collection_guard.py -v
run_pytest tests/unit/test_mcp_search_memories.py -v
run_pytest tests/unit/test_mcp_search_conversations_poison.py -v
run_pytest tests/unit/test_mcp_memory_filters.py -v
run_pytest tests/unit/test_mcp_client_tool_result.py -v
run_pytest tests/unit/test_mcp_data_endpoints.py -v
run_pytest tests/unit/test_mcp_oauth.py -v
run_pytest tests/unit/test_mcp_action_item_writes.py -v
run_pytest tests/unit/test_mcp_conversations_poison.py -v
run_pytest tests/unit/test_mcp_profile_contact.py -v
run_pytest tests/unit/test_memory_temporal_brain.py -v
run_pytest tests/unit/test_memory_category_auto.py -v
run_pytest tests/unit/test_memories_validation.py -v
run_pytest tests/unit/test_memories_user_review.py -v
run_pytest tests/unit/test_announcement_malformed_type.py -v
run_pytest tests/unit/test_llm_gateway_service.py -v
run_pytest tests/unit/test_llm_gateway_config.py -v
run_pytest tests/unit/test_llm_gateway_auth.py -v
run_pytest tests/unit/test_llm_gateway_credentials.py -v
run_pytest tests/unit/test_llm_gateway_validator.py -v
run_pytest tests/unit/test_llm_gateway_resolver.py -v
run_pytest tests/unit/test_llm_gateway_executor.py -v
run_pytest tests/unit/test_llm_gateway_openai_provider.py -v
run_pytest tests/unit/test_llm_gateway_openai_compatible.py -v
run_pytest tests/unit/test_llm_gateway_readiness.py -v
run_pytest tests/unit/test_llm_gateway_client_config.py -v
run_pytest tests/unit/test_llm_gateway_route_refs.py -v
run_pytest tests/unit/test_llm_gateway_dependencies.py -v
run_pytest tests/unit/test_llm_gateway_chat_extraction_pilot.py -v
run_pytest tests/unit/test_backend_runtime_env_validator.py -v
run_pytest tests/unit/test_llm_usage_tracker.py -v
run_pytest tests/unit/test_llm_provider_plugin_structure.py -v
run_pytest tests/unit/test_process_conversation_usage_context.py -v
run_pytest tests/unit/test_high_priority_usage_tracking.py -v
run_pytest tests/unit/test_new_usage_tracking_gaps.py -v
run_pytest tests/unit/test_llm_usage_db.py -v
run_pytest tests/unit/test_user_usage.py -v
run_pytest tests/unit/test_llm_usage_endpoints.py -v
run_pytest tests/unit/test_app_uid_keyerror.py -v
run_pytest tests/unit/test_create_persona_user_none.py -v
run_pytest tests/unit/test_daily_summary_race_condition.py -v
run_pytest tests/unit/test_daily_summary_regenerate.py -v
run_pytest tests/unit/test_chat_tools_messages.py -v
run_pytest tests/unit/test_chat_tool_parameters_json.py -v
run_pytest tests/unit/test_prompt_caching.py -v
run_pytest tests/unit/test_mentor_notifications.py -v
run_pytest tests/unit/test_proactive_notification_language.py -v
run_pytest tests/unit/test_advice_update_missing_doc_guard.py -v
run_pytest tests/unit/test_notification_token_cleanup.py -v
run_pytest tests/unit/test_integration_notification_validation.py -v
run_pytest tests/unit/test_conversations_to_string.py -v
run_pytest tests/unit/test_location_maps_status_guard.py -v
run_pytest tests/unit/test_conversation_render_factory.py -v
run_pytest tests/unit/test_conversation_redact_enrich.py -v
run_pytest tests/unit/test_retrieval_semantics.py -v
run_pytest tests/unit/test_screen_activity_search_utc.py -v
run_pytest tests/unit/test_conversation_tool_date_range_bound.py -v
run_pytest tests/unit/test_retrieval_result_bounds.py -v
run_pytest tests/unit/test_folder_name_enrichment.py -v
run_pytest tests/unit/test_folder_conversations_malformed.py -v
run_pytest tests/unit/test_conversations_count.py -v
run_pytest tests/unit/test_conversations_date_range_validation.py -v
run_pytest tests/unit/test_calendar_autolink_invalid_timestamp.py -v
run_pytest tests/unit/test_calendar_timezone.py -v
run_pytest tests/unit/test_prompt_cache_optimization.py -v
run_pytest tests/unit/test_prompt_cache_integration.py -v
run_pytest tests/unit/test_firestore_cache.py -v
run_pytest tests/unit/test_firestore_invariant_helpers.py -v
run_pytest tests/unit/test_task_sharing.py -v
run_pytest tests/unit/test_action_items_conversation_list_malformed.py -v
run_pytest tests/unit/test_firmware_pagination.py -v
run_pytest tests/unit/test_vad_gate.py -v
run_pytest tests/unit/test_vad_onnx.py -v
run_pytest tests/unit/test_log_sanitizer.py -v
run_pytest tests/unit/test_hume_callback_malformed.py -v
run_pytest tests/unit/test_file_upload_security.py -v
run_pytest tests/unit/test_file_upload_endpoint_security.py -v
run_pytest tests/unit/test_auth_redirect_uri.py -v
run_pytest tests/unit/test_pusher_heartbeat.py -v
run_pytest tests/unit/test_pusher_conversation_retry.py -v
run_pytest tests/unit/utils/test_listen_pusher_session.py -v
run_pytest tests/unit/test_listen_fallback_removal.py -v
run_pytest tests/unit/test_desktop_updates.py -v
run_pytest tests/unit/test_translation_optimization.py -v
run_pytest tests/unit/test_translation_cost_optimization.py -v
run_pytest tests/unit/test_translation_dedup_edge_cases.py -v
run_pytest tests/unit/test_conversation_source_unknown.py -v
run_pytest tests/unit/test_conversation_model_split.py -v
run_pytest tests/unit/test_transcribe_conversation_cache.py -v
run_pytest tests/unit/test_pusher_private_cloud_data_protection.py -v
run_pytest tests/unit/test_pusher_batch_upload.py -v
run_pytest tests/unit/test_storage_upload_audio_chunk_data_protection.py -v
run_pytest tests/unit/test_optional_audio_codecs.py -v
run_pytest tests/unit/test_storage_opus_encoding.py -v
run_pytest tests/unit/test_speech_profile_existence.py -v
run_pytest tests/unit/test_speech_profile_wav_decode.py -v
run_pytest tests/unit/test_storage_fanout_limits.py -v
run_pytest tests/unit/test_deferred_blob_janitor.py -v
run_pytest tests/unit/test_audio_merge_tasks.py -v
run_pytest tests/unit/test_sync_playback_service.py -v
run_pytest tests/unit/test_people_conversations_500s.py -v
run_pytest tests/unit/test_import_jobs_malformed.py -v
run_pytest tests/unit/test_firestore_read_ops_cache.py -v
run_pytest tests/unit/test_ws_auth_handshake.py -v
run_pytest tests/unit/test_streaming_deepgram_backoff.py -v
run_pytest tests/unit/test_executors.py -v
run_pytest tests/unit/test_task_integrations_async_offload.py -v
run_pytest tests/unit/test_modulate_stt.py -v
run_pytest tests/unit/test_batch_upload_storage.py -v
run_pytest tests/unit/test_action_item_date_validation.py -v
run_pytest tests/unit/test_action_items_date_range_validation.py -v
run_pytest tests/unit/test_action_items_timezone.py -v
run_pytest tests/unit/test_request_validation_contracts.py -v
run_pytest tests/unit/test_conversation_structure_timezone.py -v
run_pytest tests/unit/test_action_item_dedup.py -v
run_pytest tests/unit/test_action_item_reminder_cancel_on_complete.py -v
run_pytest tests/unit/test_action_item_idempotency.py -v
run_pytest tests/unit/test_goals_id_fallback.py -v
run_pytest tests/unit/test_tools_router.py -v
run_pytest tests/unit/test_kg_user_type_mismatch.py -v
run_pytest tests/unit/test_kg_edge_id_sanitization.py -v
run_pytest tests/unit/test_goal_extraction_batch.py -v
run_pytest tests/unit/test_listen_pipeline.py -v
run_pytest tests/unit/test_resample_pcm_divzero.py -v
run_pytest tests/unit/test_fair_use_models.py -v
run_pytest tests/unit/test_fair_use_flagged_limit_clamp.py -v
run_pytest tests/unit/test_fair_use_engine.py -v
run_pytest tests/unit/test_fair_use_classifier.py -v
run_pytest tests/unit/test_fair_use_async.py -v
run_pytest tests/unit/test_dg_usage_batch.py -v
run_pytest tests/unit/test_billable_transcription_seconds.py -v
run_pytest tests/unit/test_sync_fair_use_gate.py -v
run_pytest tests/unit/test_sync_pcm_decode.py -v
run_pytest tests/unit/test_sync_opus_decode.py -v
run_pytest tests/unit/test_transcribe_lc3_optional.py -v
run_pytest tests/unit/test_sync_silent_failure.py -v
run_pytest tests/unit/test_sync_ordered_assignment.py -v
run_pytest tests/unit/test_fair_use_free_tier.py -v
run_pytest tests/unit/test_fair_use_upgrade.py -v
run_pytest tests/unit/test_skip_classifier_restrict.py -v
run_pytest tests/unit/test_timeout_middleware.py -v
run_pytest tests/unit/test_pusher_circuit_breaker.py -v
run_pytest tests/unit/test_pusher_ghost_connections.py -v
run_pytest tests/unit/test_async_tasks.py -v
run_pytest tests/unit/test_async_resource_correctness.py -v
run_pytest tests/unit/test_lock_bypass_fixes.py -v
run_pytest tests/unit/test_integration_malformed_records.py -v
run_pytest tests/unit/test_oauth_callback_uid_guard.py -v
run_pytest tests/unit/test_dev_api_lock_bypass.py -v
run_pytest tests/unit/test_dev_api_folder_filters.py -v
run_pytest tests/unit/test_dev_api_conversations_poison.py -v
run_pytest tests/unit/test_developer_from_segments_idempotency.py -v
run_pytest tests/unit/test_dev_api_memories_pagination.py -v
run_pytest tests/unit/test_dev_api_action_items_poison.py -v
run_pytest tests/unit/test_rate_limiting.py -v
run_pytest tests/unit/test_rate_limit_json_failopen.py -v
run_pytest tests/unit/test_memories_batch.py -v
run_pytest tests/unit/test_memories_create.py -v
run_pytest tests/unit/test_memories_pagination_clamp.py -v
run_pytest tests/unit/test_sync_v2.py -v
run_pytest tests/unit/test_sync_file_paths_filename_none.py -v
run_pytest tests/unit/test_sync_cloud_tasks.py -v
run_pytest tests/unit/test_sync_transcription_prefs.py -v
run_pytest tests/unit/test_sync_record_usage.py -v
run_pytest tests/unit/test_vision_stream_async.py -v
run_pytest tests/unit/test_desktop_transcribe.py -v
run_pytest tests/unit/test_desktop_migration.py -v
run_pytest tests/unit/test_staged_tasks_batch_scores.py -v
run_pytest tests/unit/test_staged_tasks_dedup.py -v
run_pytest tests/unit/test_dg_start_guard.py -v
run_pytest tests/unit/test_available_plans_resilience.py -v
run_pytest tests/unit/test_subscription_restructure.py -v
run_pytest tests/unit/test_chat_quota.py -v
run_pytest tests/unit/test_voice_message_filename_none.py -v
run_pytest tests/unit/test_subscription_plans.py -v
run_pytest tests/unit/test_payment_available_plans_source.py -v
run_pytest tests/unit/test_payment_reactivation_billing_date_utc.py -v
run_pytest tests/unit/test_payment_promotion_codes.py -v
run_pytest tests/unit/test_payment_connect_account_user_guard.py -v
run_pytest tests/unit/test_stripe_webhook_none_guard.py -v
run_pytest tests/unit/test_stripe_webhook_behavioral.py -v
run_pytest tests/unit/test_voice_duration_limiter.py -v
run_pytest tests/unit/test_async_webhooks.py -v
run_pytest tests/unit/test_async_app_integrations.py -v
run_pytest tests/unit/test_async_realtime_integrations_offload.py -v
run_pytest tests/unit/test_async_geocoding.py -v
run_pytest tests/unit/test_geocoding_cache.py -v
run_pytest tests/unit/test_realtime_integrations_usage_tracking.py -v
run_pytest tests/unit/test_async_auth.py -v
run_pytest tests/unit/test_thread_join_elimination.py -v
run_pytest tests/unit/test_async_http_infrastructure.py -v
run_pytest tests/unit/test_clean_sweep_migrations.py -v
run_pytest tests/unit/test_omi_qos_tiers.py -v
run_pytest tests/unit/test_byok_security.py -v
run_pytest tests/unit/test_paywall_reconnect_gate.py -v
run_pytest tests/unit/test_trial_metadata.py -v
run_pytest tests/unit/test_neo_desktop_grandfather.py -v
run_pytest tests/unit/test_vertex_ai_system_role.py -v
run_pytest tests/unit/test_tts.py -v
run_pytest tests/unit/test_webhook_auto_disable.py -v
run_pytest tests/unit/test_merge_validation.py -v
run_pytest tests/unit/test_phone_calls.py -v
run_pytest tests/unit/test_twilio_service.py -v
run_pytest tests/unit/test_twilio_account_deletion.py -v
run_pytest tests/unit/test_phone_verification_created_at.py -v
run_pytest tests/unit/test_conversation_search_date_validation.py -v
run_pytest tests/unit/test_conversation_events_bounds.py -v
run_pytest tests/unit/test_conversation_hybrid_search.py -v
run_pytest tests/unit/test_delete_account_stripe_cancel.py -v
run_pytest tests/unit/test_delete_account_purge_storage.py -v
run_pytest tests/unit/test_claim_deletion_wipe_txn.py -v
run_pytest tests/services/users/test_account_deletion.py -v
run_pytest tests/services/users/test_data_export.py -v
run_pytest tests/routers/test_users.py -v
run_pytest tests/unit/test_apps_review_reply_validation.py -v
run_pytest tests/unit/test_apps_create_app_json.py -v
run_pytest tests/unit/test_app_visibility_missing_doc_guard.py -v

# Optional fair-use integration tests require Redis and are intentionally outside
# the deterministic unit signal.
if [[ "${RUN_BACKEND_INTEGRATION_TESTS:-0}" == "1" ]]; then
  if command -v redis-cli >/dev/null 2>&1 && redis-cli ping >/dev/null 2>&1; then
    run_pytest tests/integration/test_fair_use_live.py -v
    run_pytest tests/integration/test_fair_use_api.py -v
  else
    echo "SKIP: fair-use integration tests (Redis not available)"
  fi
else
  echo "SKIP: fair-use integration tests (set RUN_BACKEND_INTEGRATION_TESTS=1 to enable)"
fi

run_pytest tests/unit/test_migrate_memories_rekey.py -v
finish_test_run
