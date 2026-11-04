"""Reviewed legacy lifecycle inventory for WP-B (source base a5ccd17d67e3).

This is a declaration of existing mechanisms, not a new runtime state machine.
Phase strings are the compatibility reader's strings. Derived phases do not
have their own writes; entered_by lists the legacy field payload builders.
The AST inventory is deliberately conservative: it includes payload builders
and response/query dictionaries, so indirect transaction writes remain visible.
It proves ownership/field coverage, not execution or bounded liveness (WP-B2).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Writer:
    module: str
    function: str


@dataclass(frozen=True)
class Exit:
    kind: str
    cite: str


@dataclass(frozen=True)
class Alert:
    uid: str | None
    tier: str | None = None


@dataclass(frozen=True)
class State:
    machine: str
    state: str
    fields: tuple[str, ...]
    entered_by: tuple[Writer, ...]
    exit: Exit
    deadline_field: str | None
    deadline_stamped_at_entry: bool
    dwell_metric: str | None
    alert: Alert
    terminal: bool = False
    owner: str | None = None
    derived: bool = False
    note: str = ''

    @property
    def key(self):
        return f'{self.machine}:{self.state}'


# Checked both directions by test_lifecycle_state_table_writers.py. This is an
# explicit reviewed list, never regenerated during a test run.
FIELD_BUILDERS = {
    'database/_client.py': {'status': ['run_transactional']},
    'database/action_item_codec.py': {'status': ['prepare_action_item_for_read', 'prepare_action_item_for_write']},
    'database/action_item_refresh_policy.py': {'status': ['plan']},
    'database/action_items.py': {'status': ['retire_action_items_for_conversation']},
    'database/apps.py': {'status': ['change_app_approval_status', 'complete_mcp_oauth_authorization._complete']},
    'database/batch_pipeline_artifact_missing.py': {
        'state': ['ArtifactMissingStore.apply.commit', 'ArtifactMissingStore.restore_reupload.commit']
    },
    'database/batch_pipeline_intake.py': {'status': ['admit.commit']},
    'database/batch_pipeline_projection.py': {
        'projection_state': [
            'ProjectionStore.acknowledge.commit',
            'ProjectionStore.complete.commit',
            'ProjectionStore.hold_for_quarantine.commit',
        ],
        'state': [
            'ProjectionStore.complete.commit',
            'ProjectionStore.complete_partial.commit',
            'ProjectionStore.mark_enrichment.commit',
            'ProjectionStore.ready.commit',
            'ProjectionStore.settle_deleted_output.commit',
        ],
        'status': ['ProjectionStore.status.read'],
    },
    'database/batch_pipeline_projection_privacy.py': {
        'projection_state': ['hold.commit', 'resume.commit'],
        'state': ['_hold_receipt', 'hold.commit', 'resume.commit'],
    },
    'database/batch_pipeline_projection_release.py': {'projection_state': ['ProjectionReleaseStore.release.commit']},
    'database/batch_pipeline_projection_session.py': {
        'projection_state': ['ProjectionSession.persist', 'ProjectionSession.write_receipt'],
        'state': ['ProjectionSession.persist', 'ProjectionSession.write_receipt'],
    },
    'database/batch_pipeline_purge.py': {'projection_state': ['_write_erased_result']},
    'database/batch_pipeline_quarantine_recovery.py': {
        'state': [
            'RecoveryStore.settle.commit',
            'SilenceDispositionStore.complete_silence.commit',
            'SilenceDispositionStore.prepare_silence.commit',
        ]
    },
    'database/batch_pipeline_recovery.py': {'state': ['quarantine_fenced.revoke']},
    'database/batch_pipeline_shadow.py': {
        'state': [
            'ShadowStore._finish',
            'ShadowStore.handoff.prepare',
            'ShadowStore.offer.update',
            'ShadowStore.ready.publish',
            'ShadowStore.reserve.claim',
            'ShadowStore.start_recovery.pin_shadow_recovery',
            'ShadowStore.take.claim',
        ]
    },
    'database/batch_pipeline_speech_redrive.py': {
        'state': [
            'SpeechRedriveStore.prepare.commit',
            'SpeechRedriveStore.settle.commit',
            'SpeechRedriveStore.start.commit',
        ]
    },
    'database/batch_pipeline_terminal_empty.py': {
        'state': ['TerminalEmptyStore.complete.commit', 'TerminalEmptyStore.prepare.commit']
    },
    'database/candidate_integration_outbox.py': {
        'status': [
            '_in_doubt_dead_letter_patch',
            'abandon_candidate_integration_dispatch.apply',
            'claim_candidate_integration_dispatch.apply',
            'complete_candidate_integration_dispatch.apply',
            'complete_candidate_integration_recorded_export.apply',
            'dead_letter_candidate_integration_generation_mismatch.apply',
            'dead_letter_malformed_candidate_integration.apply',
        ]
    },
    'database/candidates.py': {
        'status': [
            '_task_create_storage',
            '_task_update_storage',
            'claim_candidate_for_legacy_promotion.apply',
            'reconcile_migrated_candidate.apply',
            'resolve_candidate_without_mutation.apply',
            'resolve_task_candidate.apply',
        ]
    },
    'database/conversation_finalization_jobs.py': {
        'finalization_status': [
            '_abandon_byok_finalization_job_txn',
            '_create_or_get_finalization_intent_txn',
            '_record_meeting_receipt_txn',
        ],
        'status': [
            '_abandon_byok_finalization_job_txn',
            '_byok_abandonment',
            '_claim_finalization_job_txn',
            '_claim_finalization_replay_txn',
            '_claim_result',
            '_create_or_get_finalization_intent_txn',
            '_dead_letter_finalization_job',
            '_defer_sync_revision_fence_txn',
            '_fanout_claim',
            '_fenced_finalization_update',
            '_grant_finalization_budget_requeue_txn',
            '_intent_from_job',
            '_mark_finalization_completed_txn',
            '_mark_finalization_retryable_txn',
            '_no_finalization_intent',
            '_reacquire_deferred_processing_txn',
            '_record_meeting_receipt_txn',
            '_recover_deferred_processing_failure_txn',
            '_resume_blocked_byok_job_txn',
            '_terminalize_exhausted_requeued_job_txn',
            'get_finalization_job_summary',
            'recover_stranded_byok_jobs',
            'scan_in_progress_conversations',
        ],
    },
    'database/conversation_merge_jobs.py': {
        'status': ['admit.commit', 'begin_recovery.commit', 'claim.commit', 'finish.commit', 'finish_recovery.commit']
    },
    'database/conversation_mutations.py': {
        'status': ['apply_conversation_sync_mutation', 'apply_conversation_sync_mutation._apply']
    },
    'database/conversation_processing_recovery.py': {
        'status': ['_complete_orphan_conversation_txn', '_complete_unstampable_orphan_conversation_txn']
    },
    'database/conversation_quiet_checks.py': {
        'status': ['_evaluate_quiet_check.evaluate', 'arm_quiet_check.arm', 'ensure_quiet_check_progress.repair']
    },
    'database/conversation_terminal_title.py': {
        'finalization_status': ['dead_letter_conversation_updates'],
        'status': ['dead_letter_conversation_updates'],
    },
    'database/conversations.py': {
        'record_audio_partial': [
            'persist_processing_result_with_lifecycle._persist',
            'upsert_conversation_with_lifecycle._write_processing_result',
        ],
        'status': [
            'claim_conversation_status._claim',
            'get_conversations_finished_after',
            'promote_final_pass_if_current.commit',
            'transition_conversation_status',
        ],
    },
    'database/daily_summaries.py': {'status': ['set_daily_summary_generation_status']},
    'database/dream_store.py': {'status': ['acquire.claim']},
    'database/durable_queue.py': {'status': ['redrive_patch']},
    'database/episode_recorded_components.py': {'recorded_merged_into': ['attach.commit'], 'status': ['_state']},
    'database/episode_timeline.py': {
        'status': ['_attach_recorded_window.attach', 'resume_recorded.resume'],
        'wrap_up_requested_at': ['resume_recorded.resume'],
    },
    'database/episodes.py': {'status': ['_closed_fields', '_reopen'], 'wrap_up_requested_at': ['_reopen']},
    'database/fair_use.py': {'stage': ['renew_fair_use_warning.apply', 'reset_fair_use_state', 'set_fair_use_stage']},
    'database/focus_sessions.py': {'status': ['_normalize_focus_session_doc', 'create_focus_session']},
    'database/goals.py': {
        'status': [
            '_new_goal_payload',
            'delete_goal',
            'focus_goal.apply',
            'normalize_goal_storage',
            'transition_goal_lifecycle.apply',
            'unfocus_goal.apply',
        ]
    },
    'database/import_jobs.py': {'status': ['cancel_import_job_if_active.apply']},
    'database/mcp_conversation_pages.py': {'status': ['get_mcp_conversation_cards', 'get_mcp_conversation_cards_page']},
    'database/mcp_oauth.py': {'status': ['_grant_write', 'revoke_grant']},
    'database/memory_apply_store.py': {
        'status': [
            '_privacy_tombstoned_memory_item',
            '_reactivate_replacement_lineage_item',
            '_write_canonical_review_resolution',
        ]
    },
    'database/memory_imports.py': {'status': ['ingest_memory_import_batch']},
    'database/memory_outbox_worker.py': {
        'status': [
            '_claim_event_transaction',
            '_settle_failure',
            'lease_canonical_memory_outbox_events',
            'run_canonical_memory_outbox_worker_tick.process_one',
        ]
    },
    'database/memory_vector_metadata.py': {
        'status': ['_active_memory_vector_filter_clauses', '_shared_memory_vector_metadata_fields']
    },
    'database/memory_vector_repair_outbox.py': {'status': ['build_vector_repair_purge_outbox_records']},
    'database/memory_vector_repair_outbox_telemetry.py': {
        'status': ['_build_vector_repair_outbox_worker_telemetry_payloads']
    },
    'database/memory_vector_repair_outbox_worker.py': {
        'status': [
            '_claim_vector_repair_purge_outbox_snapshot_in_transaction',
            '_claim_vector_repair_purge_outbox_snapshot_without_transaction',
            '_lease_patch',
            'process_vector_repair_purge_outbox_records.process_one',
        ]
    },
    'database/messaging.py': {
        'status': [
            'MessagingStore._claim.apply',
            'MessagingStore.claim_expired.apply',
            'MessagingStore.complete',
            'MessagingStore.enqueue.apply',
            'MessagingStore.retry',
        ]
    },
    'database/messaging_albums.py': {'status': ['append_album']},
    'database/open_loops.py': {'status': ['upsert_loop']},
    'database/oversized_conversation_terminal.py': {'status': ['_complete_oversized_in_progress_conversation_txn']},
    'database/pinecone_partition_state.py': {
        'status': ['_begin_mutation', '_finish_mutation', '_mark_mutation_uncertain', '_reconcile_mutation']
    },
    'database/proactivity.py': {'status': ['publish_item.transact']},
    'database/quiet_check_retirement.py': {'status': ['_retire', 'restore_quiet_check_in_transaction']},
    'database/record_audio.py': {
        'record_audio_closed': [
            'mark_record_upload_failed.commit',
            'seal_record_audio.commit',
            'set_record_upload_pending.commit',
        ],
        'record_upload_failed': ['mark_record_upload_failed.commit'],
        'record_upload_sessions': ['set_record_upload_pending.commit'],
    },
    'database/record_partial.py': {
        'record_audio_closed': ['finish_partial.commit', 'update_run.commit'],
        'record_audio_partial': ['finish_partial.commit', 'update_run.commit'],
        'record_upload_sessions': ['finish_partial.commit'],
        'state': ['finish_partial.commit', 'update_run.commit'],
    },
    'database/recurrence_inbox.py': {'status': ['complete_recurrence_receipt.apply']},
    'database/redis_db.py': {'status': ['set_migration_status']},
    'database/review_memory_hygiene.py': {'status': ['record_change.apply', 'set_undone.reverse']},
    'database/review_queue.py': {
        'status': [
            '_advance_legacy_scan_cursor',
            '_authoritative_canonical_review_projection',
            '_build_correction_record',
            '_stale_review_self_heal_update',
            'accepted_fact',
            'expire_review_conflicts',
            'list_review_conflicts',
            'resolve_review_conflict',
        ]
    },
    'database/review_store.py': {
        'status': ['enqueue_review_proposal.enqueue', 'finish_answer.finish', 'list_proposals']
    },
    'database/short_term_memories.py': {'status': ['mark_consolidated', 'tombstone_source']},
    'database/stale_conversation_recovery.py': {'status': ['get_stale_recovery_page']},
    'database/stuck_backfill.py': {'status': ['_close_txn']},
    'database/summary_debt_queries.py': {'summary_due_at': ['due_conversations']},
    'database/summary_processing.py': {'summary_due_at': ['record_empty_failure.commit']},
    'database/sync_backfill_sequencer.py': {'status': ['retire_expired.commit']},
    'database/sync_cap_holds.py': {'status': ['mark_content_held.commit', 'settle_hold.commit']},
    'database/sync_dead_letters.py': {'status': ['confirm_dead_letter._txn', 'record_dead_letter_pending._txn']},
    'database/sync_jobs.py': {
        'status': [
            '_sync_job_finalization_updates',
            'create_sync_job',
            'fenced_mark_job_failed',
            'fenced_mark_job_processing',
            'fenced_mark_job_queued_for_retry',
            'mark_job_failed',
            'mark_job_processing',
            'mark_job_queued_for_retry',
        ]
    },
    'database/sync_ledger.py': {
        'status': [
            '_mark_completed_transaction',
            '_processing_claim_updates',
            '_release_claim_after_job_retired_transaction',
            '_release_claim_transaction',
            'complete_batch_partial_in_transaction',
            'complete_batch_projection_in_transaction',
        ]
    },
    'database/sync_redrive.py': {'status': ['prepare']},
    'database/usage_units.py': {'status': ['_render_usage', '_safe_price', 'gateway_shadow']},
    'database/user_data_deletion.py': {'status': ['purge_user_subtree']},
    'database/users.py': {
        'status': ['ensure_backend_onboarding_admission.admit', 'set_migration_status', 'set_user_training_data_opt_in']
    },
    'database/vector_db.py': {
        'status': [
            'query_workstream_association_candidates',
            'upsert_memory_vector',
            'upsert_memory_vectors_batch',
            'upsert_workstream_association_vector',
        ]
    },
    'database/workstreams.py': {
        'status': [
            '_task_storage',
            'create_artifact_descriptor.apply',
            'import_task_goal_links.complete',
            'import_task_goal_links.reserve',
            'resolve_workstream_candidate.apply',
            'transition_artifact_status.apply',
        ]
    },
    'database/wrapped.py': {'status': ['create_wrapped', 'reset_wrapped_for_regeneration', 'update_wrapped_status']},
    'utils/batch_pipeline/contracts.py': {'state': ['vad_receipt']},
    'utils/batch_pipeline/live.py': {'state': ['register_recording.commit']},
    'utils/batch_pipeline/merge.py': {
        'projection_state': ['OrderedMerge.commit_next.commit'],
        'state': ['OrderedMerge.commit_next.commit', '_fresh_pick'],
    },
    'utils/batch_pipeline/provider_stt.py': {
        'state': [
            'ProviderSttStore.hold.commit',
            'ProviderSttStore.redrive.commit',
            'ProviderSttStore.settle.commit',
            'ProviderSttStore.start.commit',
            'ProviderSttStore.supersede.commit',
            'ProviderSttStore.terminal.commit',
        ]
    },
    'utils/batch_pipeline/provider_stt_admission.py': {'state': ['enqueue_in_transaction']},
    'utils/batch_pipeline/record_seal_nojob.py': {
        'record_audio_closed': ['apply_backfill.commit'],
        'record_upload_failed': ['apply_backfill.commit'],
        'record_upload_sessions': ['apply_backfill.commit'],
        'state': ['refusal'],
    },
    'utils/batch_pipeline/record_seal_repair.py': {
        'record_audio_closed': ['apply_seals.commit'],
        'record_upload_failed': ['apply_seals.commit'],
        'record_upload_sessions': ['apply_seals.commit'],
    },
    'utils/batch_pipeline/retry_policy.py': {'state': ['quarantine_job']},
    'utils/batch_pipeline/scheduler.py': {
        'state': [
            'Scheduler._pull_shard.commit',
            'Scheduler.complete.commit',
            'Scheduler.defer.commit',
            'Scheduler.enqueue_in_transaction',
            'Scheduler.recover.commit',
            'Scheduler.redrive_in_transaction',
            'Scheduler.restore_audio_in_transaction',
            '_defer',
        ]
    },
    'utils/batch_pipeline/vendor_health.py': {'state': ['BreakerRecord.to_raw']},
    'utils/conversations/lifecycle.py': {'status': ['get_finalization_status']},
    'utils/conversations/minimum_derived.py': {'summary_due_at': ['waive_short_clip_summary_debt']},
    'utils/conversations/summary_delivery.py': {
        'summary_completed_at': ['merge_result'],
        'summary_due_at': ['merge_result', 'prepare'],
        'summary_first_pending_at': ['merge_result', 'prepare'],
    },
    'utils/episodes/composer.py': {'composed_fingerprint': ['_compose', '_compose.finish']},
    'utils/episodes/log/fold.py': {'recorded_merged_into': ['Fold.rows']},
    'utils/episodes/service.py': {
        'status': ['_close', '_reconcile', 'dismiss_item', 'new_episode', 'to_wire'],
        'wrap_up_requested_at': ['new_episode', 'wrap_up'],
    },
    'utils/fair_use.py': {
        'stage': ['clear_fair_use_on_upgrade', 'escalate_enforcement', 'normalize_expired_restriction_state']
    },
    'utils/sync/assignment.py': {'sync_bridge_pending': ['assign_in_transaction.plan']},
}


def writers(machine, *fields):
    status_modules = {
        'finalization': {'database/conversation_finalization_jobs.py', 'database/conversation_terminal_title.py'},
        'episode': {'database/episodes.py', 'database/episode_timeline.py', 'utils/episodes/service.py'},
    }.get(
        machine,
        {
            'database/conversations.py',
            'utils/conversations/lifecycle.py',
            'database/conversation_finalization_jobs.py',
            'database/conversation_terminal_title.py',
        },
    )
    return tuple(
        Writer(module, function)
        for module, declared in FIELD_BUILDERS.items()
        for field, functions in declared.items()
        if field in fields
        if field != 'status' or module in status_modules
        for function in functions
    )


def row(
    machine,
    state,
    fields,
    *,
    exit=None,
    deadline=None,
    metric=None,
    alert=None,
    terminal=False,
    owner=None,
    derived=False,
    note='',
):
    return State(
        machine,
        state,
        fields,
        writers(machine, *fields),
        exit or Exit('callback-only', 'No independent automatic exit declared'),
        deadline,
        deadline is not None,
        metric,
        alert or Alert(None),
        terminal,
        owner,
        derived,
        note,
    )


FINALIZER = Exit('sweeper', 'services/conversation_finalization.py:reconcile_listen_finalization_jobs')
BATCH = Exit('sweeper', 'utils/batch_pipeline/serving.py:')
LEASE = Exit('lease', 'utils/batch_pipeline/scheduler.py:Scheduler.recover')
DECAY = Exit('decay', 'utils/fair_use.py:normalize_expired_restriction_state')
SUMMARY = Exit('sweeper', 'services/summary_debt_repair.py:')
PHASE_FIELDS = (
    'status',
    'finalization_status',
    'record_audio_closed',
    'record_upload_sessions',
    'record_upload_failed',
    'record_audio_partial',
    'summary_completed_at',
)
CONVERSATION_PHASES = (
    'capturing',
    'sealed',
    'processing',
    'transcribed',
    'complete',
    'settled',
    'discarded',
    'quarantined',
    'dead_letter',
    'failed',
    'merged',
)
EPISODE_PHASES = ('live', 'closing', 'closed', 'composed', 'redirected')

# Derived conversation rows are reader vocabulary, not automatic entry sites.
# The underlying obligations below each receive the full four-clause verdict.
STATES = (
    tuple(
        row(
            'conversation_phase',
            name,
            PHASE_FIELDS,
            derived=True,
            note='Read-only compatibility projection; no persisted phase writer',
        )
        for name in CONVERSATION_PHASES
    )
    + (
        row(
            'conversation',
            'in_progress',
            ('status',),
            exit=FINALIZER,
            note='Stale-content sweep; no deadline stamped for every capture',
        ),
        row(
            'conversation',
            'processing',
            ('status',),
            exit=FINALIZER,
            metric='listen_finalization_oldest_nonterminal_age_seconds',
            alert=Alert('omi-capture-oldest-nonterminal', 'agent'),
        ),
        row('conversation', 'merging', ('status',), exit=FINALIZER),
        row('conversation', 'completed', ('status',), terminal=True, owner='utils/conversations/lifecycle.py'),
        row('conversation', 'failed', ('status',), terminal=True, owner='utils/conversations/lifecycle.py'),
        row(
            'record_audio',
            'capturing',
            ('record_upload_sessions',),
            note='freshtitles open-producer-token fix, no PR yet',
        ),
        row(
            'record_audio',
            'sealed',
            ('record_audio_closed',),
            note='No job: manual digest-gated nojob recovery is not an automatic exit; freshtitles fix, no PR yet',
        ),
        row(
            'record_audio',
            'record_upload_failed',
            ('record_upload_failed',),
            note='Sticky bit; full-proof repair exists, but reconnect is not retry; freshtitles fix, no PR yet',
        ),
        row(
            'record_audio',
            'record_audio_partial',
            ('record_audio_partial',),
            exit=BATCH,
            note='Partial inventory coordinator polls with next_inventory_at; not stamped on conversation entry',
        ),
        row(
            'finalization',
            'queued',
            ('finalization_status', 'status'),
            exit=FINALIZER,
            deadline='reconcile_after_at',
            metric='listen_finalization_oldest_nonterminal_age_seconds',
            alert=Alert('omi-capture-oldest-nonterminal', 'agent'),
        ),
        row(
            'finalization',
            'leased',
            ('status',),
            exit=FINALIZER,
            deadline='lease_expires_at',
            metric='listen_finalization_oldest_nonterminal_age_seconds',
            alert=Alert('omi-capture-oldest-nonterminal', 'agent'),
        ),
        row(
            'finalization',
            'blocked_byok',
            ('finalization_status', 'status'),
            exit=FINALIZER,
            metric='omi_finalization_byok_new_oldest_age_seconds',
            alert=Alert('omi-finalization-byok-dwell-page', 'page'),
            note='14-day abandonment is computed from activity, not a deadline stamped at entry; #24533 supplies alerts',
        ),
        row(
            'finalization',
            'dead_letter',
            ('finalization_status', 'status'),
            terminal=True,
            owner='backend/docs/runbooks/real-traffic-journeys.md',
            metric='listen_finalization_jobs',
            alert=Alert('omi-finalization-dead-letter-stock', 'agent'),
            note='#24533 supplies stock and age alerts',
        ),
        row(
            'finalization',
            'completed',
            ('finalization_status', 'status'),
            terminal=True,
            owner='services/conversation_finalization.py',
            metric='listen_finalization_jobs',
        ),
        row(
            'summary_debt',
            'pending',
            ('summary_first_pending_at', 'summary_due_at'),
            exit=SUMMARY,
            deadline='summary_due_at',
            metric='omi_summary_debt_oldest_age_seconds',
        ),
        row(
            'summary_debt',
            'completed',
            ('summary_completed_at',),
            terminal=True,
            owner='utils/conversations/summary_delivery.py',
            metric='omi_summary_terminal_total',
            note='Outcome counter is not a stock metric',
        ),
        row(
            'fair_use',
            'none',
            ('stage',),
            terminal=True,
            owner='utils/fair_use.py',
            note='Base enforcement state; read-path dwell gauge is not a fleet stock gauge',
        ),
        row(
            'fair_use',
            'warning',
            ('stage',),
            exit=DECAY,
            deadline='warning_until',
            metric='omi_fair_use_stage_dwell_seconds',
            note='#24531 adds warning expiry and downward decay',
        ),
        row(
            'fair_use',
            'throttle',
            ('stage',),
            exit=DECAY,
            deadline='throttle_until',
            metric='omi_fair_use_stage_dwell_seconds',
            note='#24531 fixes the previously absorbing stage',
        ),
        row(
            'fair_use',
            'restrict',
            ('stage',),
            exit=DECAY,
            deadline='restrict_until',
            metric='omi_fair_use_stage_dwell_seconds',
        ),
        row(
            'visibility',
            'bridge_pending',
            ('sync_bridge_pending',),
            exit=Exit('decay', 'utils/sync/bridge_pending.py:hidden'),
            deadline='expires_at',
            note='600-second nonrenewable visibility bound',
        ),
        row(
            'visibility',
            'settling_hold',
            ('status',),
            exit=Exit('decay', 'utils/conversations/fragment_visibility.py:is_settling_fragment'),
            note='2-hour bound computed from finished_at; deadline not stamped at entry',
        ),
    )
    + tuple(
        row(
            'batch',
            name,
            ('state',),
            exit=LEASE if name == 'leased' else BATCH,
            deadline='lease_until' if name == 'leased' else None,
            metric=(
                None
                if name in ('record_pending', 'committed', 'partial_retired', 'privacy_blocked')
                else 'omi_batch_timeliness_new_oldest_age_seconds'
            ),
            alert=(
                None
                if name in ('record_pending', 'committed', 'partial_retired', 'privacy_blocked')
                else Alert('omi-batch-unit-unpublished-2h', 'page')
            ),
            terminal=name in ('committed', 'partial_retired', 'privacy_blocked'),
            owner=(
                'utils/batch_pipeline/serving.py'
                if name in ('committed', 'partial_retired', 'privacy_blocked')
                else None
            ),
            note=(
                'PR #24587 addresses drain contention; available_at is a defer, not an admission budget'
                if name == 'record_pending'
                else ''
            ),
        )
        for name in (
            'record_pending',
            'ready',
            'leased',
            'retry',
            'result_ready',
            'vendor_held',
            'quarantined',
            'privacy_blocked',
            'partial_retired',
            'committed',
        )
    )
    + tuple(
        row(
            'batch_projection',
            name,
            ('projection_state',),
            exit=BATCH,
            terminal=name in ('completed', 'erased'),
            owner='database/batch_pipeline_projection.py' if name in ('completed', 'erased') else None,
            metric=None if name in ('completed', 'erased') else 'omi_batch_timeliness_new_oldest_age_seconds',
            alert=None if name in ('completed', 'erased') else Alert('omi-batch-unit-unpublished-2h', 'page'),
            note='Result projection receipt state, distinct from batch job state',
        )
        for name in ('pending', 'persisted', 'ready', 'quarantine_held', 'completed', 'erased')
    )
    + tuple(
        row(
            'episode',
            name,
            ('status', 'wrap_up_requested_at', 'composed_fingerprint', 'recorded_merged_into'),
            terminal=name in ('composed', 'redirected'),
            owner='database/episodes.py' if name in ('composed', 'redirected') else None,
            note='Closing is lazy on read; no entry deadline' if name == 'closing' else '',
        )
        for name in EPISODE_PHASES
    )
)

CLAUSES = ('automatic_exit', 'entry_deadline', 'dwell_metric', 'dwell_alert')
