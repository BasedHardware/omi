# AST query-coverage ratchet supersession proof

Generated against `origin/main` / `75a8877f1e217901878a2ae2dc538ae8a9c7581b` before retiring the AST coverage tool. The tool reported **132 serving rows**: 90 registered, 39 raw-unregistered, and 3 unsupported.
Its report also included 17 explicitly non-serving rows under scripts and tests; those are outside the serving guard contract.

## Registry declaration rows

Of the 90 registered rows, 81 are in `backend/database/firestore_index_registry.py`. These are `FirestoreQuerySpec`/index requirement declarations, not query execution sites: they describe shapes and generate the manifest. Serving builders call the specs; `test_firestore_query_shapes.py` records those runtime calls and asserts each serving shape is served and certain against the generated manifest. The AST tool matched declaration definitions to their own spec entries, which explains why the declarations have no driver key of their own. Every AST-reported registry declaration is listed here:

`mcp_conversation_cards_category_start_end`, `mcp_conversation_cards_category_end`, `mcp_conversation_cards_start`, `mcp_conversation_cards_category`, `mcp_conversation_cards_start_end`, `mcp_conversation_cards_end`, `mcp_conversation_cards_category_start`, `mcp_conversation_cards_all`, `task_attention_overrides_active_by_generation`, `candidates_generation_created`, `staged_tasks_legacy_conversation_recovery_by_id`, `memory_items_required_processing_by_capture`, `memory_items_consolidation_by_capture`, `memory_items_recent_rejected_feedback`, `memory_items_policy_expired_short_term_by_capture`, `memory_items_expiry_urgent_short_term_by_capture`, `memory_items_canonical_graph_read`, `memory_items_canonical_atlas_read`, `memory_items_universal_list_scan`, `daily_sweep_active_fact_subject`, `daily_sweep_active_fact_slot`, `daily_sweep_active_fact_entity`, `daily_sweep_active_fact_entity_slot`, `daily_sweep_active_fact_subject_content`, `daily_sweep_active_fact_entity_content`, `daily_sweep_onboarding_completed_users`, `daily_sweep_onboarding_device_completed_users`, `daily_sweep_onboarding_conversations`, `memories_universal_list_scan_updated_at`, `memories_universal_list_scan_created_at`, `memory_items_by_conversation_source`, `memory_items_superseded_by_canonical_target`, `memory_items_superseded_by_legacy_target`, `memory_items_expired_short_term_by_expiry`, `memory_items_expiry_urgent_short_term_by_stored_expiry`, `memory_outbox_due_by_availability`, `memory_outbox_expired_lease_by_event_type`, `memory_review_queue_by_fact`, `memory_review_queue_by_conflict`, `memory_review_queue_by_status_impact`, `memory_review_queue_by_impact`, `memory_review_queue_by_status_id`, `conversations_in_progress_by_finished_at`, `conversations_by_status_finished_after`, `conversations_discarded_created`, `conversations_count_discarded_created_range`, `conversations_recording_lineage`, `conversations_entity_timeline_completed`, `meetings_entity_timeline`, `screen_activity_entity_timeline`, `screen_activity_keyword_timestamp_range`, `action_items_completion_id_scan`, `action_items_canonical_completion_count`, `action_items_completed_due_range`, `action_items_created_range`, `memories_created_range`, `canonical_memories_captured_range`, `action_items_completed_created_range`, `chat_first_deferrals_due`, `chat_first_deferrals_by_subject`, `chat_first_transient_dead_letter_repair`, `chat_sessions_current_by_app`, `chat_sessions_current_by_app_created_at`, `messages_by_app_created_at`, `feedback_events_negative_by_created_at`, `conversation_finalization_jobs_meeting_receipts_due`, `hourly_usage_plan_attribution_month`, `hourly_usage_utc_day`, `conversation_finalization_jobs_oldest_nonterminal`, `conversations_first_open_folder_active_count`, `conversation_keyframe_jobs_device_state`, `screen_activity_keyframe_device_generation_timestamp`, `frame_vision_receipts_output_expiry`, `frame_requests_terminal_metadata_expiry`, `messages_by_session_created_at`, `users_signup_platform_signup_os_signup_at_range`, `conversations_created_range_day_zero`, `conversations_created_after_day_zero`, `daily_summary_recipients_by_hour_and_zone`, `conversations_smart_merge_preceding`, `conversation_photos_name_range_export`.

## Serving query execution sites outside the registry

The remaining 51 AST rows are execution sites. Every row resolves to a registered runtime driver or an explicit `COVERED_BY` relationship in `tests/support/firestore_query_driver_registry.py`. Driver runs call the real production function with its parameter profiles against `RecordingFirestore`; the guard rejects empty/unclassified captures, uncertain shapes, and any serving shape absent from generated composites or field overrides. The 3 unsupported AST rows are also covered by the runtime driver; AST inability to model their chain is not a runtime-coverage gap.

| AST site | Function | AST classification | AST id | Runtime recorder coverage |
|---|---|---|---|---|
| `backend/database/action_items.py:989` | `get_action_items_count_by_conversation` | raw_unregistered | `0e08215b6ef5f3a6` | `database.action_items.get_action_items_count_by_conversation` driver |
| `backend/database/action_items.py:1374` | `get_pending_apple_reminders_sync` | raw_unregistered | `db91448693d164b7` | `database.action_items.get_pending_apple_reminders_sync` driver |
| `backend/database/action_items.py:1465` | `get_daily_score` | raw_unregistered | `9fb243390e66c156` | `database.action_items.get_daily_score` driver |
| `backend/database/action_items.py:1521` | `get_scores` | raw_unregistered | `e45d7e1590250c2d` | `database.action_items.get_scores` driver |
| `backend/database/announcements.py:28` | `get_app_changelogs` | raw_unregistered | `d2226c85c73787cd` | `database.announcements.get_app_changelogs` driver |
| `backend/database/announcements.py:61` | `get_recent_changelogs` | raw_unregistered | `3897bd4019721e0e` | `database.announcements.get_recent_changelogs` driver |
| `backend/database/announcements.py:96` | `get_firmware_features` | raw_unregistered | `22ddf94e28ce6efc` | `database.announcements.get_firmware_features` driver |
| `backend/database/announcements.py:127` | `get_app_features` | raw_unregistered | `fbf6a1e1fdc6920e` | `database.announcements.get_app_features` driver |
| `backend/database/announcements.py:148` | `get_general_announcements` | raw_unregistered | `4697c32b6eda9c89` | `database.announcements.get_general_announcements` driver |
| `backend/database/candidate_integration_outbox.py:243` | `list_candidate_integration_dispatches` | raw_unregistered | `d79c3e5472a04da2` | `database.candidate_integration_outbox.list_candidate_integration_dispatches` driver |
| `backend/database/chat.py:215` | `get_app_messages` | raw_unregistered | `995a1232ca9f00f0` | `database.chat.get_app_messages` driver |
| `backend/database/chat.py:646` | `batch_delete_messages` | raw_unregistered | `05fdb282df637274` | `database.chat.batch_delete_messages` driver |
| `backend/database/chat.py:746` | `get_chat_files_desc` | raw_unregistered | `2a846099f82aa044` | `database.chat.get_chat_files_desc` driver |
| `backend/database/chat.py:1075` | `get_chat_sessions` | raw_unregistered | `d4cf7676519c097c` | `database.chat.get_chat_sessions` driver |
| `backend/database/chat.py:1077` | `get_chat_sessions` | raw_unregistered | `92c65999902cd6f2` | `database.chat.get_chat_sessions` driver |
| `backend/database/conversations.py:473` | `iter_all_conversation_photos` | registered | `94464b27cc4d608e` | `database.conversations.iter_all_conversation_photos` driver |
| `backend/database/conversations.py:1919` | `get_in_progress_conversation` | raw_unregistered | `4c64bf8ddb021ead` | `database.conversations.get_in_progress_conversation` driver |
| `backend/database/conversations.py:2239` | `get_action_items` | raw_unregistered | `fcb4a9e8a36ebd5e` | `database.conversations.get_action_items` driver |
| `backend/database/conversations.py:2241` | `get_action_items` | raw_unregistered | `766f4615b8337172` | `database.conversations.get_action_items` driver |
| `backend/database/conversations.py:2244` | `get_action_items` | raw_unregistered | `b0d377d6304ee36b` | `database.conversations.get_action_items` driver |
| `backend/database/conversations.py:3415` | `get_closest_conversation_to_timestamps` | raw_unregistered | `5e1801d8a93d95b2` | `database.conversations.get_closest_conversation_to_timestamps` driver |
| `backend/database/conversations.py:3445` | `get_last_completed_conversation` | raw_unregistered | `e056656ec5fc547a` | `database.conversations.get_last_completed_conversation` driver |
| `backend/database/folders.py:333` | `get_conversations_in_folder` | registered | `7974cb3672cd19e7` | `database.folders.get_conversations_in_folder` driver |
| `backend/database/folders.py:335` | `get_conversations_in_folder` | raw_unregistered | `d2bd1198af3f25a1` | `database.folders.get_conversations_in_folder` driver |
| `backend/database/folders.py:432` | `update_folder_conversation_count` | registered | `6349dbe884bdc903` | `database.folders.update_folder_conversation_count` driver |
| `backend/database/import_jobs.py:35` | `get_import_jobs` | raw_unregistered | `e50ee9d2d660185a` | `database.import_jobs.get_import_jobs` driver |
| `backend/database/memories.py:427` | `get_memories` | raw_unregistered | `9ce8173108a79e95` | `database.memories.get_memories` driver |
| `backend/database/memories.py:699` | `get_user_public_memories` | raw_unregistered | `24a4e24a308881dc` | `database.memories.get_user_public_memories` driver |
| `backend/database/memory_vector_repair_outbox_worker.py:231` | `lease_vector_repair_purge_outbox_records` | unsupported | `78e1f5ccede68267` | `database.memory_vector_repair_outbox_worker.lease_vector_repair_purge_outbox_records` driver |
| `backend/database/memory_vector_repair_outbox_worker.py:238` | `lease_vector_repair_purge_outbox_records` | unsupported | `7ff44f1f1a5597e9` | `database.memory_vector_repair_outbox_worker.lease_vector_repair_purge_outbox_records` driver |
| `backend/database/recurrence_inbox.py:133` | `list_pending_recurrence_receipts` | raw_unregistered | `ae20f1b2278c927e` | `database.recurrence_inbox.list_pending_recurrence_receipts` driver |
| `backend/database/screen_activity.py:128` | `get_screen_activity` | raw_unregistered | `a49ef54b849736d4` | `database.screen_activity.get_screen_activity` driver |
| `backend/database/screen_activity.py:131` | `get_screen_activity` | raw_unregistered | `d3f5a567b8a2363d` | `database.screen_activity.get_screen_activity` driver |
| `backend/database/screen_activity.py:133` | `get_screen_activity` | raw_unregistered | `5483ca63032ff8e5` | `database.screen_activity.get_screen_activity` driver |
| `backend/database/screen_activity.py:172` | `get_screen_activity_page` | raw_unregistered | `196fab68eca3c0bd` | `database.screen_activity.get_screen_activity_page` driver |
| `backend/database/screen_activity.py:176` | `get_screen_activity_page` | raw_unregistered | `1a56318e7178a385` | `database.screen_activity.get_screen_activity_page` driver |
| `backend/database/screen_activity.py:179` | `get_screen_activity_page` | raw_unregistered | `0db1e429b51f6e93` | `database.screen_activity.get_screen_activity_page` driver |
| `backend/database/screen_activity.py:181` | `get_screen_activity_page` | raw_unregistered | `1dc007241a935aac` | `database.screen_activity.get_screen_activity_page` driver |
| `backend/database/task_recommendations.py:298` | `save_projection` | raw_unregistered | `0c75b579eb9f7f04` | `database.task_recommendations.save_projection` driver |
| `backend/database/task_recommendations.py:633` | `_first_chain_record` | unsupported | `4a1b611f6580fc78` | covered by `database.task_recommendations.create_outcome` |
| `backend/database/task_recommendations.py:935` | `list_open_loop_snapshots` | raw_unregistered | `67648c7513966177` | `database.task_recommendations.list_open_loop_snapshots` driver |
| `backend/database/tasks.py:21` | `get_task_by_action_request` | raw_unregistered | `c7a018366f791dcd` | `database.tasks.get_task_by_action_request` driver |
| `backend/database/user_usage.py:318` | `get_usage_by_plan` | registered | `2437d945dc3f063f` | `database.user_usage.get_usage_by_plan` driver |
| `backend/database/user_usage.py:546` | `get_today_usage_stats` | registered | `103b55b9f0482db6` | `database.user_usage.get_today_usage_stats` driver |
| `backend/database/user_usage.py:594` | `get_monthly_usage_stats` | registered | `2e3df6553113f693` | `database.user_usage.get_monthly_usage_stats` driver |
| `backend/database/user_usage.py:608` | `get_monthly_usage_stats_since` | raw_unregistered | `a4f65460a9ad9a40` | `database.user_usage.get_monthly_usage_stats_since` driver |
| `backend/database/user_usage.py:686` | `_local_period_usage` | registered | `5cee0ce317cde930` | covered by `database.user_usage.get_current_user_usage` |
| `backend/database/user_usage.py:735` | `get_hourly_history_for_today` | registered | `92ddcc8ed8cf0e94` | `database.user_usage.get_hourly_history_for_today` driver |
| `backend/database/user_usage.py:769` | `get_daily_history_for_month` | registered | `db0f0af923c67e1a` | `database.user_usage.get_daily_history_for_month` driver |
| `backend/database/workstreams.py:368` | `list_open_workstreams` | raw_unregistered | `dba3e56194d22a9f` | `database.workstreams.list_open_workstreams` driver |
| `backend/database/workstreams.py:516` | `list_workstream_events` | raw_unregistered | `9f37fe9424a425d0` | `database.workstreams.list_workstream_events` driver |

## Replacement gates

- `tests/unit/test_firestore_query_shapes.py` covers discovered database query functions, driver/profile capture, covered-by observations, and zero unserved/uncertain serving shapes.
- `tests/unit/test_firestore_outside_query_contract.py` runs and validates non-database serving drivers and their witnesses.
- `backend/scripts/firestore_index_oracle.py` compares predictions with Firestore actual query planning when the `index-oracle` operation is run.
- The index workflow applies declared schema, and backend deploy readiness blocks while an index is not `READY`; the missing-index alert routes runtime misses to the runbook.

Conclusion: the AST coverage ratchet is fully superseded for serving query enforcement. Its cumulative registration counts and waivers are retired; `QUERY_SPECS` and `FirestoreQuerySpec` remain the serving query/index declaration mechanism.
