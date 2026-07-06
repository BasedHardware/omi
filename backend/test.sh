#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

export ENCRYPTION_SECRET="omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv"
export OPENAI_API_KEY="test-openai-key-not-real"

pytest() {
  "${PYTHON:-python3}" -m pytest "$@"
}

if [[ -n "${BACKEND_UNIT_TEST_FILE_LIST:-}" ]]; then
  if [[ ! -f "$BACKEND_UNIT_TEST_FILE_LIST" ]]; then
    echo "BACKEND_UNIT_TEST_FILE_LIST does not exist: $BACKEND_UNIT_TEST_FILE_LIST" >&2
    exit 1
  fi

  selected_tests=()
  while IFS= read -r test_path; do
    [[ -n "$test_path" ]] && selected_tests+=("$test_path")
  done < "$BACKEND_UNIT_TEST_FILE_LIST"

  if [[ ${#selected_tests[@]} -eq 0 ]]; then
    echo "No backend unit tests selected."
    exit 0
  fi

  echo "Running ${#selected_tests[@]} selected backend unit test file(s)."
  for test_path in "${selected_tests[@]}"; do
    pytest "$test_path" -v
  done
  exit 0
fi

# Fallback: hardcoded test list for local runs without BACKEND_UNIT_TEST_FILE_LIST.
# CI uses: scripts/select_backend_unit_tests.py --all
pytest tests/unit/test_transcript_segment.py -v
pytest tests/unit/test_import_job_status_detail_enum.py -v
pytest tests/unit/test_text_similarity.py -v
pytest tests/unit/test_text_containment.py -v
pytest tests/unit/test_speaker_sample.py -v
pytest tests/unit/test_speaker_sample_migration.py -v
pytest tests/unit/test_short_audio_embedding.py -v
pytest tests/unit/test_users_add_sample_transaction.py -v
pytest tests/unit/test_users_webhook_url_validation.py -v
pytest tests/unit/test_voice_message_language.py -v
pytest tests/unit/test_speaker_assignment.py -v
pytest tests/unit/test_speaker_id_pipeline.py -v
pytest tests/unit/test_user_speaker_embedding.py -v
pytest tests/unit/test_parakeet_diarization.py -v
pytest tests/unit/test_diarizer_embedding_decoder_bypass.py -v
pytest tests/unit/test_parakeet_prerecorded.py -v
pytest tests/unit/test_parakeet_nim.py -v
pytest tests/unit/test_parakeet_stream_session.py -v
pytest tests/unit/test_parakeet_gpu_worker.py -v
pytest tests/unit/test_parakeet_batch_engine.py -v
pytest tests/unit/test_flush_pending_batch1.py -v
pytest tests/unit/test_gpu_worker_submit_lock.py -v
pytest tests/unit/test_vram_batch.py -v
pytest tests/unit/test_oom_reproduction.py -v
pytest tests/unit/test_parakeet_batch_routing.py -v
pytest tests/unit/test_parakeet_builtin_embedding.py -v
pytest tests/unit/test_parakeet_endpoints.py -v
pytest tests/unit/test_audiobuffer_guard.py -v
pytest tests/unit/test_memory_leak_buffers.py -v
pytest tests/unit/test_mcp_search_memories.py -v
pytest tests/unit/test_mcp_search_conversations_poison.py -v
pytest tests/unit/test_mcp_memory_filters.py -v
pytest tests/unit/test_mcp_client_tool_result.py -v
pytest tests/unit/test_mcp_data_endpoints.py -v
pytest tests/unit/test_mcp_api_key_full_access.py -v
pytest tests/unit/test_mcp_oauth.py -v
pytest tests/unit/test_mcp_action_item_writes.py -v
pytest tests/unit/test_mcp_conversations_poison.py -v
pytest tests/unit/test_mcp_profile_contact.py -v
pytest tests/unit/test_memory_temporal_brain.py -v
pytest tests/unit/test_memory_category_auto.py -v
pytest tests/unit/test_memories_validation.py -v
pytest tests/unit/test_memory_domain.py -v
pytest tests/unit/test_memory_system_cohort.py -v
pytest tests/unit/test_canonical_memory_vectors.py -v
pytest tests/unit/test_ws_k_layer_field.py -v
pytest tests/unit/test_memory_service_parity.py -v
pytest tests/unit/test_ws_i_write_convergence.py -v
pytest tests/unit/test_ws_i_hardening.py -v
pytest tests/unit/test_ws_b_short_term_lifecycle.py -v
pytest tests/unit/test_canonical_consolidation.py -v
pytest tests/unit/test_canonical_consolidation_apply.py -v
pytest tests/unit/test_canonical_kg_promotion.py -v
pytest tests/unit/test_canonical_extraction_subject_wiring.py -v
pytest tests/unit/test_review_queue_cascade_purge.py -v
pytest tests/unit/test_canonical_maintenance_ordering.py -v
pytest tests/unit/test_canonical_short_term_maintenance_cron.py -v
pytest tests/unit/test_ws_c_backfill.py -v
pytest tests/unit/test_ws_j_delete_privacy.py -v
pytest tests/unit/test_ws_l_surface_routing.py -v
pytest tests/unit/test_ws_g_module_aliases.py -v
pytest tests/unit/test_ws_m_atom_keyword_index.py -v
pytest tests/unit/test_ws_n_graph_traversal.py -v
pytest tests/unit/test_upstream_boundary.py -v
pytest tests/unit/test_memories_user_review.py -v
pytest tests/unit/test_announcement_malformed_type.py -v
pytest tests/unit/test_short_term_lifecycle.py -v
pytest tests/unit/test_product_memory_items.py -v
pytest tests/unit/test_product_memory_read_service.py -v
pytest tests/unit/test_default_read_rollout_decision.py -v
pytest tests/unit/test_rollout_schema_readiness.py -v
pytest tests/unit/test_chat_memory_adapter.py -v
pytest tests/unit/test_chat_memory_tool_caller.py -v
pytest tests/unit/test_chat_session_normalize.py -v
pytest tests/unit/test_tools_agent_route_response_shape.py -v
pytest tests/unit/test_tools_rest_memory_runtime_adapter.py -v
pytest tests/unit/test_p1_5_tools_fastapi_testclient_readiness.py -v
pytest tests/unit/test_developer_memory_adapter.py -v
pytest tests/unit/test_mcp_memory_adapter.py -v
pytest tests/unit/test_product_memory_router.py -v
pytest tests/unit/test_product_authorization.py -v
pytest tests/unit/test_memory_app_key_grants.py -v
pytest tests/unit/test_app_key_memory_grant_assignment_readiness.py -v
pytest tests/unit/test_developer_auth_context_static.py -v
pytest tests/unit/test_mcp_auth_context_static.py -v
pytest tests/unit/test_mcp_api_key_auth_context.py -v
pytest tests/unit/test_mcp_api_key_scope_readiness.py -v
pytest tests/unit/test_mcp_oauth_template.py -v
pytest tests/unit/test_sync_firebase_google_provider_secret.py -v
pytest tests/unit/test_short_term_lifecycle_worker.py -v
pytest tests/unit/test_short_term_lifecycle_firestore_store.py -v
pytest tests/unit/test_memory_contracts.py -v
pytest tests/unit/test_working_observations_extractor.py -v
pytest tests/unit/test_durable_memory_patches.py -v
pytest tests/unit/test_patch_adapter.py -v
pytest tests/unit/test_memory_read_api.py -v
pytest tests/unit/test_projections.py -v
pytest tests/unit/test_vector_metadata.py -v
pytest tests/unit/test_vector_filters.py -v
pytest tests/unit/test_vector_search_service.py -v
pytest tests/unit/test_vector_repair_outbox_worker.py -v
pytest tests/unit/test_vector_repair_outbox_infra.py -v
pytest tests/unit/test_firestore_rules_iam_proof.py -v
pytest tests/unit/test_pinecone_repair_validation_readiness.py -v
pytest tests/unit/test_shared_ns2_legacy_isolation_readiness.py -v
pytest tests/unit/test_vector_search_provider_readiness.py -v
# /v3 router behavioral probes (replaces readiness gate framework).
pytest tests/unit/test_v3_fastapi_route_contract.py -v
pytest tests/unit/test_v3_get_dependency_auth.py -v
pytest tests/unit/test_v3_real_router_dependency_map.py -v
pytest tests/unit/test_v3_real_router_get_testclient.py -v
pytest tests/unit/test_v3_real_router_fail_closed_matrix.py -v
pytest tests/unit/test_v3_route_signature_integration.py -v
pytest tests/unit/test_v3_canary_approval_production_read.py -v
pytest tests/unit/test_v3_cursor_secret_production_read.py -v
pytest tests/unit/test_v3_projection_write_convergence_read.py -v
pytest tests/unit/test_v3_runtime_config_source_read.py -v
pytest tests/unit/test_v3_compatibility.py -v
pytest tests/unit/test_v3_cursor.py -v
pytest tests/unit/test_v3_projection_readiness.py -v
pytest tests/unit/test_v3_memory_read_service.py -v
pytest tests/unit/test_v3_write_convergence.py -v
pytest tests/unit/test_v3_response_adapter.py -v
pytest tests/unit/test_v3_request_adapter.py -v
pytest tests/unit/test_v3_route_planner.py -v
pytest tests/unit/test_v3_get_dependency_seam.py -v
pytest tests/unit/test_v3_archive_visibility_readiness.py -v
pytest tests/unit/test_v3_local_telemetry.py -v
# memory /v3 canary approval schema + fake-injectable reader readiness seam.
pytest tests/unit/test_v3_canary_approval_artifact.py -v
pytest tests/unit/test_v3_control_reader_contract.py -v
pytest tests/unit/test_v3_control_state_adapter.py -v
pytest tests/unit/test_v3_account_generation_source.py -v
pytest tests/unit/test_v3_compatibility_projection.py -v
pytest tests/unit/test_v3_production_runtime_wiring.py -v
pytest tests/unit/test_first_user_memory_tools.py -v
pytest tests/unit/test_v3_limited_rollout_config.py -v
pytest tests/unit/test_v3_f5_real_service_evidence_readiness.py -v
pytest tests/unit/test_v3_gcp_evidence_config.py -v
pytest tests/unit/test_v3_gcp_evidence_run_record.py -v
pytest tests/unit/test_v3_gcp_evidence_redaction.py -v
pytest tests/unit/test_v3_f6_readonly_contracts.py -v
pytest tests/unit/test_v3_f6_pre_gcp_aggregate.py -v
pytest tests/unit/test_v3_dev_cloud_readiness.py -v
pytest tests/unit/test_cutover_evidence_readiness.py -v
pytest tests/unit/test_firestore_indexes.py -v
pytest tests/unit/test_firestore_index_config.py -v
pytest tests/unit/test_normative_foundations.py -v
pytest tests/unit/test_typed_synthesis.py -v
pytest tests/unit/test_memory_operations.py -v
pytest tests/unit/test_atomic_apply.py -v
pytest tests/unit/test_memory_search_gateway.py -v
pytest tests/unit/test_memory_apply_store.py -v
pytest tests/unit/test_firestore_security_rules.py -v
pytest tests/unit/test_firestore_emulator_harness_wiring.py -v
pytest tests/unit/test_firestore_iam_deployment_doc.py -v
pytest tests/unit/test_non_active_routes.py -v
pytest tests/unit/test_non_active_route_audit.py -v
pytest tests/unit/test_non_active_route_report.py -v
pytest tests/unit/test_non_active_route_admin_endpoint.py -v
pytest tests/unit/test_review_queue_non_active_routes.py -v
pytest tests/unit/test_l2_promotion_agent_v2.py -v
pytest tests/unit/test_memory_tools.py -v
pytest tests/unit/test_memory_ingestion_pipeline.py -v
pytest tests/unit/test_working_memory_candidate_schema.py -v
pytest tests/unit/test_llm_gateway_service.py -v
pytest tests/unit/test_llm_gateway_config.py -v
pytest tests/unit/test_llm_gateway_auth.py -v
pytest tests/unit/test_llm_gateway_credentials.py -v
pytest tests/unit/test_llm_gateway_validator.py -v
pytest tests/unit/test_llm_gateway_resolver.py -v
pytest tests/unit/test_llm_gateway_executor.py -v
pytest tests/unit/test_llm_gateway_openai_provider.py -v
pytest tests/unit/test_llm_gateway_openai_compatible.py -v
pytest tests/unit/test_llm_gateway_readiness.py -v
pytest tests/unit/test_llm_gateway_client_config.py -v
pytest tests/unit/test_llm_gateway_route_refs.py -v
pytest tests/unit/test_llm_gateway_dependencies.py -v
pytest tests/unit/test_llm_gateway_chat_extraction_pilot.py -v
pytest tests/unit/test_llm_gateway_coverage_guardrails.py -v
pytest tests/unit/test_backend_runtime_env_validator.py -v
pytest tests/unit/test_render_backend_runtime_env.py -v
pytest tests/unit/test_google_credentials.py -v
pytest tests/unit/test_llm_usage_tracker.py -v
pytest tests/unit/test_llm_provider_plugin_structure.py -v
pytest tests/unit/test_process_conversation_usage_context.py -v
pytest tests/unit/test_high_priority_usage_tracking.py -v
pytest tests/unit/test_new_usage_tracking_gaps.py -v
pytest tests/unit/test_llm_usage_db.py -v
pytest tests/unit/test_user_usage.py -v
pytest tests/unit/test_llm_usage_endpoints.py -v
pytest tests/unit/test_app_uid_keyerror.py -v
pytest tests/unit/test_create_persona_user_none.py -v
pytest tests/unit/test_daily_summary_race_condition.py -v
pytest tests/unit/test_daily_summary_regenerate.py -v
pytest tests/unit/test_chat_tools_messages.py -v
pytest tests/unit/test_chat_tool_parameters_json.py -v
pytest tests/unit/test_prompt_caching.py -v
pytest tests/unit/test_mentor_notifications.py -v
# Canonical memory system tests (added with the new 2-layer runtime).
pytest tests/unit/test_claim_dedup.py -v
pytest tests/unit/test_client_device_provenance.py -v
pytest tests/unit/test_memory_ledger.py -v
pytest tests/unit/test_memory_rollout.py -v
pytest tests/unit/test_v3_composed_get_service.py -v
pytest tests/unit/test_v3_get_runtime_snapshot.py -v
pytest tests/unit/test_proactive_notification_language.py -v
pytest tests/unit/test_notification_token_cleanup.py -v
pytest tests/unit/test_integration_notification_validation.py -v
pytest tests/unit/test_conversations_to_string.py -v
pytest tests/unit/test_location_maps_status_guard.py -v
pytest tests/unit/test_conversation_render_factory.py -v
pytest tests/unit/test_conversation_redact_enrich.py -v
pytest tests/unit/test_retrieval_semantics.py -v
pytest tests/unit/test_folder_name_enrichment.py -v
pytest tests/unit/test_folder_conversations_malformed.py -v
pytest tests/unit/test_conversations_count.py -v
pytest tests/unit/test_calendar_autolink_invalid_timestamp.py -v
pytest tests/unit/test_prompt_cache_optimization.py -v
pytest tests/unit/test_prompt_cache_integration.py -v
pytest tests/unit/test_firestore_cache.py -v
pytest tests/unit/test_firestore_invariant_helpers.py -v
pytest tests/unit/test_task_sharing.py -v
pytest tests/unit/test_action_items_conversation_list_malformed.py -v
pytest tests/unit/test_firmware_pagination.py -v
pytest tests/unit/test_vad_gate.py -v
pytest tests/unit/test_vad_onnx.py -v
pytest tests/unit/test_log_sanitizer.py -v
pytest tests/unit/test_hume_callback_malformed.py -v
pytest tests/unit/test_file_upload_security.py -v
pytest tests/unit/test_file_upload_endpoint_security.py -v
pytest tests/unit/test_auth_redirect_uri.py -v
pytest tests/unit/test_pusher_heartbeat.py -v
pytest tests/unit/test_pusher_conversation_retry.py -v
pytest tests/unit/utils/test_listen_pusher_session.py -v
pytest tests/unit/test_listen_fallback_removal.py -v
pytest tests/unit/test_desktop_updates.py -v
pytest tests/unit/test_translation_optimization.py -v
pytest tests/unit/test_translation_cost_optimization.py -v
pytest tests/unit/test_translation_dedup_edge_cases.py -v
pytest tests/unit/test_conversation_source_unknown.py -v
pytest tests/unit/test_conversation_model_split.py -v
pytest tests/unit/test_transcribe_conversation_cache.py -v
pytest tests/unit/test_pusher_private_cloud_data_protection.py -v
pytest tests/unit/test_pusher_batch_upload.py -v
pytest tests/unit/test_storage_upload_audio_chunk_data_protection.py -v
pytest tests/unit/test_optional_audio_codecs.py -v
pytest tests/unit/test_storage_opus_encoding.py -v
pytest tests/unit/test_speech_profile_existence.py -v
pytest tests/unit/test_speech_profile_wav_decode.py -v
pytest tests/unit/test_storage_fanout_limits.py -v
pytest tests/unit/test_deferred_blob_janitor.py -v
pytest tests/unit/test_audio_merge_tasks.py -v
pytest tests/unit/test_sync_playback_service.py -v
pytest tests/unit/test_people_conversations_500s.py -v
pytest tests/unit/test_import_jobs_malformed.py -v
pytest tests/unit/test_firestore_read_ops_cache.py -v
pytest tests/unit/test_ws_auth_handshake.py -v
pytest tests/unit/test_streaming_deepgram_backoff.py -v
pytest tests/unit/test_executors.py -v
pytest tests/unit/test_modulate_stt.py -v
pytest tests/unit/test_batch_upload_storage.py -v
pytest tests/unit/test_action_item_date_validation.py -v
pytest tests/unit/test_request_validation_contracts.py -v
pytest tests/unit/test_conversation_structure_timezone.py -v
pytest tests/unit/test_action_item_dedup.py -v
pytest tests/unit/test_action_item_reminder_cancel_on_complete.py -v
pytest tests/unit/test_action_item_idempotency.py -v
pytest tests/unit/test_goals_id_fallback.py -v
pytest tests/unit/test_tools_router.py -v
pytest tests/unit/test_kg_user_type_mismatch.py -v
pytest tests/unit/test_kg_edge_id_sanitization.py -v
pytest tests/unit/test_kg_prune_memory_citations.py -v
pytest tests/unit/test_goal_extraction_batch.py -v
pytest tests/unit/test_listen_pipeline.py -v
pytest tests/unit/test_resample_pcm_divzero.py -v
pytest tests/unit/test_fair_use_models.py -v
pytest tests/unit/test_fair_use_flagged_limit_clamp.py -v
pytest tests/unit/test_fair_use_engine.py -v
pytest tests/unit/test_fair_use_classifier.py -v
pytest tests/unit/test_fair_use_async.py -v
pytest tests/unit/test_dg_usage_batch.py -v
pytest tests/unit/test_billable_transcription_seconds.py -v
pytest tests/unit/test_sync_fair_use_gate.py -v
pytest tests/unit/test_sync_pcm_decode.py -v
pytest tests/unit/test_sync_opus_decode.py -v
pytest tests/unit/test_transcribe_lc3_optional.py -v
pytest tests/unit/test_sync_silent_failure.py -v
pytest tests/unit/test_sync_ordered_assignment.py -v
pytest tests/unit/test_fair_use_free_tier.py -v
pytest tests/unit/test_fair_use_upgrade.py -v
pytest tests/unit/test_skip_classifier_restrict.py -v
pytest tests/unit/test_timeout_middleware.py -v
pytest tests/unit/test_pusher_circuit_breaker.py -v
pytest tests/unit/test_pusher_ghost_connections.py -v
pytest tests/unit/test_async_tasks.py -v
pytest tests/unit/test_async_resource_correctness.py -v
pytest tests/unit/test_hermetic_network.py -v
pytest tests/unit/test_hermetic_network_collection_guard.py -v
pytest tests/unit/test_lock_bypass_fixes.py -v
pytest tests/unit/test_integration_malformed_records.py -v
pytest tests/unit/test_oauth_callback_uid_guard.py -v
pytest tests/unit/test_dev_api_lock_bypass.py -v
pytest tests/unit/test_dev_api_folder_filters.py -v
pytest tests/unit/test_dev_api_conversations_poison.py -v
pytest tests/unit/test_dev_api_memories_pagination.py -v
pytest tests/unit/test_env_loader.py -v
pytest tests/unit/test_dev_api_action_items_poison.py -v
pytest tests/unit/test_rate_limiting.py -v
pytest tests/unit/test_rate_limit_json_failopen.py -v
pytest tests/unit/test_memories_batch.py -v
pytest tests/unit/test_memories_create.py -v
pytest tests/unit/test_per_file_import_guard.py -v
pytest tests/unit/test_memories_pagination_clamp.py -v
pytest tests/unit/test_sync_v2.py -v
pytest tests/unit/test_sync_file_paths_filename_none.py -v
pytest tests/unit/test_sync_cloud_tasks.py -v
pytest tests/unit/test_sync_transcription_prefs.py -v
pytest tests/unit/test_sync_record_usage.py -v
pytest tests/unit/test_vision_stream_async.py -v
pytest tests/unit/test_desktop_transcribe.py -v
pytest tests/unit/test_desktop_migration.py -v
pytest tests/unit/test_staged_tasks_batch_scores.py -v
pytest tests/unit/test_staged_tasks_dedup.py -v
pytest tests/unit/test_dg_start_guard.py -v
pytest tests/unit/test_available_plans_resilience.py -v
pytest tests/unit/test_subscription_restructure.py -v
pytest tests/unit/test_chat_quota.py -v
pytest tests/unit/test_voice_message_filename_none.py -v
pytest tests/unit/test_subscription_plans.py -v
pytest tests/unit/test_payment_available_plans_source.py -v
pytest tests/unit/test_payment_promotion_codes.py -v
pytest tests/unit/test_stripe_webhook_none_guard.py -v
pytest tests/unit/test_stripe_webhook_behavioral.py -v
pytest tests/unit/test_voice_duration_limiter.py -v
pytest tests/unit/test_async_webhooks.py -v
pytest tests/unit/test_async_app_integrations.py -v
pytest tests/unit/test_async_realtime_integrations_offload.py -v
pytest tests/unit/test_async_geocoding.py -v
pytest tests/unit/test_geocoding_cache.py -v
pytest tests/unit/test_realtime_integrations_usage_tracking.py -v
pytest tests/unit/test_async_auth.py -v
pytest tests/unit/test_thread_join_elimination.py -v
pytest tests/unit/test_async_http_infrastructure.py -v
pytest tests/unit/test_clean_sweep_migrations.py -v
pytest tests/unit/test_omi_qos_tiers.py -v
pytest tests/unit/test_byok_security.py -v
pytest tests/unit/test_paywall_reconnect_gate.py -v
pytest tests/unit/test_trial_metadata.py -v
pytest tests/unit/test_neo_desktop_grandfather.py -v
pytest tests/unit/test_vertex_ai_system_role.py -v
pytest tests/unit/test_tts.py -v
pytest tests/unit/test_webhook_auto_disable.py -v
pytest tests/unit/test_merge_validation.py -v
pytest tests/unit/test_phone_calls.py -v
pytest tests/unit/test_twilio_service.py -v
pytest tests/unit/test_twilio_account_deletion.py -v
pytest tests/unit/test_phone_verification_created_at.py -v
pytest tests/unit/test_conversation_search_date_validation.py -v
pytest tests/unit/test_conversation_events_bounds.py -v
pytest tests/unit/test_conversation_hybrid_search.py -v
pytest tests/unit/test_delete_account_stripe_cancel.py -v
pytest tests/unit/test_delete_account_purge_storage.py -v
pytest tests/unit/test_claim_deletion_wipe_txn.py -v
pytest tests/services/users/test_account_deletion.py -v
pytest tests/services/users/test_data_export.py -v
pytest tests/routers/test_users.py -v
pytest tests/unit/test_apps_review_reply_validation.py -v
pytest tests/unit/test_apps_create_app_json.py -v

# Fair-use integration tests (require Redis; skip gracefully if unavailable)
if redis-cli ping >/dev/null 2>&1; then
  pytest tests/integration/test_fair_use_live.py -v
  pytest tests/integration/test_fair_use_api.py -v
else
  echo "SKIP: fair-use integration tests (Redis not available)"
fi
