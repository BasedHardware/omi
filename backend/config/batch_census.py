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

# Physical collection names per logical stock. Stage-scoped collections are
# shared by prod and dev in one Firestore project, so both are declared.
COLLECTIONS = {
    'jobs': ('batch_pipeline_prod_jobs', 'batch_pipeline_dev_jobs'),
    'results': ('batch_pipeline_prod_results', 'batch_pipeline_dev_results'),
    'provider_outbox': (
        'batch_pipeline_prod_provider_stt_outbox',
        'batch_pipeline_dev_provider_stt_outbox',
    ),
    'memory_outbox': ('memory_outbox',),
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
    runnable_exclude: tuple[tuple[str, str, object], ...]
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
    runnable_exclude: tuple[tuple[str, str, object], ...] = (),
    note: str = '',
) -> CensusEntry:
    return CensusEntry(
        'batch',
        state,
        'jobs',
        COLLECTION,
        'state',
        (('state', '==', state),),
        runnable_exclude,
        clock,
        True,
        custody,
        _OWNER,
        ceiling,
        alarm,
        reason_field=reason_field,
        reasons=reasons,
        note=note,
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
) -> CensusEntry:
    return CensusEntry(
        'batch_projection',
        state,
        'results',
        COLLECTION,
        'projection_state',
        (('projection_state', '==', state),),
        (),
        clock,
        clock_verified,
        custody,
        _OWNER,
        ceiling,
        alarm,
        legacy=legacy,
        note=note,
    )


def _recovery(state: str, *, ceiling: int | None = None) -> CensusEntry:
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
        (),
        'enqueued_at',
        True,
        None,
        _OWNER,
        ceiling,
        _CENSUS_ALARM,
        note='recovery_state is not AST-guarded yet, so a new recovery state would not fail CI (follow-up)',
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
) -> CensusEntry:
    return CensusEntry(
        machine,
        state,
        collection,
        scope,
        field,
        ((field, '==', state),),
        (),
        clock,
        clock_verified,
        custody,
        _OWNER,
        ceiling,
        _CENSUS_ALARM,
    )


# --- batch job states -------------------------------------------------------
# The full job lifecycle, including the provider trio that the lifecycle table
# does not carry and the late-audio recovery park. ``record_recovery_waiting``
# is written with ``merge_pending: False``, so the merge-pending complement
# census does not see it; this registry's own count is what measures it.
JOB_ENTRIES = (
    _job(
        'record_pending',
        clock='record_dead_letter_deadline_at',
        custody=_RECORD_CUSTODY,
        ceiling=50_000,
        alarm=_RECORD_ALARM,
    ),
    _job(
        'ready',
        ceiling=100_000,
        alarm=_UNPUBLISHED_ALARM,
        runnable_exclude=(('compute_decision.outcome', '==', 'held'),),
    ),
    _job('leased', clock='lease_until', ceiling=50_000, alarm=_UNPUBLISHED_ALARM),
    _job('retry', ceiling=100_000, alarm=_UNPUBLISHED_ALARM),
    _job('allowance_held', note='Policy parked; no expiry or late-work alarm; entitlement-generation release.'),
    _job(
        'result_ready',
        custody=_RESULT_CUSTODY,
        ceiling=2_000_000,
        alarm=_UNPUBLISHED_ALARM,
        note='provider-lane rows only; record-lane rows have no provider_intent, so their horizon is null',
    ),
    _job(
        'vendor_held',
        custody=_VENDOR_CUSTODY,
        ceiling=50_000,
        alarm=_UNPUBLISHED_ALARM,
        reason_field='vendor_hold.reason',
        reasons=VENDOR_HOLD_REASONS,
    ),
    _job(
        'quarantined',
        clock='held_deadline_at',
        custody=_HELD_CUSTODY,
        ceiling=50_000,
        alarm=_HELD_ALARM,
        reason_field='quarantine_reason',
        reasons=QUARANTINE_REASONS,
    ),
    _job(
        'privacy_blocked',
        ceiling=10_000,
        reason_field='privacy_blocked_reason',
        reasons=PRIVACY_REASONS,
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
        clock='held_deadline_at',
        custody=_HELD_CUSTODY,
        ceiling=100_000,
        reason_field='dead_letter_reason',
        reasons=DEAD_REASONS,
    ),
    _job('provider_pending', ceiling=400_000, alarm=_FRESH_ALARM),
    _job('provider_running', ceiling=50_000, alarm=_FRESH_ALARM),
    _job('provider_superseded', clock='superseded_at', ceiling=50_000),
    _job(
        'record_recovery_waiting',
        ceiling=10_000,
        note='merge_pending=False; not covered by the merge-pending complement census',
    ),
)

# --- result projection states ----------------------------------------------
PROJECTION_ENTRIES = (
    _projection('pending', ceiling=100_000),
    _projection('persisted', ceiling=100_000),
    _projection('ready', custody=_PROJECTION_CUSTODY, ceiling=2_000_000),
    _projection(
        'quarantine_held',
        clock='held_deadline_at',
        custody=_HELD_CUSTODY,
        ceiling=50_000,
        alarm=_HELD_ALARM,
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
    _recovery(state, ceiling=ceiling)
    for state, ceiling in (
        ('held', 50_000),
        ('prepared', 50_000),
        ('running', 50_000),
        ('failed_held', 50_000),
        ('recovered', 100_000),
        ('cancelled', 10_000),
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
MEMORY_OUTBOX_ENTRIES = tuple(
    _simple(
        'memory_outbox',
        state,
        'memory_outbox',
        'status',
        scope=COLLECTION_GROUP,
        clock='available_at',
        clock_verified=True,
        ceiling=ceiling,
    )
    for state, ceiling in (
        ('pending', 2_000_000),
        ('processing', 100_000),
        ('delivered', 2_000_000),
        ('retryable_failure', 100_000),
        ('dead_letter', 100_000),
    )
)

ENTRIES = JOB_ENTRIES + PROJECTION_ENTRIES + RECOVERY_ENTRIES + PROVIDER_OUTBOX_ENTRIES + MEMORY_OUTBOX_ENTRIES
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
    'database/batch_pipeline_allowance_hold.py',
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
