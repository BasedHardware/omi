"""Declarative census registry for batch pipeline stocks (W3 / PR1).

One entry per measurable stock. This module is the single source of truth for
the scheduled exact-count census (PR2 exporter), the CI completeness guard
(``tests/unit/test_batch_census_registry.py``) and ``KNOWN_STATES`` in
``scripts/batch_pipeline_poll_state_census.py``.

It is declarative only: no Firestore reads, no runtime state machine, no
retention or deletion behaviour. A declared clock/retention assumption is not
proof that an object exists, that a bucket policy is present, that a copy is
the sole copy, or that deletion is imminent. Clocks whose provenance is not
verified in code are marked ``clock_verified=False`` and custody assumptions
carry ``provenance='unverified'``; neither is a current production fact.

Legacy and free-text reasons aggregate into the bounded ``legacy`` bucket.
Every label here is a fixed string, so no metric label is unbounded and no
document is read to build one.
"""

from __future__ import annotations

from dataclasses import dataclass

COLLECTION = 'COLLECTION'
COLLECTION_GROUP = 'COLLECTION_GROUP'

# Physical collection names per logical stock: production only.
#
# Prod and dev stage collections live in one Firestore project, and reading both
# doubles the cost of every stage-scoped stock. The production census therefore
# reads exactly one collection per stock — one count aggregation and at most one
# clock-only oldest-row read — and dev-stage rows are excluded from production
# totals. Dev traffic is measured by its own environment, never folded in here.
COLLECTIONS = {
    'jobs': ('batch_pipeline_prod_jobs',),
    'results': ('batch_pipeline_prod_results',),
    'provider_outbox': ('batch_pipeline_prod_provider_stt_outbox',),
    'speaker_outbox': ('batch_pipeline_prod_speaker_final_pass_outbox',),
    'memory_outbox': ('memory_outbox',),
    'enrichment_outbox': ('sync_reprocess_outbox',),
    # Reads are collection-group: holds live under ``users/{uid}/stt_cap_holds``
    # and ledger rows under ``users/{uid}/pipeline_ledger``.
    'cap_holds': ('stt_cap_holds',),
    'pipeline_ledger': ('pipeline_ledger',),
}

# Bounded reason vocabularies. ``legacy`` is the single bucket for free-text or
# out-of-enum values written before the current vocabulary; it is never split
# per value, so a legacy row cannot create a new metric label.
VENDOR_HOLD_REASONS = (
    'unknown',
    'no_healthy_vendor',
    'funds_refusal',
    'cap_reached',
    'rate_limited',
    'health_unavailable',
    'legacy',
)
QUARANTINE_REASONS = ('worker_failed', 'legacy')
DEAD_REASONS = ('held_expired', 'input_expiring', 'record_barrier_aged', 'legacy')
PRIVACY_REASONS = (
    'account_deleted',
    'account_missing',
    'data_protection_changed',
    'privacy_generation_changed',
    'conversation_redirect_cycle',
    'conversation_fence_budget',
    'conversation_deleted',
    'recording_privacy_changed',
    'conversation_redirect_missing',
    'result_lease_lost',
    'unknown',
    'legacy',
)

# The spend-gate subset of ``utils.observability.reasons.AdmissionHoldReason``:
# a refusal that lasts until the owner's plan or budget changes. Fair use, the
# daily ceiling, privacy and consent holds stay in ``batch:ready_parked``.
ALLOWANCE_HOLD_REASONS = ('allowance_exhausted', 'allowance_unavailable', 'budget_exhausted')

# States that represent an unpublished unit in the deep-backlog band. Terminal
# and delivered states are excluded: an old ``dead`` row is not a backlog.
DEEP_BACKLOG_STATES = (
    'record_pending',
    'ready',
    'leased',
    'retry',
    'result_ready',
    'vendor_held',
    'quarantined',
    'provider_pending',
    'provider_running',
)
DEEP_BACKLOG_SECONDS = 7 * 86400


@dataclass(frozen=True)
class AgeCutoff:
    """A relative ``clock < now - seconds`` filter, resolved by the exporter.

    Bands (for example the 7-day deep backlog) cannot be expressed as a static
    value in a declarative registry, and a registry must not read the wall clock
    at import. The exporter resolves the cutoff from the sample moment.
    """

    seconds: float


@dataclass(frozen=True)
class Alarm:
    """Alarm metadata for a stock. ``None`` means no dedicated rule yet."""

    uid: str | None = None
    tier: str | None = None
    warn_seconds: int | None = None
    page_seconds: int | None = None


@dataclass(frozen=True)
class Custody:
    """A declared expiry assumption, never proof of object existence.

    ``clock`` is the field the horizon is measured from, ``retention_seconds``
    the assumed lifetime after that clock, and ``provenance`` one of
    ``declared`` (a stamped deadline field exists in code), ``unverified`` (a
    documented policy or proxy that was not measured) or ``none``.
    """

    clock: str | None
    retention_seconds: int | None
    provenance: str
    note: str = ''


@dataclass(frozen=True)
class CensusEntry:
    machine: str
    state: str
    collection: str
    scope: str
    field: str
    filters: tuple[tuple[str, str, object], ...]
    clock: str | None
    clock_verified: bool
    custody: Custody | None
    owner: str
    ceiling: int | None
    alarm: Alarm
    legacy: bool = False
    reason_field: str | None = None
    reasons: tuple[str, ...] = ()
    note: str = ''
    # Per-stock age alarm rendered into backend/charts/monitoring/alerts by
    # scripts/generate_batch_census_alerts.py. None means "measured, not alarmed".
    age_alarm_seconds: int | None = None
    age_alarm_severity: str | None = None

    @property
    def key(self) -> str:
        return f'{self.machine}:{self.state}'


_CENSUS_ALARM = Alarm('omi-batch-census-units', 'agent')
_FRESH_ALARM = Alarm('omi-batch-fresh-wait', 'page', warn_seconds=1800, page_seconds=7200)
_UNPUBLISHED_ALARM = Alarm('omi-batch-unit-unpublished-2h', 'page', page_seconds=7200)
_HELD_ALARM = Alarm('omi-pipeline-held-row-age', 'page')
_RECORD_ALARM = Alarm('omi-record-pending-dwell', 'page')

# Result objects are assumed to live 30 days after settle; the bucket policy was
# not readable from the planning role, so this stays unverified.
_RESULT_CUSTODY = Custody('provider_intent.settled_at', 30 * 86400, 'unverified', 'bucket lifecycle not measured')
# Results documents carry committed_at, not provider_intent (that field is job-only).
_PROJECTION_CUSTODY = Custody('committed_at', 30 * 86400, 'unverified', 'bucket lifecycle not measured')
_HELD_CUSTODY = Custody('held_deadline_at', 0, 'declared', 'stamped deadline; expiry is a re-drive, not deletion')
_RECORD_CUSTODY = Custody('record_dead_letter_deadline_at', 0, 'declared', 'stamped 14-day barrier deadline')
_OUTBOX_CUSTODY = Custody('created_at', 31 * 86400, 'unverified', 'Cloud Tasks retention is documented, not measured')
_VENDOR_CUSTODY = Custody('enqueued_at', 29 * 86400, 'unverified', 'enqueue proxy; no dedicated vendor clock')
# Speaker obligations carry no acceptance timestamp at all; the only clock is the
# retry wake, so an age reading is a lower bound on the wait.
_SPEAKER_CUSTODY = Custody('due_at', None, 'none', 'no stamped acceptance clock; due_at is a retry wake')
_OWNER = 'batch-pipeline'


def _job(
    state: str,
    *,
    clock: str = 'enqueued_at',
    custody: Custody | None = None,
    ceiling: int | None = None,
    alarm: Alarm = _CENSUS_ALARM,
    reason_field: str | None = None,
    reasons: tuple[str, ...] = (),
    note: str = '',
    age_alarm_seconds: int | None = None,
    age_alarm_severity: str = 'warning',
) -> CensusEntry:
    return CensusEntry(
        'batch',
        state,
        'jobs',
        COLLECTION,
        'state',
        (('state', '==', state),),
        clock=clock,
        clock_verified=True,
        custody=custody,
        owner=_OWNER,
        ceiling=ceiling,
        alarm=alarm,
        reason_field=reason_field,
        reasons=reasons,
        note=note,
        age_alarm_seconds=age_alarm_seconds,
        age_alarm_severity=age_alarm_severity if age_alarm_seconds is not None else None,
    )


def _projection(
    state: str,
    *,
    clock: str | None = 'committed_at',
    clock_verified: bool = True,
    custody: Custody | None = None,
    ceiling: int | None = None,
    alarm: Alarm = _CENSUS_ALARM,
    legacy: bool = False,
    note: str = '',
    age_alarm_seconds: int | None = None,
    age_alarm_severity: str = 'warning',
) -> CensusEntry:
    return CensusEntry(
        'batch_projection',
        state,
        'results',
        COLLECTION,
        'projection_state',
        (('projection_state', '==', state),),
        clock=clock,
        clock_verified=clock_verified,
        custody=custody,
        owner=_OWNER,
        ceiling=ceiling,
        alarm=alarm,
        legacy=legacy,
        note=note,
        age_alarm_seconds=age_alarm_seconds,
        age_alarm_severity=age_alarm_severity if age_alarm_seconds is not None else None,
    )


def _recovery(state: str, *, ceiling: int | None = None, age_alarm_seconds: int | None = None) -> CensusEntry:
    # recovery_state literals are not yet part of the AST discovery guard
    # (SCA-1921 follow-up): the shared writer inventory does not track this
    # field, so a new recovery state can ship without a registry entry. The
    # declared vocabulary below is complete for current main only.
    return CensusEntry(
        'batch_recovery',
        state,
        'jobs',
        COLLECTION,
        'recovery_state',
        (('recovery_state', '==', state),),
        clock='enqueued_at',
        clock_verified=True,
        custody=None,
        owner=_OWNER,
        ceiling=ceiling,
        alarm=_CENSUS_ALARM,
        note='recovery_state is not AST-guarded yet, so a new recovery state would not fail CI (follow-up)',
        age_alarm_seconds=age_alarm_seconds,
        age_alarm_severity='warning' if age_alarm_seconds is not None else None,
    )


def _stock(
    machine: str,
    state: str,
    collection: str,
    filters: tuple[tuple[str, str, object], ...],
    *,
    scope: str = COLLECTION,
    clock: str | None = None,
    clock_verified: bool = False,
    custody: Custody | None = None,
    ceiling: int | None = None,
    field: str = 'state',
    note: str = '',
    age_alarm_seconds: int | None = None,
    age_alarm_severity: str = 'warning',
) -> CensusEntry:
    """A stock outside the job/projection lifecycle, declared by explicit filters."""
    return CensusEntry(
        machine,
        state,
        collection,
        scope,
        field,
        filters,
        clock=clock,
        clock_verified=clock_verified,
        custody=custody,
        owner=_OWNER,
        ceiling=ceiling,
        alarm=_CENSUS_ALARM,
        note=note,
        age_alarm_seconds=age_alarm_seconds,
        age_alarm_severity=age_alarm_severity if age_alarm_seconds is not None else None,
    )


def _simple(
    machine: str,
    state: str,
    collection: str,
    field: str,
    *,
    scope: str = COLLECTION,
    clock: str | None = None,
    clock_verified: bool = False,
    custody: Custody | None = None,
    ceiling: int | None = None,
    age_alarm_seconds: int | None = None,
    note: str = '',
) -> CensusEntry:
    return CensusEntry(
        machine,
        state,
        collection,
        scope,
        field,
        ((field, '==', state),),
        clock=clock,
        clock_verified=clock_verified,
        custody=custody,
        owner=_OWNER,
        ceiling=ceiling,
        alarm=_CENSUS_ALARM,
        note=note,
        age_alarm_seconds=age_alarm_seconds,
        age_alarm_severity='warning' if age_alarm_seconds is not None else None,
    )


# --- batch job states -------------------------------------------------------
# The full job lifecycle, including the provider trio that the lifecycle table
# does not carry and the late-audio recovery park. ``record_recovery_waiting``
# is written with ``merge_pending: False``, so the merge-pending complement
# census does not see it; this registry's own count is what measures it.
JOB_ENTRIES = (
    _job(
        'record_pending',
        # Age is dwell since admission, never the stamped 14-day barrier
        # deadline: `now - deadline` is negative for the whole legitimate wait
        # and would read a healthy 0. The alarm is the barrier-approach page.
        clock='enqueued_at',
        custody=_RECORD_CUSTODY,
        ceiling=50_000,
        alarm=_RECORD_ALARM,
        age_alarm_seconds=13 * 86400,
        age_alarm_severity='critical',
        note='dwell since admission; the 14-day record barrier stays in custody metadata',
    ),
    _job(
        'ready',
        ceiling=100_000,
        alarm=_UNPUBLISHED_ALARM,
        note='every ready row, including parked holds; the runnable/parked split is published separately',
    ),
    _job(
        'leased',
        # A leased row is owned; `lease_until` is a future deadline and would
        # read 0 for every healthy lease. Read dwell and leave paging to the
        # lease-recovery metrics.
        clock='enqueued_at',
        ceiling=50_000,
        alarm=_UNPUBLISHED_ALARM,
        note='dwell since admission; a live lease is not a stuck row',
    ),
    _job(
        'retry',
        ceiling=100_000,
        alarm=_UNPUBLISHED_ALARM,
        age_alarm_seconds=21600,
        age_alarm_severity='critical',
    ),
    _job(
        'result_ready',
        custody=_RESULT_CUSTODY,
        ceiling=2_000_000,
        alarm=_UNPUBLISHED_ALARM,
        note='provider-lane rows only; record-lane rows have no provider_intent, so their horizon is null',
        age_alarm_seconds=7200,
        age_alarm_severity='critical',
    ),
    _job(
        'vendor_held',
        custody=_VENDOR_CUSTODY,
        ceiling=50_000,
        alarm=_UNPUBLISHED_ALARM,
        reason_field='vendor_hold.reason',
        reasons=VENDOR_HOLD_REASONS,
        age_alarm_seconds=86400,
    ),
    _job(
        'quarantined',
        # Dwell, not `held_deadline_at` (hold + 7 days, always future): the
        # deadline clock reads 0 for a week of real quarantine.
        clock='enqueued_at',
        custody=_HELD_CUSTODY,
        ceiling=50_000,
        alarm=_HELD_ALARM,
        reason_field='quarantine_reason',
        reasons=QUARANTINE_REASONS,
        age_alarm_seconds=86400,
        note='dwell since admission; the 7-day held deadline stays in custody metadata',
    ),
    _job(
        'privacy_blocked',
        ceiling=10_000,
        reason_field='privacy_blocked_reason',
        reasons=PRIVACY_REASONS,
        age_alarm_seconds=86400,
    ),
    _job('partial_retired', ceiling=10_000),
    _job(
        'committed',
        custody=_RESULT_CUSTODY,
        ceiling=100_000,
        note='provider-lane rows only; record-lane rows have no provider_intent, so their horizon is null',
    ),
    _job(
        'dead',
        clock='enqueued_at',
        custody=_HELD_CUSTODY,
        ceiling=100_000,
        reason_field='dead_letter_reason',
        reasons=DEAD_REASONS,
    ),
    _job('provider_pending', ceiling=400_000, alarm=_FRESH_ALARM, age_alarm_seconds=604800),
    _job('provider_running', ceiling=50_000, alarm=_FRESH_ALARM, age_alarm_seconds=21600),
    _job('provider_superseded', clock='superseded_at', ceiling=50_000),
    _job(
        'record_recovery_waiting',
        ceiling=10_000,
        note='merge_pending=False; not covered by the merge-pending complement census',
        age_alarm_seconds=86400,
    ),
)

# --- result projection states ----------------------------------------------
PROJECTION_ENTRIES = (
    _projection('pending', ceiling=100_000, age_alarm_seconds=3600, age_alarm_severity='critical'),
    _projection('persisted', ceiling=100_000, age_alarm_seconds=3600, age_alarm_severity='critical'),
    _projection(
        'ready',
        custody=_PROJECTION_CUSTODY,
        ceiling=2_000_000,
        age_alarm_seconds=7200,
        age_alarm_severity='critical',
    ),
    _projection(
        'quarantine_held',
        # Results carry committed_at; held_deadline_at is the future deadline.
        clock='committed_at',
        custody=_HELD_CUSTODY,
        ceiling=50_000,
        alarm=_HELD_ALARM,
        age_alarm_seconds=86400,
        note='dwell since commit; the 7-day held deadline stays in custody metadata',
    ),
    _projection('completed', ceiling=2_000_000),
    _projection('erased', clock=None, clock_verified=False, ceiling=100_000),
    _projection(
        'claimed',
        clock=None,
        clock_verified=False,
        legacy=True,
        note='legacy rows seen in production; no current writer',
    ),
)

# --- job recovery states ----------------------------------------------------
RECOVERY_ENTRIES = tuple(
    _recovery(state, ceiling=ceiling, age_alarm_seconds=age_alarm_seconds)
    for state, ceiling, age_alarm_seconds in (
        ('held', 50_000, 86400),
        ('prepared', 50_000, 3600),
        ('running', 50_000, 3600),
        ('failed_held', 50_000, 86400),
        ('recovered', 100_000, None),
        ('cancelled', 10_000, None),
    )
)

# --- provider outbox --------------------------------------------------------
PROVIDER_OUTBOX_ENTRIES = (
    _simple(
        'provider_outbox',
        'open',
        'provider_outbox',
        'state',
        clock='created_at',
        clock_verified=True,
        custody=_OUTBOX_CUSTODY,
        ceiling=400_000,
        age_alarm_seconds=86400,
    ),
    _simple(
        'provider_outbox',
        'closed',
        'provider_outbox',
        'state',
        clock='created_at',
        clock_verified=True,
        ceiling=400_000,
    ),
)

# --- memory outbox ----------------------------------------------------------
# Rows live under ``{user_root}/memory_outbox``, so the fleet census needs the
# COLLECTION_GROUP twin of the existing COLLECTION-scoped due index.
# ``MemoryOutboxEvent`` carries no immutable acceptance clock: ``available_at``
# moves on every retry and may sit in the future, and ``lease_expires_at`` is a
# wake. Aging from either would clamp to 0 and report old outstanding work as
# healthy, so these stocks publish their count and the ``-1`` undated sentinel
# until the writer stamps an acceptance timestamp. They have no dwell alarm for
# the same reason: an unknown age cannot have a threshold.
MEMORY_OUTBOX_ENTRIES = tuple(
    _simple(
        'memory_outbox',
        state,
        'memory_outbox',
        'status',
        scope=COLLECTION_GROUP,
        clock=None,
        clock_verified=False,
        ceiling=ceiling,
        note='no immutable acceptance clock (available_at is a retry/wake clock): count plus the -1 undated sentinel',
    )
    for state, ceiling in (
        ('pending', 2_000_000),
        ('processing', 100_000),
        ('delivered', 2_000_000),
        ('retryable_failure', 100_000),
        ('dead_letter', 100_000),
    )
)

# --- enrichment outbox ------------------------------------------------------
# ``sync_reprocess_outbox`` rows are deleted when the obligation completes, so
# the whole collection is one stock. ``first_pending_at`` is stamped on every
# durable obligation and is not reset by an append or a retry.
ENRICHMENT_OUTBOX_ENTRIES = (
    _stock(
        'enrichment_outbox',
        'pending',
        'enrichment_outbox',
        (),
        clock='first_pending_at',
        clock_verified=True,
        ceiling=100_000,
        field='first_pending_at',
        note='every row is a live obligation; parked rows are counted separately',
        age_alarm_seconds=86400,
    ),
    _stock(
        'enrichment_outbox',
        'parked',
        'enrichment_outbox',
        (('age_gate_parked', '==', True),),
        clock='first_pending_at',
        clock_verified=True,
        ceiling=2_000_000,
        field='age_gate_parked',
        note='age-gate parking is deliberate and reversible; old parked rows are expected, not stuck',
    ),
    _stock(
        'enrichment_outbox',
        'sync_hold',
        'enrichment_outbox',
        (('sync_hold', '==', True),),
        clock='first_pending_at',
        clock_verified=True,
        ceiling=100_000,
        field='sync_hold',
        note='held behind a live capture; the hold has a stamped maximum, so age is a wait not a leak',
    ),
)

# --- speaker final-pass outbox ---------------------------------------------
# Speaker obligations carry no acceptance timestamp at all: ``due_at`` and
# ``repair_after`` move on retry and can be in the future. Publishing a count
# with the ``-1`` undated sentinel is the honest reading; a dwell alarm waits for
# a stamped acceptance clock at the writer.
SPEAKER_OUTBOX_ENTRIES = (
    _stock(
        'speaker_outbox',
        'open',
        'speaker_outbox',
        (('outcome', '==', None),),
        clock=None,
        clock_verified=False,
        custody=_SPEAKER_CUSTODY,
        ceiling=10_000,
        field='outcome',
        note='no acceptance clock (due_at is a retry wake): count plus the -1 undated sentinel',
    ),
    _stock(
        'speaker_outbox',
        'terminal_pending',
        'speaker_outbox',
        (('terminal_pending', '==', True),),
        clock=None,
        clock_verified=False,
        custody=_SPEAKER_CUSTODY,
        ceiling=10_000,
        field='terminal_pending',
        note='closed receipt waiting for its repair write; no acceptance clock, so count plus the -1 sentinel',
    ),
)

# --- over-cap (.stt) holds --------------------------------------------------
# Pending pre-STT holds live under ``{user_root}/stt_cap_holds``; the fleet
# census is a collection-group read. ``listed_at`` is the stamped hold clock.
_CRITICAL_CAP_HOLDS = frozenset({'staging', 'sealing'})
CAP_HOLD_ENTRIES = tuple(
    _stock(
        'cap_hold',
        state,
        'cap_holds',
        (('state', '==', state),),
        scope=COLLECTION_GROUP,
        clock='listed_at',
        clock_verified=True,
        ceiling=ceiling,
        note=note,
        age_alarm_seconds=age_alarm_seconds,
    )
    for state, ceiling, note, age_alarm_seconds in (
        (
            'held',
            6_000_000,
            'over-cap audio waiting on credits; months old is expected, so the stock is measured and not paged',
            None,
        ),
        ('staging', 10_000, 'live capture being encrypted into durable staging', 3600),
        ('sealing', 10_000, 'live staging being sealed into a hold', 3600),
        ('retained', 500_000, 'terminal retained hold; not actionable by this census', None),
        ('batch_admitted', 100_000, 'handed to a batch job; the job is the continuing obligation', None),
    )
)

# --- pipeline ledger (live admission) --------------------------------------
# ``pipeline_ledger`` is the in-flight capture ledger; rows live under
# ``{user_root}/pipeline_ledger``. ``capturing`` is live admission before seal.
LEDGER_ENTRIES = tuple(
    _stock(
        'pipeline_ledger',
        stage,
        'pipeline_ledger',
        (('stage', '==', stage),),
        scope=COLLECTION_GROUP,
        clock='admitted_at',
        clock_verified=True,
        ceiling=ceiling,
        field='stage',
        note=note,
        age_alarm_seconds=age_alarm_seconds,
        age_alarm_severity='critical',
    )
    for stage, ceiling, note, age_alarm_seconds in (
        ('capturing', 100_000, 'live admission before seal', 21600),
        ('sealed', 100_000, 'sealed capture waiting for transcription', 3600),
        ('transcribed', 100_000, 'transcript landed waiting for notes/enrichment', 1800),
        ('noted', 100_000, 'notes landed waiting for terminal projection', 1800),
    )
)

# --- derived stocks ---------------------------------------------------------
# Stocks that are a predicate over an existing collection rather than a state
# field. Each is the audit's own framing, spelled out as filters so the count
# and the oldest-age reading answer the same question.
_DERIVED_ENTRIES = (
    _stock(
        'batch',
        'committed_hidden',
        'results',
        (('projection_state', 'in', ('pending', 'persisted', 'ready', 'quarantine_held')),),
        clock='committed_at',
        clock_verified=True,
        ceiling=2_000_000,
        field='projection_state',
        note='committed results whose projection has not completed, so the conversation is not visible yet',
        age_alarm_seconds=7200,
        age_alarm_severity='critical',
    ),
    _stock(
        'batch',
        'ready_runnable',
        'jobs',
        (('state', '==', 'ready'), ('compute_decision.outcome', 'in', ('unattempted', 'allowed'))),
        clock='enqueued_at',
        clock_verified=True,
        ceiling=100_000,
        field='state',
        note='admissible ready rows; fields an earlier allow/unevaluated decision stamps, so no row can be hidden by the split',
        age_alarm_seconds=7200,
        age_alarm_severity='critical',
    ),
    _stock(
        'batch',
        'ready_parked',
        'jobs',
        (('state', '==', 'ready'), ('compute_decision.outcome', '==', 'held')),
        clock='compute_decision.at',
        clock_verified=True,
        ceiling=100_000,
        field='state',
        note='ready rows parked by a policy/capacity refusal; the hold clock is when the latest refusal landed',
    ),
    _stock(
        'batch',
        'allowance_held',
        'jobs',
        (
            ('compute_decision.outcome', '==', 'held'),
            ('compute_decision.reason', 'in', ALLOWANCE_HOLD_REASONS),
        ),
        clock='compute_decision.at',
        clock_verified=True,
        ceiling=100_000,
        field='compute_decision.outcome',
        note='spend-gate refusals (allowance/budget); durable until the plan changes, so measured and not paged',
    ),
    _stock(
        'batch',
        'deep_backlog',
        'jobs',
        (
            ('state', 'in', DEEP_BACKLOG_STATES),
            ('enqueued_at', '<', AgeCutoff(DEEP_BACKLOG_SECONDS)),
        ),
        clock='enqueued_at',
        clock_verified=True,
        ceiling=400_000,
        field='state',
        note='unpublished units older than the 7-day depth band; exact count where the timeliness backlog walk caps at 10000',
    ),
)

ENTRIES = (
    JOB_ENTRIES
    + PROJECTION_ENTRIES
    + RECOVERY_ENTRIES
    + PROVIDER_OUTBOX_ENTRIES
    + MEMORY_OUTBOX_ENTRIES
    + ENRICHMENT_OUTBOX_ENTRIES
    + SPEAKER_OUTBOX_ENTRIES
    + CAP_HOLD_ENTRIES
    + LEDGER_ENTRIES
    + _DERIVED_ENTRIES
)
BY_KEY = {entry.key: entry for entry in ENTRIES}

# The job vocabulary the merge-pending complement census treats as known. It is
# the registry's job states, not a hand-maintained list.
JOB_STATES = tuple(entry.state for entry in JOB_ENTRIES)


# --- writer-site scope for the completeness guard ---------------------------
# The guard scans exactly these modules' ``state`` payload sites. A new state at
# one of them fails CI; request-lane coalescing vocabularies are classified out
# below so they cannot create a false failure.
#
# Mixed-purpose batch modules write ``state`` on non-job documents (recovery
# intents, markers) and on job documents, sometimes inside the same transaction
# function. These modules stay in this job set so their job write remains
# discoverable; ``NON_JOB_STATE_SITES`` excludes only the reviewed (owner,
# state) payload sites that do not target a job document. A mutated job literal
# is a new, unexcluded value and still fails the census guard.
JOB_STATE_MODULES = (
    'utils/batch_pipeline/scheduler.py',
    'utils/batch_pipeline/live.py',
    'utils/batch_pipeline/retry_policy.py',
    'utils/batch_pipeline/provider_stt.py',
    'utils/batch_pipeline/provider_stt_admission.py',
    'utils/batch_pipeline/record_seal_nojob.py',
    'utils/batch_pipeline/record_lease_append.py',
    'utils/batch_pipeline/merge.py',
    'database/record_partial.py',
    'database/batch_pipeline_artifact_missing.py',
    'database/batch_pipeline_quarantine_recovery.py',
    'database/batch_pipeline_record_dead_letter.py',
    'database/batch_pipeline_record_lease_recovery.py',
    'database/batch_pipeline_recovery.py',
    'database/batch_pipeline_projection_release.py',
    'database/batch_pipeline_speech_redrive.py',
    'database/batch_pipeline_terminal_empty.py',
)

# Reviewed non-job state payload sites inside those mixed-purpose modules, keyed
# by (qualified owner, literal state value). Keep this per site: excluding a
# whole module would hide its job write (that is how ``result_ready`` in
# database/batch_pipeline_speech_redrive.py escaped the first census guard).
NON_JOB_STATE_SITES: dict[str, tuple[tuple[str, str], ...]] = {
    'database/batch_pipeline_artifact_missing.py': (
        ('ArtifactMissingStore.apply.commit', 'missing'),
        ('ArtifactMissingStore.restore_reupload.commit', 'restored'),
    ),
    'database/batch_pipeline_quarantine_recovery.py': (
        ('SilenceDispositionStore.complete_silence.commit', 'completed'),
        ('SilenceDispositionStore.prepare_silence.commit', 'prepared'),
    ),
    'database/batch_pipeline_speech_redrive.py': (
        ('SpeechRedriveStore.prepare.commit', 'prepared'),
        ('SpeechRedriveStore.settle.commit', 'completed'),
        ('SpeechRedriveStore.settle.commit', 'failed_held'),
        ('SpeechRedriveStore.start.commit', 'running'),
    ),
    'database/batch_pipeline_terminal_empty.py': (
        ('TerminalEmptyStore.complete.commit', 'completed'),
        ('TerminalEmptyStore.prepare.commit', 'prepared'),
    ),
}

# Batch-scope modules that write a ``state`` field only for a different
# document. Each is reviewed here; a new module writing ``state`` must be
# classified. Collection-scoped result and request-lane documents stay out of
# the job census entirely.
NON_JOB_STATE_MODULES = {
    'database/batch_pipeline_coalescing.py': 'request-lane intake coalescing, not a pipeline stock',
    'database/batch_pipeline_shadow.py': 'shadow-lane documents',
    'database/batch_pipeline_projection.py': 'result documents',
    'database/batch_pipeline_projection_privacy.py': 'result documents',
    'database/batch_pipeline_projection_session.py': 'result documents',
    'utils/batch_pipeline/contracts.py': 'VAD receipt documents',
    'utils/batch_pipeline/vendor_health.py': 'breaker documents',
}

PROJECTION_STATE_MODULES = (
    'database/batch_pipeline_projection.py',
    'database/batch_pipeline_projection_privacy.py',
    'database/batch_pipeline_projection_release.py',
    'database/batch_pipeline_projection_session.py',
    'database/batch_pipeline_purge.py',
    'utils/batch_pipeline/merge.py',
)


def entries_for(machine: str) -> tuple[CensusEntry, ...]:
    return tuple(entry for entry in ENTRIES if entry.machine == machine)


def states_for(machine: str) -> frozenset[str]:
    return frozenset(entry.state for entry in entries_for(machine))
