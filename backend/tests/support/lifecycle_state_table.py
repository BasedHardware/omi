"""Reviewed legacy lifecycle inventory for WP-B (B2 source base 43085bb24061).

This is a declaration of existing mechanisms, not a new runtime state machine.
Phase strings are the compatibility reader's strings. Derived phases do not
have their own writes; entered_by lists the legacy field payload builders.
The AST inventory is deliberately conservative: it includes payload builders
and response/query dictionaries, so indirect transaction writes remain visible.
It proves ownership/field coverage, not execution or bounded liveness (WP-B2).
"""

from dataclasses import dataclass
import math
from typing import cast

from tests.support.lifecycle_ast import EntryPath, builders
from tests.support.lifecycle_writer_inventory import FIELD_SITES


@dataclass(frozen=True)
class Writer:
    module: str
    function: str


@dataclass(frozen=True)
class Exit:
    kind: str
    cite: str
    # Conditional automatic transitions coexist with a live producer's normal
    # callback exit. They do not make all live tokens eligible for expiration.
    automatic_writers: tuple[Writer, ...] = ()


@dataclass(frozen=True)
class Alert:
    uid: str | None
    tier: str | None = None


# Reviewed observability debt, independent of live rule state or failed assertions.
# Lead2 ruling699300 (2026-11-08T15:13Z), PR #24938 explicitly pauses known
# backlog pages until #24731/#24893 drain work ships and clean24h criteria hold.
# These rows do NOT have active dwell-alert protection while paused. The strict
# invariant still fails; strict xfail removal is required when an owner unpauses.
# Criteria: backend/charts/monitoring/batch-projection/pipeline-alerts.md.
IMPORT_PAUSED_DWELL_ROWS = {
    'batch:record_pending': 'omi-record-pending-dwell',
    'batch:ready': 'omi-batch-unit-unpublished-2h',
    'batch:leased': 'omi-batch-unit-unpublished-2h',
    'batch:retry': 'omi-batch-unit-unpublished-2h',
    'batch:result_ready': 'omi-batch-unit-unpublished-2h',
    'batch:vendor_held': 'omi-batch-unit-unpublished-2h',
    'batch:quarantined': 'omi-batch-unit-unpublished-2h',
    'batch_projection:pending': 'omi-batch-unit-unpublished-2h',
    'batch_projection:persisted': 'omi-batch-unit-unpublished-2h',
    'batch_projection:ready': 'omi-batch-unit-unpublished-2h',
    'batch_projection:quarantine_held': 'omi-pipeline-held-row-age',
}


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
    deadline_entries: tuple[EntryPath, ...] = ()
    alert_required: bool = True
    quiescent: bool = False
    deadline_exemption: str = ''
    exit_exemption: str = ''

    @property
    def key(self):
        return f'{self.machine}:{self.state}'


# Checked both directions by test_lifecycle_state_table_writers.py. This is an
# explicit reviewed list, never regenerated during a test run.
FIELD_BUILDERS = {module: builders(sites) for module, sites in FIELD_SITES.items()}


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


# Durably refused transitions must retire the summary due index in the same
# payload. These write owners are exercised by test_summary_refusal_writers;
# they do not create a new lifecycle state or retire transient pending debt.
SUMMARY_REFUSAL_WRITERS = (
    Writer('utils/sync/assignment.py', '_donor_redirect_patch'),
    Writer('database/conversations.py', 'update_conversation_title'),
    Writer('database/conversation_mutations.py', '_apply_operation'),
    Writer('database/chat_edits.py', 'apply_update.apply'),
    Writer('database/chat_edits.py', 'restore.apply'),
    Writer('utils/retrieval/tools/edit_tools.py', 'update_conversation'),
    Writer('utils/conversations/summary_delivery.py', 'merge_result'),
)

# The inverse manual-field writes recover only an owed, unindexed obligation,
# from its original acceptance and deadline, inside the same transaction.
SUMMARY_MANUAL_CLEAR_WRITERS = (
    Writer('database/chat_edits.py', 'apply_update.apply'),
    Writer('database/chat_edits.py', 'restore.apply'),
)

SUMMARY_DISCARD_RESTORE_WRITERS = (Writer('database/conversations.py', 'restore_conversation_from_discarded._restore'),)


FINALIZATION_MODULE = 'database/conversation_finalization_jobs.py'
FAIR_USE_MODULE = 'utils/fair_use.py'


@dataclass(frozen=True)
class PatchContract:
    keys: tuple[str, ...]
    sources: tuple[tuple[Writer, str], ...]


# An opaque patch is rejected unless its complete returned-key boundary has
# been audited. AST fingerprints ignore comments/formatting, but force a new
# source audit when this proof's callees or serialization model change.
PATCH_CONTRACTS = {
    'utils.conversations.recorded_time.write_span': PatchContract(
        ('recorded_start', 'recorded_end', 'arrival_at', 'clock'),
        (
            (
                Writer('utils/conversations/recorded_time.py', 'write_span'),
                '67652bbdd304ef4e0761e2e20594a50369cef1bc6955f3dce41bfa5d58ca553b',
            ),
            (
                Writer('utils/conversations/recorded_time.py', 'span_fields'),
                '97badd257455e75827f4ed287c1a68fb35eea1e4b3db2d9e132a900af4fed30a',
            ),
            (
                Writer('utils/conversations/recorded_time.py', 'conversation_span'),
                'fc65ea6d28331e9fdb075178b84bca85d3d47a28aecf4155d0d11f314e6cab92',
            ),
            (
                Writer('models/recorded_span.py', 'RecordedSpan'),
                '26aae72c41aff5b01f58e14d792a14d67c630831cfc4c44710437f1e8bea8001',
            ),
        ),
    ),
}


def entry(module, function, field, state=None, *, inplace=False, patches=(), **bindings):
    return EntryPath(module, function, field, state, tuple(sorted(bindings.items())), inplace, patches)


# Automatic entry paths are distinct from conservative payload builders.
DEADLINE_ENTRIES = {
    'batch:quarantined': (
        entry('utils/batch_pipeline/retry_policy.py', 'quarantine_job', 'state', 'quarantined', inplace=True),
        entry('utils/batch_pipeline/provider_stt.py', 'ProviderSttStore.settle.commit', 'state', 'quarantined'),
        entry('utils/batch_pipeline/provider_stt.py', 'ProviderSttStore.terminal.commit', 'state', 'quarantined'),
    ),
    'finalization:queued': (
        entry(
            FINALIZATION_MODULE,
            '_create_or_get_finalization_intent_txn',
            'status',
            'queued',
            status='queued',
            requires_byok=False,
        ),
        entry(FINALIZATION_MODULE, '_resume_blocked_byok_job_txn', 'status', 'queued'),
        entry(FINALIZATION_MODULE, '_mark_finalization_retryable_txn', 'status', 'queued'),
        entry(FINALIZATION_MODULE, '_defer_sync_revision_fence_txn', 'status', 'queued'),
        entry(FINALIZATION_MODULE, '_claim_finalization_replay_txn', 'status', 'queued'),
        entry(FINALIZATION_MODULE, '_grant_finalization_budget_requeue_txn', 'status', 'queued'),
    ),
    'finalization:leased': (entry(FINALIZATION_MODULE, '_claim_finalization_job_txn', 'status', 'leased'),),
    'batch:leased': (entry('utils/batch_pipeline/scheduler.py', 'Scheduler._pull_shard.commit', 'state', 'leased'),),
    'summary_debt:pending': (
        entry('utils/conversations/summary_delivery.py', 'prepare', 'summary_first_pending_at', inplace=True),
    ),
    'fair_use:warning': (
        entry(
            FAIR_USE_MODULE,
            'escalate_enforcement',
            'stage',
            'warning',
            new_stage='warning',
            FAIR_USE_THROTTLE_DECAY_ENABLED=True,
        ),
        entry(
            FAIR_USE_MODULE,
            'normalize_expired_restriction_state',
            'stage',
            'warning',
            new_stage='warning',
            stage='throttle',
            FAIR_USE_THROTTLE_DECAY_ENABLED=True,
        ),
    ),
    'fair_use:throttle': (
        entry(
            FAIR_USE_MODULE,
            'escalate_enforcement',
            'stage',
            'throttle',
            new_stage='throttle',
            FAIR_USE_THROTTLE_DECAY_ENABLED=True,
        ),
        entry(
            FAIR_USE_MODULE,
            'normalize_expired_restriction_state',
            'stage',
            'throttle',
            new_stage='throttle',
            stage='restrict',
            FAIR_USE_THROTTLE_DECAY_ENABLED=True,
        ),
    ),
    'fair_use:restrict': (
        entry(
            FAIR_USE_MODULE,
            'escalate_enforcement',
            'stage',
            'restrict',
            new_stage='restrict',
            FAIR_USE_THROTTLE_DECAY_ENABLED=True,
        ),
    ),
    'visibility:transcribing_hold': (
        entry(
            'database/conversation_finalization_jobs.py',
            '_complete_server_batch_capture_txn',
            'home_transcription_pending_at',
        ),
        # The reviewed orphan owner stamps the same bounded Home hold in its
        # canonical registration transaction, without finalization fanout.
        entry(
            'utils/conversations/lifecycle.py',
            'complete_orphan_batch_capture',
            'home_transcription_pending_at',
        ),
    ),
    'visibility:bridge_pending': (
        entry(
            'utils/sync/assignment.py',
            'assign_in_transaction.plan',
            'sync_bridge_pending',
            inplace=True,
            patches=('utils.conversations.recorded_time.write_span',),
        ),
    ),
}


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
    stamped=False,
    alert_required=None,
    quiescent=False,
    deadline_exemption='',
    exit_exemption='',
    entry_writers=None,
):
    entries = DEADLINE_ENTRIES.get(f'{machine}:{state}', ())
    entered_by = (
        entry_writers
        if entry_writers is not None
        else (
            tuple(dict.fromkeys(Writer(path.module, path.function) for path in entries))
            if entries
            else writers(machine, *fields)
        )
    )
    return State(
        machine,
        state,
        fields,
        entered_by,
        exit or Exit('callback-only', 'No independent automatic exit declared'),
        deadline,
        stamped,
        metric,
        alert or Alert(None),
        terminal,
        owner,
        derived,
        note,
        entries,
        not terminal if alert_required is None else alert_required,
        quiescent,
        deadline_exemption,
        exit_exemption,
    )


FINALIZER = Exit('sweeper', 'services/conversation_finalization.py:reconcile_listen_finalization_jobs')
BATCH = Exit('sweeper', 'utils/batch_pipeline/serving.py:start_serving_from_env.run')
LEASE = Exit('lease', 'utils/batch_pipeline/scheduler.py:Scheduler.recover')
DECAY = Exit('decay', 'utils/fair_use.py:normalize_expired_restriction_state')
SUMMARY = Exit('sweeper', 'services/summary_debt_repair.py:tick')
RECORD_REPAIR = Exit('sweeper', 'utils/batch_pipeline/record_seal_worker.py:Worker.tick')
ABANDON_RECORD_PRODUCER = Writer('database/record_audio.py', 'abandon_record_upload_session.commit')
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
    (
        row(
            'batch',
            'allowance_held',
            ('state',),
            exit=Exit('sweeper', 'utils/batch_pipeline/allowance_hold.py:AllowanceHolds.tick'),
            metric='omi_batch_allowance_held_units',
            alert_required=False,
            deadline_exemption='SCA-2195: allowance policy parking has no recording expiry; owner generation releases it.',
            entry_writers=(Writer('database/batch_pipeline_allowance_hold.py', 'park'),),
            note='Current held/allowance_exhausted only; custody retained, outside retry and pending-work sweeps.',
        ),
    )
    + tuple(
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
        row(
            'conversation',
            'completed',
            ('status', 'terminal_family', 'terminal_family_at'),
            terminal=True,
            owner='utils/conversations/lifecycle.py',
            note='Phase 2a claim/persist success; only explicit restore supersedes failure; persist never regresses completed status; legacy and other writers may lack classifier',
        ),
        row(
            'conversation',
            'failed',
            ('status',),
            terminal=True,
            owner='utils/conversations/lifecycle.py',
            alert_required=True,
        ),
        row(
            'record_audio',
            'capturing',
            ('record_upload_sessions',),
            exit=Exit(
                'callback-only',
                'database/record_audio.py:set_record_upload_pending',
                automatic_writers=(ABANDON_RECORD_PRODUCER,),
            ),
            deadline_exemption='No producer TTL: live custody is cleared only by exact-token finish; lead2 9d457c / 4bf62d',
            exit_exemption='Interactive live custody awaits exact-token finish, not automatic expiration; 4bf62d',
            note='Live producer custody; exact-token finish remains the normal exit. Capacity eviction automatically '
            'transitions only the evicted socket\'s owned tokens to abandoned, after its worker and all executor '
            'futures settle (utils/pusher_record_finish.py:abandon_evicted_record_drain; '
            'utils/pusher_record_barrier.py:PusherRecordBarrier.abandon_recordings). '
            'The kill switch can disable this conditional exit. When bounded abandon admission is full, '
            'outcome=abandon_overflow leaves the token capturing/fenced with no new coordinator; '
            'the existing process/pod-death repair proof remains its exit. Off-mode frame tokens never expire by age; '
            'serve-created custody tokens retain their own lease exit after rollback. The leased per-token view is separate. '
            'Refused seals have a separate first-entry clock and bounded job-page visibility in seal_refused; '
            'general live-producer dwell visibility remains required',
        ),
        row(
            'record_token',
            'capturing',
            ('record_upload_sessions',),
            entry_writers=(
                Writer('database/record_audio.py', 'set_record_upload_pending.commit'),
                Writer('database/record_audio.py', 'renew_record_token_lease.commit'),
                Writer('database/record_custody_append.py', 'begin.commit'),
            ),
            exit=Exit('lease', 'utils/batch_pipeline/record_producer_proof.py:producer_tokens_dead'),
            derived=True,
            metric='omi_record_token_lease_active',
            alert=Alert('omi-record-token-lease-late-append', 'page'),
            deadline_exemption='Nested per-token lease_expires_at, stamped only when lease mode is enabled',
            note='Exact-token finish clear (including record_custody_append.finish after durable acceptance or refusal); '
            'custody lease covers the configured sync request timeout plus a named margin. '
            'abandon attestation; or computed lease lapse. Off preserves original producer proof.',
        ),
        row(
            'record_token',
            'lease_lapsed',
            ('record_upload_sessions',),
            entry_writers=(
                Writer('database/record_audio.py', 'set_record_upload_pending.commit'),
                Writer('database/record_audio.py', 'renew_record_token_lease.commit'),
            ),
            exit=Exit(
                'sweeper',
                'utils/batch_pipeline/record_seal_repair.py:apply_seals',
                (
                    Writer('utils/batch_pipeline/record_seal_repair.py', 'apply_seals.commit'),
                    Writer('database/record_partial.py', 'finish_partial.commit'),
                    Writer('database/record_audio.py', 'renew_record_token_lease.commit'),
                ),
            ),
            derived=True,
            metric='omi_record_token_lease_active',
            alert=Alert('omi-record-token-lease-late-append', 'page'),
            deadline_exemption='Computed from nested lease clocks; never persisted as expiry state',
            note='Named exits: seal via apply_seals after retained-tail proof; partial finish via finish_partial '
            'clears token map and re-arms hourly inventory; late frames re-activate via renew_record_token_lease. '
            'Custody uploads first fence via record_custody_append.begin, then bump record_upload_revision '
            'only after durable acceptance in finish, including after rollback. A lost accepted fence recovers via '
            'record_custody_append.recover_committed with an exact-request durable receipt and partial continuation. '
            'Separate recovery is parked as record_recovery_waiting until record_recovery_gate.promote '
            'transactionally observes the original publication complete; promotion runs off/shadow/serve. '
            'Recovery is independent of '
            'conversation status; uncaptured input reopens for normal admission of the newer revision. Never deletes audio.',
        ),
        row(
            'record_audio',
            'seal_refused',
            ('record_seal_refused_at',),
            entry_writers=(Writer('database/record_audio.py', 'seal_record_audio.commit'),),
            exit=Exit('callback-only', 'database/record_audio.py:seal_record_audio'),
            metric='omi_record_seal_refused_age_seconds',
            alert=Alert('omi-record-seal-refused-age', 'agent'),
            note='First producer-pending refusal clock, meaningful only while record_audio_closed is false. '
            'Normal successful seal after exact-token finish clears it; repair/nojob seals may retain a stale stamp. '
            'Closed stamped rows are excluded from sweeper classification and refusal count/age gauges. '
            'Age is not a deadline or seal authority. Metrics cover the existing bounded record_pending job page; '
            'the alert is a declaration, not a deployed rule. No-job visibility remains outside phase 1.',
        ),
        row(
            'record_audio',
            'abandoned',
            ('record_upload_sessions',),
            entry_writers=(ABANDON_RECORD_PRODUCER,),
            exit=Exit('sweeper', 'utils/batch_pipeline/record_seal_sweeper.py:sweep'),
            note='Conditional per-token view: a conversation can also have live reconnect tokens. '
            'Producer token gains abandoned_at, not a successful-drain clear. '
            'record_producer_proof.producer_tokens_dead accepts finite abandoned_at >= process_started_at; '
            'seal repair still requires archive discovery, retained-tail/finish proof and the privacy transaction '
            'before clearing the exact producer map and sealing. abandoned_at is an age anchor, not a deadline. '
            'The 30-second metadata admission deadline and bounded 1-60 second retry backoff are attempt bounds, '
            'not an end-to-end exit deadline; waiting for worker/future settlement and durable-tail repair is unbounded. '
            'outcome=abandoned is an event, not an authoritative dwell gauge or alert; those remain declared gaps',
        ),
        row(
            'record_audio_orphan',
            'capturing',
            ('record_upload_sessions',),
            exit=Exit('sweeper', 'utils/batch_pipeline/record_seal_sweeper.py:sweep'),
            deadline_exemption='No producer TTL: proven-dead repair needs scoped producer and retained-tail evidence; lead2 9d457c / 4bf62d',
            note='Conditional orphan view, not a new persisted phase: producer proven dead, complete retained-tail evidence, job-backed repair',
        ),
        row(
            'record_audio',
            'sealed',
            ('record_audio_closed',),
            # Bounded stock coverage for the no-job subset only, not all sealed captures.
            metric='omi_record_seal_nojob_count',
            alert=Alert('omi-record-nojob-stock', 'agent'),
            note='No job: manual digest-gated nojob recovery is not an automatic exit; freshtitles fix, no PR yet',
        ),
        row(
            'record_audio',
            'record_upload_failed',
            ('record_upload_failed',),
            exit=RECORD_REPAIR,
            note='Worker proof repair can clear the bit; reconnect-only retry remains a freshtitles fix, no PR yet',
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
            stamped=True,
            metric='listen_finalization_oldest_nonterminal_age_seconds',
            alert=Alert('omi-capture-oldest-nonterminal', 'agent'),
        ),
        row(
            'finalization',
            'leased',
            ('status',),
            exit=FINALIZER,
            deadline='lease_expires_at',
            stamped=True,
            metric='listen_finalization_oldest_nonterminal_age_seconds',
            alert=Alert('omi-capture-oldest-nonterminal', 'agent'),
        ),
        row(
            'finalization',
            'blocked_byok',
            ('finalization_status', 'status'),
            exit=FINALIZER,
            metric='omi_finalization_byok_new_oldest_age_seconds',
            alert=Alert('omi-finalization-byok-dwell-page', 'agent'),
            note='Lead2 ruling699300 (2026-11-08T15:13Z), PR #24938: active muted BYOK warning; '
            '259200s/1h threshold unchanged. Recent-cohort dwell from #24595; historical age is separate. '
            '14-day abandonment is computed from activity, not a deadline stamped at entry',
        ),
        row(
            'finalization',
            'dead_letter',
            ('finalization_status', 'status'),
            terminal=True,
            owner='backend/docs/runbooks/real-traffic-journeys.md',
            metric='listen_finalization_jobs',
            alert=Alert('omi-finalization-dead-letter-stock', 'agent'),
            alert_required=True,
            note='#24533 supplies stock and age alerts',
        ),
        row(
            'finalization',
            'completed',
            ('finalization_status', 'status'),
            terminal=True,
            owner='services/conversation_finalization.py',
            note='Publisher samples queued/leased/blocked_byok/dead_letter, not completed stock',
        ),
        row(
            'summary_debt',
            'pending',
            ('summary_first_pending_at', 'summary_due_at'),
            exit=SUMMARY,
            deadline='summary_due_at',
            stamped=True,
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
            quiescent=True,
            owner='utils/fair_use.py',
            note='Base enforcement state; read-path dwell gauge is not a fleet stock gauge',
        ),
        row(
            'fair_use',
            'warning',
            ('stage',),
            exit=DECAY,
            deadline='warning_until',
            stamped=True,
            metric='omi_fair_use_stage_dwell_seconds',
            note='#24531 adds warning expiry and downward decay',
        ),
        row(
            'fair_use',
            'throttle',
            ('stage',),
            exit=DECAY,
            deadline='throttle_until',
            stamped=True,
            metric='omi_fair_use_stage_dwell_seconds',
            note='#24531 fixes the previously absorbing stage',
        ),
        row(
            'fair_use',
            'restrict',
            ('stage',),
            exit=DECAY,
            deadline='restrict_until',
            stamped=True,
            metric='omi_fair_use_stage_dwell_seconds',
        ),
        row(
            'visibility',
            'bridge_pending',
            ('sync_bridge_pending',),
            exit=Exit('decay', 'utils/sync/bridge_pending.py:hidden'),
            deadline='expires_at',
            stamped=True,
            note='600-second nonrenewable visibility bound',
        ),
        row(
            'visibility',
            'transcribing_hold',
            ('home_transcription_pending_at', 'home_transcription_deadline_at'),
            exit=Exit('decay', 'utils/conversations/transcribing_hold.py:project'),
            deadline='home_transcription_deadline_at',
            stamped=True,
            note='Reader-enforced expiry keeps overdue rows visible; no dedicated dwell gauge/alert yet (homegate phase 1).',
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
            exit=(
                LEASE
                if name == 'leased'
                else (
                    Exit(
                        'sweeper',
                        'utils/batch_pipeline/held_dead_letter.py:HeldDeadLetter.tick',
                        (Writer('database/batch_pipeline_quarantine_recovery.py', 'expire_held_in_transaction'),),
                    )
                    if name == 'quarantined'
                    else BATCH
                )
            ),
            deadline=(
                'lease_until'
                if name == 'leased'
                else (
                    'held_deadline_at'
                    if name == 'quarantined'
                    else 'record_dead_letter_deadline_at' if name == 'record_pending' else None
                )
            ),
            stamped=name in {'leased', 'quarantined', 'record_pending'},
            metric=(
                'omi_batch_record_pending_new_oldest_age_seconds'
                if name == 'record_pending'
                else (
                    None
                    if name in ('committed', 'partial_retired', 'privacy_blocked')
                    else 'omi_batch_timeliness_new_oldest_age_seconds'
                )
            ),
            alert=(
                Alert('omi-record-pending-dwell', 'page')
                if name == 'record_pending'
                else (
                    None
                    if name in ('committed', 'partial_retired', 'privacy_blocked')
                    else Alert('omi-batch-unit-unpublished-2h', 'page')
                )
            ),
            terminal=name in ('committed', 'partial_retired', 'privacy_blocked'),
            alert_required=name != 'committed',
            owner=(
                'utils/batch_pipeline/serving.py'
                if name in ('committed', 'partial_retired', 'privacy_blocked')
                else None
            ),
            note=(
                'Barrier refusals stamp record_dead_letter_deadline_at with a full 14-day window; aged rows become dead/record_barrier_aged under BATCH_HELD_DEAD_LETTER_ENABLED. Private OIDC requeue-record retains the privacy fence and custody. '
                '#24595 supplies recent-cohort age/page'
                if name == 'record_pending'
                else (
                    'GPU holds gain seven-day expiry and nightly requeue; provider-STT holds remain fenced from the GPU ring.'
                    if name == 'quarantined'
                    else ''
                )
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
    + (
        row(
            'batch',
            'dead',
            ('state',),
            terminal=True,
            owner='database/batch_pipeline_quarantine_recovery.py',
            deadline='held_deadline_at',
            exit=Exit('sweeper', 'utils/batch_pipeline/held_dead_letter.py:HeldDeadLetter.tick'),
            metric='omi_batch_held_expired_units',
            alert=Alert('omi-batch-held-expired-volume', 'agent'),
            alert_required=True,
            note='Reason held_expired is retained stock, never TTL/deletion; nightly UTC and private OIDC requeue. Reason input_expiring is retained at audio_staged_at (else legacy enqueued_at) + 29d for staging GPU/assignment holds under BATCH_INPUT_EXPIRING_ENABLED (default on); no nightly/poll exit. Only checked operator GPU requeue, target-restorable assignment release, or exact-bundle GPU re-upload exits it; the preterminal staged_input age warning fires above 21d. Record reason record_barrier_aged retains merge_pending=false, record_dead_letter_deadline_at and record_dead_letter_at; omi_batch_record_dead_letter_units and omi-batch-record-dead-letter-volume (agent); private OIDC requeue-record only.',
        ),
    )
    + tuple(
        row(
            'batch_projection',
            name,
            ('projection_state',),
            exit=(
                Exit('sweeper', 'database/batch_pipeline_projection_release.py:ProjectionReleaseStore.release')
                if name == 'quarantine_held'
                else BATCH
            ),
            deadline='held_deadline_at' if name == 'quarantine_held' else None,
            terminal=name in ('completed', 'erased'),
            owner='database/batch_pipeline_projection.py' if name in ('completed', 'erased') else None,
            metric=(
                None
                if name in ('completed', 'erased')
                else (
                    'omi_batch_held_oldest_age_seconds'
                    if name == 'quarantine_held'
                    else 'omi_batch_timeliness_new_oldest_age_seconds'
                )
            ),
            alert=(
                None
                if name in ('completed', 'erased')
                else (
                    Alert('omi-pipeline-held-row-age', 'page')
                    if name == 'quarantine_held'
                    else Alert('omi-batch-unit-unpublished-2h', 'page')
                )
            ),
            note=(
                'Committed assignment holds, including real-held gate failures without privacy refusal or open operator intent, retain quarantine_held with held_deadline_at, held_expired_at and held_expired_reason; nightly re-drive; omi_batch_held_expired_units and omi-batch-held-expired-volume (agent). Privacy holds are excluded. Legacy ready-receipt ghosts have a ready-hint exit plus an inert ghost_settled_cohort marker in the same transaction: BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_ENABLED default OFF, 24h committed age floor, max 16 per pass; off classifies existing reads only.'
                if name == 'quarantine_held'
                else 'Result projection receipt state, distinct from batch job state'
            ),
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


@dataclass(frozen=True)
class OrderingRule:
    name: str
    fields: tuple[str, ...]
    source: tuple[Writer, ...]
    waits_on: str


ORDERING_RULES = (
    OrderingRule(
        'late_result_commit_rearms_titling',
        ('record_lane_owner', 'completed_before_results', 'batch_result_count', 'rearm_on_result_commit'),
        (Writer('database/batch_pipeline_projection.py', 'ProjectionStore.mark_enrichment'),),
        'covered by B2 durable late-result rearm control; e13891 corrects the initial f1e35a premise',
    ),
    OrderingRule(
        'completed_capture_has_closed_audio',
        ('record_lane_owner', 'status', 'record_audio_closed', 'record_upload_sessions', 'record_audio_partial'),
        (Writer('utils/conversations/lifecycle.py', 'complete'),),
        'phase ordering follow-up, no fix PR yet; uicleanup intake; ruling f1e35a',
    ),
)


def durable_titling_rearm(before, after):
    """A pending outbox increment is durable evidence; an unchanged row is not."""
    old_version = (before or {}).get('version', 0)
    row = after or {}
    version = row.get('version')
    due = row.get('due_at')
    return bool(
        type(old_version) is int
        and type(version) is int
        and version > old_version
        and not row.get('dormant')
        and isinstance(row.get('task_token'), str)
        and row['task_token']
        and type(due) in (int, float)
        and math.isfinite(cast(float, due))
    )


def ordering_holds(rule, row, *, batch_result_count=0, rearm_on_result_commit=False, completed_before_results=False):
    """Pure cross-store contract; B2 supplies simulator-derived store evidence.

    Early completion alone is allowed. If results later commit after that
    completion, their commit must durably rearm titling (e13891). A caller
    supplies the prior completion and current result/outbox store evidence.
    A completed/title bit alone is insufficient evidence of rearm. No account
    identifiers, fetching, client construction or other IO belongs here.
    """
    if row.get('record_lane_owner') not in {'batch_live_v1', 'batch_sync_v1'} or row.get('deleted'):
        return True
    if rule.name == 'late_result_commit_rearms_titling':
        return not completed_before_results or batch_result_count == 0 or rearm_on_result_commit
    if rule.name == 'completed_capture_has_closed_audio':
        return row.get('status') != 'completed' or bool(
            row.get('record_audio_closed')
            and not row.get('record_upload_sessions')
            and not row.get('record_audio_partial')
        )
    raise ValueError('unknown ordering rule')
