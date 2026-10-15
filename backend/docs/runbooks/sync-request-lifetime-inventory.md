# Request-lifetime producer inventory

Static source inventory for the shared app and sync-reachable producers, 2026-10-04. Conditional calls are not proof of live execution. This is a conservative safety inventory; normal awaited child work and request-owned heartbeats remain distinct from fire-and-forget effects. The shared app registers other routers too: existing blockers suffice to reject request billing, and a future switch requires a full service-role boundary audit.

| Source | Enclosing function | Producer | Target |
| --- | --- | --- | --- |
| `backend/main.py:356` | `startup_event` | `start_background_task` | `live_stt_health.refresh_forever()` |
| `backend/main.py:359` | `startup_event` | `start_background_task` | `poll_forever()` |
| `backend/main.py:362` | `startup_event` | `start_background_task` | `log_executor_health()` |
| `backend/main.py:365` | `startup_event` | `start_background_task` | `run_blocking(db_executor, _drain_pending_deletion_wipes)` |
| `backend/main.py:371` | `startup_event` | `start_background_task` | `_periodic_deletion_wipe_reconcile()` |
| `backend/main.py:372` | `startup_event` | `start_background_task` | `run_blocking(db_executor, _drain_listen_finalization_jobs)` |
| `backend/main.py:376` | `startup_event` | `start_background_task` | `run_blocking(db_executor, _drain_stale_processing_conversations)` |
| `backend/main.py:380` | `startup_event` | `start_background_task` | `run_blocking(db_executor, _drain_stale_in_progress_conversations)` |
| `backend/main.py:384` | `startup_event` | `start_background_task` | `run_blocking(db_executor, _drain_abandoned_byok_finalization_jobs)` |
| `backend/main.py:388` | `startup_event` | `start_background_task` | `run_blocking(db_executor, _drain_meeting_receipts)` |
| `backend/main.py:392` | `startup_event` | `start_background_task` | `_periodic_listen_finalization_reconcile()` |
| `backend/main.py:393` | `startup_event` | `start_background_task` | `proactive_message_dispatcher()` |
| `backend/routers/sync.py:702` | `sync_local_files` | `start_background_task` | `trigger_classifier_if_needed(uid, triggered_caps)` |
| `backend/routers/sync.py:800` | `sync_local_files` | `schedule_person_voice_learning_retries` | `uid` |
| `backend/routers/sync.py:1483` | `sync_local_files_v2` | `start_background_task` | `_run_full_pipeline_background_async(job_id, uid, owned_paths, source, should_lock, job_dir, conversation_id, geolocation=geolocation, client` |
| `backend/routers/sync.py:1865` | `run_sync_job` | `start_background_task` | `_maintain_uid_sequencer_lease(uid, job_id, epoch, stop, asyncio.current_task())` |
| `backend/utils/sync/pipeline.py:1085` | `_reprocess_conversation_after_update` | `submit_with_context` | `_run_conversation_created_webhook` |
| `backend/utils/sync/pipeline.py:1979` | `_run_full_pipeline_background_async` | `start_background_task` | `_maintain_inline_run_lease(job_id, inline_run_lock_token, inline_lease_stop_event, inline_lease_lost_event, owner_task)` |
| `backend/utils/sync/pipeline.py:2370` | `_run_full_pipeline_background_async` | `start_background_task` | `trigger_classifier_if_needed(uid, triggered_caps)` |
| `backend/utils/sync/pipeline.py:2730` | `_run_full_pipeline_background_async` | `schedule_person_voice_learning_retries` | `uid` |
| `backend/utils/sync/playback.py:130` | `_run_parallel_precache` | `submit_with_context` | `precache_audio_file` |
| `backend/utils/sync/playback.py:157` | `precache_audio_files` | `submit_with_context` | `_precache_all_parallel` |
| `backend/utils/sync/playback.py:324` | `_get_audio_urls_inline` | `submit_with_context` | `_cache_uncached_parallel` |
| `backend/utils/other/deferred_delete.py:41` | `schedule` | `threading.Thread` | `self._run` |
| `backend/utils/conversations/process_conversation.py:1038` | `trigger_conversation_apps` | `submit_with_context` | `execute_app` |
| `backend/utils/conversations/process_conversation.py:2246` | `_write_action_items` | `submit_with_context` | `_run_auto_sync` |
| `backend/utils/conversations/process_conversation.py:2251` | `_write_action_items` | `submit_with_context` | `_run_auto_sync` |
| `backend/utils/conversations/process_conversation.py:3291` | `_emit_derived_effects` | `submit_with_context` | `save_structured_vector` |
| `backend/utils/conversations/process_conversation.py:3293` | `_emit_derived_effects` | `submit_with_context` | `save_transcript_chunk_vectors` |
| `backend/utils/conversations/process_conversation.py:3305` | `_emit_derived_effects` | `submit_with_context` | `_save_action_items` |
| `backend/utils/conversations/process_conversation.py:3310` | `_emit_derived_effects` | `submit_with_context` | `update_goal_progress` |
| `backend/utils/conversations/process_conversation.py:3342` | `_emit_derived_effects` | `submit_with_context` | `_run_webhook` |
| `backend/utils/conversations/lifecycle.py:348` | `processing_admission_guard` | `threading.Thread` | `_run_processing_lease_heartbeat` |
| `backend/utils/conversations/capture_jev_shadow.py:369` | `_submit` | `submit_with_context` | `_run` |
| `backend/utils/conversations/jev_shadow.py:138` | `_submit` | `submit_with_context` | `_run` |
| `backend/utils/conversations/transcription_shadow.py:47` | `<module>` | `ThreadPoolExecutor` | `` |
| `backend/utils/conversations/transcription_shadow.py:125` | `maybe_start_shadow` | `start_background_task` | `_run_later(uid, conversation.id)` |
| `backend/utils/stt/live_health.py:394` | `launch` | `start_background_task` | `coroutine` |
| `backend/utils/stt/live_health.py:545` | `launch` | `start_background_task` | `coroutine` |
| `backend/utils/stt/batch_pressure.py:73` | `start` | `start_background_task` | `self._refresh_forever(pool_host, min_replicas)` |
| `backend/utils/metrics.py:1379` | `start_metrics_sidecar_server` | `start_http_server` | `port` |
