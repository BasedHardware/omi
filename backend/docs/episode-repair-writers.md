# Episode repair source-writer coverage (round 5)

Audited 2026-11-05 for BasedHardware/omi PR #24607. Paths below are relative to
`backend/`. This inventories storage writers, including generic adapters and
maintenance tools; lifecycle/services/routers that call those primitives inherit
the same protection. The proof is independent of capture delivery, application
version fields, and whether a writer changes a Home-selected field.

- **C**: `home_read.read_members` records each exact conversation snapshot's
  document path and SDK `update_time`, including absent, hidden and unreadable
  members. `reconcile.verify` batch-reads those paths **inside publication's
  transaction**, before any write, and compares versions. Edit/delete/recreate,
  or creation of a previously missing member, rejects stale publication. Later
  writes serialize against those transactional reads. This covers the entire
  document, even when the initial read selected only Home fields.
- **E/L/R**: `reconcile.source_documents` records and transactionally re-queries
  `episodes`, `episode_links`, `episode_segment_receipts` and each declared `s`
  archive shard, comparing SDK versions and path sets. This also detects source
  insertion/deletion and receipt-shard-count changes.
- The owner epoch, lease, dirty token, append watermark, policy barriers and
  account-deletion marker remain additional publication fences. Target
  `episode_views`, `episode_view_links`, and checkpoint writes have one storage
  writer (`database/episode_log.py:publish`) under that owner transaction.

| Writer module | Storage entrypoints / branches | Publication coverage |
|---|---|---|
| `database/episodes.py` | `_record_activity`, `_commit`, `_close`, `_reopen`, `_update`, `write_membership`, `_write_receipts` | E/L/R |
| `database/episode_timeline.py` | `_attach_recorded_window`, `resume_recorded` | E/L/C |
| `database/episode_recorded_components.py` | `attach` (owner, absorbed episodes, timeline fence, pending members) | E/L/C |
| `database/conversation_recorded_time.py` | `create_if_absent` (membership adoption is read-only) | C |
| `utils/sync/assignment.py` | `assign_in_transaction`: record replacement; canonical create/update; donors; flattened ancestors; rollover parts | C; queued `member_refresh` emulator proof |
| `database/smart_merge.py` | `absorb_conversation` (survivor/donor/ancestors), `record_decision`, `claim_survivor_refresh`, `release_survivor_refresh`, `checkpoint_survivor_processing`, `complete_survivor_refresh`, `delegate_survivor_refresh` | C; queued absorb emulator proof |
| `database/conversations.py` | `upsert_conversation_with_lifecycle`, `persist_processing_result_with_lifecycle`, `update_conversation`, `transition_conversation_status`, `claim_conversation_status`, `update_conversation_finished_at`, `promote_final_pass_if_current`, `complete_sync_processing_hold` | C |
| `database/conversations.py` | `update_conversation_title`, `update_conversation_summary`, `update_conversation_segments`, `bind_client_processing`, `materialize_translation`, `migrate_conversations_level_batch` | C |
| `database/conversations.py` | `delete_conversation`, `set_conversation_as_discarded`, `rule_discard_outcome`, `restore_conversation_from_discarded`, `set_conversation_starred`, `set_conversation_visibility`, `publish_conversation_visibility_if_private`, `set_conversation_visibility_if_unchanged` | C |
| `database/conversations.py` | `update_owner_recognition_diagnostics`, `mark_playback_deferred`, `claim_record_lane_owner`, `record_demand_enrichment_checkpoint`, `link_duplicate_capture`, `reserve_share_email_recipients`, `confirm_share_email_recipients`, `release_share_email_recipients`, `set_postprocessing_status`, `store_conversation_photos` (parent marker) | C; even unrelated-field changes reject conservatively |
| `database/conversation_mutations.py` | `apply_conversation_sync_mutation` | C |
| `database/conversation_finalization_jobs.py` | `_apply_snapshot_bound_projection` (shared lifecycle projection primitive), `_dead_letter_finalization_job`, `_terminalize_exhausted_requeued_job_txn`, `_record_meeting_receipt_txn`, `_renew_processing_lease_txn`, `_reacquire_deferred_processing_txn`, `_abandon_byok_finalization_job_txn` | C |
| `database/conversation_terminal_title.py` | `recover_deferred_processing_failure_txn` | C |
| `database/conversation_quiet_checks.py` | `arm_quiet_check`, `_evaluate_quiet_check` (conversation updates) | C |
| `database/quiet_check_retirement.py` | `restore_quiet_check_in_transaction` (conversation status) | C |
| `database/oversized_conversation_terminal.py` | `_complete_oversized_in_progress_conversation_txn` | C |
| `database/conversation_merge_jobs.py` | `admit`, `finish_recovery` (source lifecycle) | C |
| `database/recording_sessions.py` | `_create_or_get_recording_session_txn` (binding), `tombstone_and_delete_empty_conversation` | C |
| `database/listen_continuations.py` | `calendar_continuity_row`, `resolve_live_continuation` (external-data hydration) | C |
| `database/server_batch_audio.py` | `note_server_batch_audio`, `close_server_batch_audio`, `note_server_batch_audio_received`, `claim_server_batch_lane` | C |
| `database/record_audio.py` | `seal_record_audio`, `set_record_upload_pending`, `mark_record_upload_failed` | C |
| `database/record_partial.py` | `finish_partial`, `update_run` | C |
| `database/batch_pipeline_store.py` | `FirestoreTransaction.flush` (conversation table and external refs); `database/batch_pipeline_intake.py:admit` routes record-lane patches here | C |
| `database/batch_pipeline_projection_session.py` | `ProjectionSession.persist` (silent-redrive revision; assignment delegates above) | C |
| `utils/batch_pipeline/record_seal_nojob.py` | `apply_backfill` | C |
| `utils/batch_pipeline/record_seal_repair.py` | `apply_seals` (also used by seal sweeper/cluster repair) | C |
| `database/episode_attach_memo.py` | `stamp`, `complete` | C |
| `database/summary_processing.py` | `claim_from_snapshot`, `record_empty_failure` | C |
| `services/summary_debt_repair.py` | `redrive` (blocked reason) | C |
| `database/action_item_refresh.py` | `reconcile` (conversation receipt) | C |
| `database/folders.py` | `_rehome_folder_conversations`, `move_conversation_to_folder`, `bulk_move_conversations_to_folder` | C |
| `database/capture_groups.py` | `join_capture_group`, `leave_capture_group` | C |
| `database/frame_requests.py` | `attach_frame_request_to_conversation` (parent photo marker) | C |
| `database/screen_frames.py` | `bump_conversation_screen_frames_revision`, `mark_conversation_screen_frames_adjudicated`, `set_conversation_screenshot_sharing_enabled` | C |
| `database/review_changes.py` | `record_agent_change`, `set_undone` (generic entity patch/restore can target conversations) | C |
| `database/review_transcript_changes.py` | `record_change`, `set_undone`; `edit_user_segment` delegates to record | C |
| `database/review_overlay_merge.py` | `transfer` (destination overlay and source duplicate marker) | C |
| `database/owner_confirmation.py` | `record` | C |
| `database/speaker_resolution_updates.py` | `persist_speaker_resolution_if_current` | C |
| `database/recording_speakers.py` | `same_assignment` (scope index) | C |
| `database/speaker_auto_enroll.py` | `publish`, `retract_conversation` (source markers/tombstone) | C |
| `database/voice_profiles.py` | `remove_ignored_voice` (manual assignment receipt) | C |
| `database/recurring_voices.py` | `learn` (source receipt) | C |
| `database/recurring_voice_privacy.py` | `scrub_transcripts` | C |
| `utils/person_evidence_backfill.py` | `backfill_person` (assignment receipt) | C |
| `utils/conversations/llm_input_dedupe.py` | `invalidate_l1`, `l1_succeeded` | C |
| `database/stuck_backfill.py` | `_close_txn`, `_restore_txn` | C |
| `database/locked_content.py` | `unlock_query_rows` (generic query adapter used for conversations) | C |
| `database/_client.py`; `database/user_data_deletion.py` | `delete_collection_recursive`; `purge_user_subtree` (retention/account recursive erasure callers) | C/E/L/R; account-deletion marker is additionally read in publication |
| `scripts/backfill_conversation_owner_uid.py` | `run_backfill` | C |
| `scripts/backfill_notes_v2_default_emoji.py` | `rewrite_emoji` | C |
| `scripts/backfill_sync_donor_tombstone_discarded.py` | `run_backfill` | C |
| `scripts/migrate_conversation_timestamps.py` | `process_user` | C |
| `scripts/migrate_screen_frames_to_data_plane_bucket.py` | `_update_with_cas` (conversation state migration) | C |
| `scripts/patch_phone_call_source.py` | `main` | C |
| `scripts/unlock_soft_cap_locked.py` | `unlock_collection` | C |
| `scripts/capture_empty_recovery.py` | `cas` | C |
| `scripts/repair_recovery_dead_letter_untitled.py` | `write_cas`, `rollback` | C |
| `scripts/staging/replay.py`; `utils/task_intelligence/chat_first_e2e_fixture.py` | `seed_capture`; `prepare_fixture` (synthetic owner only) | C |

`database/episode_receipts.py:plan_write` only plans receipt mutations; the actual
head/archive writes are `episodes._write_receipts`, listed above. Read-only
`episode_batch_pending.read_patch` returns patches applied by the listed timeline
and component writers. Child-only photo/model/shadow/evidence documents are not
read by repair: their parent-marker writers are listed where applicable.
Synthetic test/emulator fixtures can also create/update/delete these documents;
the same C/E/L/R proof applies, without a capture hook. Generic external/admin
writes are covered by SDK versions too, not by a manually maintained hook list.

The two queued-writer emulator cases execute the real `assign_in_transaction`
and `smart_merge.absorb_conversation` commits **after** the member snapshots,
with capture held in a queue and the owner unchanged. Both reject publication
atomically, retain dirty/checkpoint state and keep the actual Home route on
legacy at 100% admission. Delivery alone cannot clear dirty; fresh repair does.
Four additional emulator cases cover direct member edit/delete, missing-member
creation and hidden-member policy change with no capture at all.
