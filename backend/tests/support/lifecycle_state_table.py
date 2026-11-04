"""Reviewed legacy lifecycle inventory for WP-B (source base 1ee787ba63c4).

This is a declaration of existing mechanisms, not a new runtime state machine.
Phase strings are the compatibility reader's strings. Derived phases do not
have their own writes; entered_by lists the legacy field payload builders.
The AST inventory is deliberately conservative: it includes payload builders
and response/query dictionaries, so indirect transaction writes remain visible.
It proves ownership/field coverage, not execution or bounded liveness (WP-B2).
"""

from dataclasses import dataclass

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
    deadline_entries: tuple[EntryPath, ...] = ()
    alert_required: bool = True
    quiescent: bool = False

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


FINALIZATION_MODULE = 'database/conversation_finalization_jobs.py'
FAIR_USE_MODULE = 'utils/fair_use.py'


def entry(module, function, field, state=None, *, inplace=False, **bindings):
    return EntryPath(module, function, field, state, tuple(sorted(bindings.items())), inplace)


# Automatic entry paths are distinct from conservative payload builders.
DEADLINE_ENTRIES = {
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
    'visibility:bridge_pending': (
        entry('utils/sync/assignment.py', 'assign_in_transaction.plan', 'sync_bridge_pending', inplace=True),
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
):
    entries = DEADLINE_ENTRIES.get(f'{machine}:{state}', ())
    entered_by = (
        tuple(dict.fromkeys(Writer(path.module, path.function) for path in entries))
        if entries
        else writers(machine, *fields)
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
    )


FINALIZER = Exit('sweeper', 'services/conversation_finalization.py:reconcile_listen_finalization_jobs')
BATCH = Exit('sweeper', 'utils/batch_pipeline/serving.py:start_serving_from_env.run')
LEASE = Exit('lease', 'utils/batch_pipeline/scheduler.py:Scheduler.recover')
DECAY = Exit('decay', 'utils/fair_use.py:normalize_expired_restriction_state')
SUMMARY = Exit('sweeper', 'services/summary_debt_repair.py:tick')
RECORD_REPAIR = Exit('sweeper', 'utils/batch_pipeline/record_seal_worker.py:Worker.tick')
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
            exit=RECORD_REPAIR,
            note='Proof repair exists for job-backed captures; bounded dwell waits on freshtitles open-producer-token fix, no PR yet',
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
            metric='listen_finalization_oldest_blocked_byok_age_seconds',
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
            stamped=name == 'leased',
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
            alert_required=name != 'committed',
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


@dataclass(frozen=True)
class OrderingRule:
    name: str
    fields: tuple[str, ...]
    source: tuple[Writer, ...]
    waits_on: str


ORDERING_RULES = (
    OrderingRule(
        'finalization_after_batch_result_or_durable_rearm',
        ('record_lane_owner', 'finalization_status', 'batch_result_count', 'rearm_on_result_commit'),
        (Writer(FINALIZATION_MODULE, '_mark_finalization_completed_txn'),),
        'phase ordering follow-up, no fix PR yet; uicleanup intake; ruling f1e35a',
    ),
    OrderingRule(
        'completed_capture_has_closed_audio',
        ('record_lane_owner', 'status', 'record_audio_closed', 'record_upload_sessions', 'record_audio_partial'),
        (Writer('utils/conversations/lifecycle.py', 'complete'),),
        'phase ordering follow-up, no fix PR yet; uicleanup intake; ruling f1e35a',
    ),
)


def ordering_holds(rule, row, *, batch_result_count=0, rearm_on_result_commit=False):
    """Pure cross-store contract; B2 supplies simulator-derived store evidence.

    A rearm is a durable obligation bound to the future result-commit event,
    rather than an earlier callback or a completed/title bit. No account
    identifiers, fetching, client construction or other IO belongs here.
    """
    if row.get('record_lane_owner') not in {'batch_live_v1', 'batch_sync_v1'} or row.get('deleted'):
        return True
    if rule.name == 'finalization_after_batch_result_or_durable_rearm':
        return row.get('finalization_status') != 'completed' or batch_result_count > 0 or rearm_on_result_commit
    if rule.name == 'completed_capture_has_closed_audio':
        return row.get('status') != 'completed' or bool(
            row.get('record_audio_closed')
            and not row.get('record_upload_sessions')
            and not row.get('record_audio_partial')
        )
    raise ValueError('unknown ordering rule')
