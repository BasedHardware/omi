"""Privacy decisions and session census with closed, identifier-free labels."""

import asyncio
from collections import Counter as Counts
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import inspect
import logging
import hashlib
from dataclasses import dataclass, field
import threading
import time

from prometheus_client import Counter, Gauge, Histogram
from config.plan_catalog import PlanType
from database.batch_privacy_attempt import PrivacyAttempt, token_version
from database.firestore_tier_context import current_tier
from utils.async_tasks import create_named_task, drain_tasks, wait_for_event

logger = logging.getLogger(__name__)
FAMILIES = frozenset({'batch', 'external', 'tombstone', 'deletion_marker'})
REASONS = frozenset(
    {
        'allow',
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
        'destructive_operation',
        'authority_unavailable',
        'unknown',
    }
)
CHECKS = Counter('privacy_checks_total', 'Privacy check decisions', ['family', 'mode', 'reason', 'plan_group'])
CALLS = Counter('privacy_check_calls_total', 'Privacy check calls including invalid inputs', ['family', 'mode'])
READS = Counter(
    'privacy_check_reads_total', 'Privacy document reads issued', ['family', 'mode', 'result', 'plan_group']
)
WALKS = Counter('privacy_conversations_walked_total', 'Distinct conversation documents walked per check', ['mode'])
DECISION_MISMATCH = Counter(
    'privacy_decision_mismatch_total', 'Live and candidate privacy decisions disagree', ['family', 'reason']
)
COMPARISONS = Counter(
    'privacy_decision_comparison_total',
    'Live/candidate comparisons with identifier-free cache evidence',
    [
        'family',
        'result',
        'candidate_source',
        'cache_age',
        'token_versions',
        'generation_versions',
        'marker_changed',
        'cache_certification',
    ],
)
SHADOW_CHECKS = Counter('privacy_shadow_checks_total', 'Privacy shadow comparisons', ['family', 'result'])
MEMO_REQUESTS = Counter('privacy_memo_requests_total', 'Candidate decision reuse', ['family', 'result'])
NEGATIVE_LOOKUPS = Counter(
    'privacy_negative_lookup_total',
    'Token-certified NOT_FOUND lookup cache outcomes',
    ['collection', 'mode', 'result'],
)
TTL_BOUND_SECONDS = 60.0
MEMO_INELIGIBLE = Counter(
    'privacy_memo_ineligible_total',
    'Batch privacy decisions the attempt memo could not certify, by reason and calling module',
    ['reason', 'caller'],
)
# Bounded caller label: the known assert_batch_write_allowed call sites (git grep, 2026-11-05).
_INELIGIBLE_CALLERS = frozenset(
    {
        'database.batch_pipeline_projection',
        'database.batch_pipeline_projection_session',
        'database.batch_pipeline_quarantine_recovery',
        'database.batch_pipeline_recovery',
        'database.batch_pipeline_store',
        'database.batch_voice_evidence',
        'database.jobstore.postgres_store',
        'database.outbox_provider_stt',
        'services.summary_debt_repair',
        'utils.batch_pipeline.record_seal_repair',
        'utils.batch_pipeline.retention',
        'utils.enrichment.custody',
        'utils.enrichment.redrive',
        'utils.sync.completed_status',
        'utils.sync.retired_handle_ack',
    }
)
_PRIVACY_MODULES = frozenset({'database.batch_pipeline_privacy', 'database.privacy_check_metrics'})
TTL_CACHE = Counter(
    'privacy_ttl_cache_total', '60s-bounded privacy decision reuse (hit, miss, store)', ['family', 'result']
)
CENSUS = Histogram(
    'privacy_session_cycle_operations',
    'Operations in each completed 60 second session interval',
    ['plane', 'family', 'mode', 'kind'],
    buckets=(0, 1, 2, 3, 4, 8, 16, 32, 64, 128, 256),
)

_MODE: ContextVar[str] = ContextVar('privacy_metrics_mode', default='live')
_READ_CALLER: ContextVar[str | None] = ContextVar('privacy_read_caller', default=None)
_READ_CALLERS = {
    'batch': 'database.batch_pipeline_privacy:read',
    'external': 'database.legal_holds:external_write_fence',
    'tombstone': 'database.conversation_tombstones:is_deleted',
    'deletion_marker': 'database.account_deletion_marker:_s4_read_deletion_status',
}
_SESSION: ContextVar['SessionCensus | None'] = ContextVar('privacy_metrics_session', default=None)
_LOG_LOCK = threading.Lock()
_LOG_AT = {}


# Margin meter: margin_core.segment_rollup / margin-basis.json split.segments.
_PLAN_SEGMENTS: dict[str, str] = {
    PlanType.basic: 'free',
    PlanType.architect: 'paid',
    PlanType.operator: 'paid',
    PlanType.plus: 'paid',
    PlanType.unlimited: 'paid',
    PlanType.unlimited_v2: 'unlimited_v2',
}


def plan_group(plan):
    """Explicit meter allowlist; legacy 'free' follows database.users normalization."""
    if not isinstance(plan, str):
        return 'unattributed'
    return _PLAN_SEGMENTS.get(plan, 'free' if plan == 'free' else 'unattributed')


@dataclass
class _BatchPlan:
    uid: str | None  # Scope identity only; never a metric label.
    group: str
    reads: Counts = field(default_factory=Counts)


_BATCH_PLAN: ContextVar[_BatchPlan | None] = ContextVar('privacy_batch_plan', default=None)


def observe_batch_plan(plan):
    """Consume only the user snapshot the authority walk already needed."""
    holder = _BATCH_PLAN.get()
    if holder is not None:
        holder.group = plan_group(plan)


def with_batch_plan(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        uid = kwargs.get('uid', args[2] if len(args) > 2 else None)
        holder = _BatchPlan(uid, plan_group(current_tier(uid)) if uid is not None else 'unattributed')
        token = _BATCH_PLAN.set(holder)
        try:
            return function(*args, **kwargs)
        finally:
            try:
                _BATCH_PLAN.reset(token)
                # At most six counters; a hard kill before exit drops this check's reads.
                for (mode, result), count in holder.reads.items():
                    READS.labels('batch', mode, result, holder.group).inc(count)
            except Exception:
                pass  # Including iteration faults: metrics never alter authority.

    return wrapped


def _plan_label(family, uid):
    holder = _BATCH_PLAN.get() if _family(family) == 'batch' else None
    if holder is not None:
        return holder.group if uid is None or uid == holder.uid else 'unattributed'
    return plan_group(current_tier(uid)) if uid is not None else 'unattributed'


@dataclass
class DecisionEvidence:
    # Private, request-scoped observations. Only closed relations leave compare().
    source: str = 'fresh_read'
    age: float | None = None
    certification: str = 'not_used'
    token_seen: bool = False
    token: object = None
    generation: object = None
    markers: dict = field(default_factory=dict)

    def cached(self, payload, age):
        self.age = age
        try:
            self.markers.update(payload.get('markers', {}))
        except (TypeError, ValueError):
            pass


_EVIDENCE: ContextVar[DecisionEvidence | None] = ContextVar('privacy_comparison_evidence', default=None)


@contextmanager
def evidence_scope(evidence):
    token = _EVIDENCE.set(evidence)
    try:
        yield evidence
    finally:
        _EVIDENCE.reset(token)


def current_evidence():
    return _EVIDENCE.get()


def observe_snapshot(reference, snapshot, family):
    evidence = _EVIDENCE.get()
    if evidence is None:
        return
    try:
        path = reference.path
        parts = path.split('/') if isinstance(path, str) else list(path)
        if parts[0] == 'batch_pipeline_privacy':
            data = snapshot.to_dict() or {}
            evidence.token_seen = True
            evidence.token = token_version(snapshot)
            evidence.generation = data.get('generation', 0)
        elif parts[0] in {'account_deletions', 'legal_hold_deletion_gates'} or (
            family == 'tombstone' and len(parts) == 4 and parts[2] == 'deleted_conversations'
        ):
            data = snapshot.to_dict() or {}
            # Fixed-size private fingerprint: no paths or marker payloads in cache
            # envelopes, logs or labels. Observe revisions AND state/existence.
            revision = getattr(snapshot, 'update_time', None)
            state = (
                snapshot.exists,
                str(revision),
                getattr(revision, 'nanosecond', 0),
                data.get('wipe_status'),
                data.get('state'),
            )
            # Closed keys keep cache metadata bounded to two fingerprints;
            # batch observes the owner erasure marker, not every source row.
            key = parts[0] if parts[0] != 'users' else 'deleted_conversations'
            evidence.markers[key] = hashlib.sha256(repr(state).encode()).hexdigest()
    except Exception:
        pass  # Instrumentation must not change the authoritative read.


def version_relation(left, right):
    if left is None or right is None:
        return 'unavailable'
    return 'same' if left == right else 'changed'


def age_bucket(age):
    if age is None:
        return 'unknown'
    if not isinstance(age, (int, float)) or not 0 <= age < float('inf'):
        return 'unknown'
    for bound, label in ((1, 'lt_1s'), (10, '1_10s'), (30, '10_30s'), (60, '30_60s')):
        if age < bound:
            return label
    return 'expired'


def comparison_labels(live, candidate):
    live, candidate = live or DecisionEvidence(), candidate or DecisionEvidence(source='unknown')
    observed = live.token_seen and candidate.token_seen
    common = live.markers.keys() & candidate.markers.keys()
    changed = (
        'true' if any(live.markers[k] != candidate.markers[k] for k in common) else ('false' if common else 'unknown')
    )
    return (
        candidate.source if candidate.source in {'ttl_hit', 'token_hit', 'session_hit', 'fresh_read'} else 'unknown',
        age_bucket(candidate.age),
        version_relation(live.token, candidate.token) if observed else 'unknown',
        version_relation(live.generation, candidate.generation) if observed else 'unknown',
        changed,
        (
            candidate.certification
            if candidate.certification in {'matched', 'mismatch', 'unavailable', 'miss'}
            else 'not_used'
        ),
    )


def _family(value):
    return value if value in FAMILIES else 'batch'


def _reason(value):
    return value if value in REASONS else 'unknown'


def _count(family, kind):
    session = _SESSION.get()
    if session is not None:
        with session.lock:
            if not session.closed:
                session.counts[(_family(family), _MODE.get(), kind)] += 1


def decision(family, reason='allow', *, uid=None):
    try:
        CHECKS.labels(_family(family), _MODE.get(), _reason(reason), _plan_label(family, uid)).inc()
    except Exception:
        pass  # Metrics must never alter authority decisions.


def called(family):
    try:
        CALLS.labels(_family(family), _MODE.get()).inc()
        _count(family, 'checks')
    except Exception:
        pass


TTL_KILL = Gauge('privacy_ttl_cache_disabled', '1 when the privacy decision cache kill switch is set or unreadable')


def ttl_kill_state(disabled):
    try:
        TTL_KILL.set(1 if disabled else 0)
    except Exception:
        pass


def ttl_result(family, result):
    try:
        result = result if result in {'hit', 'miss', 'store'} else 'miss'
        TTL_CACHE.labels(_family(family), result).inc()
    except Exception:
        pass


def memo_ineligible(reason):
    """Count why a batch decision skipped the attempt memo, attributed to the first non-privacy frame."""
    current = frame = None
    try:
        reason = reason if reason in {'no_attempt', 'no_transaction', 'snapshots'} else 'other'
        caller = 'other'
        current = inspect.currentframe()
        frame = current.f_back if current is not None else None
        for _ in range(8):
            if frame is None:
                break
            module = frame.f_globals.get('__name__', '')
            if module not in _PRIVACY_MODULES:
                caller = module if module in _INELIGIBLE_CALLERS else 'other'
                break
            frame = frame.f_back
        MEMO_INELIGIBLE.labels(reason, caller).inc()
    except Exception:
        pass
    finally:
        # Break the frame reference cycle so request frames are freed immediately.
        del current, frame


def memo_result(family, result):
    try:
        result = result if result in {'hit', 'miss', 'ineligible', 'no_token', 'mint', 'mint_error'} else 'ineligible'
        MEMO_REQUESTS.labels(_family(family), result).inc()
    except Exception:
        pass


def negative_lookup(collection, mode, result):
    try:
        collection = (
            collection if collection in {'account_deletions', 'deleted_conversations', 'conversations'} else 'other'
        )
        mode = 'shadow' if mode == 'shadow' else 'enforce'
        result = result if result in {'hit', 'miss', 'mismatch'} else 'miss'
        NEGATIVE_LOOKUPS.labels(collection, mode, result).inc()
    except Exception:
        pass


def read_snapshot(family, reference, *, read_budget=None, uid=None, **kwargs):
    """Count issued reads, including failures, without inspecting paths or payloads."""
    _count(family, 'reads')
    caller = _READ_CALLERS[_family(family)]
    caller_token = _READ_CALLER.set(caller)
    try:
        if read_budget is not None:
            kwargs.update(timeout=read_budget.timeout(10), retry=None)
        snapshot = reference.get(**kwargs)
    except BaseException:
        _read_result(family, 'error', uid=uid)
        raise
    finally:
        _READ_CALLER.reset(caller_token)
    _read_result(family, 'hit' if snapshot.exists else 'miss', uid=uid)
    observe_snapshot(reference, snapshot, family)
    return snapshot


def current_read_caller():
    """Only the closed names above may override SDK attribution."""
    return _READ_CALLER.get()


def _read_result(family, result, *, uid=None):
    try:
        holder = _BATCH_PLAN.get() if _family(family) == 'batch' else None
        if holder is not None and (uid is None or uid == holder.uid):
            holder.reads[(_MODE.get(), result)] += 1
        else:
            READS.labels(_family(family), _MODE.get(), result, _plan_label(family, uid)).inc()
    except Exception:
        pass


def walked():
    try:
        WALKS.labels(_MODE.get()).inc()
        _count('batch', 'conversations')
    except Exception:
        pass


@contextmanager
def mode_scope(mode):
    token = _MODE.set('shadow' if mode == 'shadow' else 'live')
    try:
        yield
    finally:
        _MODE.reset(token)


def compare(family, live, candidate, *, cached_age=None, live_evidence=None, candidate_evidence=None):
    """Emit only closed labels, never raw versions, paths or exception text.

    TTL is an upper bound, never permission for a stale ALLOW. Version fields
    describe live versus candidate observations, not raw token values. A marker
    change is known only when both sides observed the same marker (including
    a cached observation); token rotation alone does not prove marker change.
    """
    family, live, candidate = _family(family), _reason(live), _reason(candidate)
    mismatch = live != candidate
    try:
        if candidate_evidence is None and cached_age is not None:
            candidate_evidence = DecisionEvidence(age=cached_age)
        labels = comparison_labels(live_evidence, candidate_evidence)
        COMPARISONS.labels(family, 'mismatch' if mismatch else 'match', *labels).inc()
        SHADOW_CHECKS.labels(family, 'mismatch' if mismatch else 'match').inc()
        if mismatch:
            reason = 'stale_allow' if candidate == 'allow' else 'stale_block' if live == 'allow' else 'block_reason'
            DECISION_MISMATCH.labels(family, reason).inc()
            # Preserve at most one fixed-size line per family per minute.
            with _LOG_LOCK:
                now = time.monotonic()
                if now - _LOG_AT.get(family, -60.0) >= 60:
                    _LOG_AT[family] = now
                    logger.warning(
                        'privacy shadow decision_mismatch family=%s reason=%s live=%s candidate=%s '
                        'candidate_source=%s cache_age=%s token_versions=%s generation_versions=%s '
                        'marker_changed=%s cache_certification=%s',
                        family,
                        reason,
                        live,
                        candidate,
                        *labels,
                    )
    except Exception:
        pass


def shadow_error(family):
    try:
        SHADOW_CHECKS.labels(_family(family), 'error').inc()
    except Exception:
        pass


class SessionCensus:
    def __init__(self, plane):
        self.plane = 'pusher' if plane == 'pusher' else 'listen'
        self.counts = Counts()
        self.lock = threading.RLock()
        self.closed = False
        self.memo = PrivacyAttempt()

    def flush(self):
        with self.lock:
            if self.closed:
                return
            counts, self.counts = self.counts, Counts()
        for family in FAMILIES:
            for mode in ('live', 'shadow'):
                for kind in ('checks', 'reads', 'conversations'):
                    try:
                        CENSUS.labels(self.plane, family, mode, kind).observe(counts[(family, mode, kind)])
                    except Exception:
                        pass


def flush_session_census():
    session = _SESSION.get()
    if session is not None:
        session.flush()


def reset_session_census():
    """Start the first full interval after session bootstrap has completed."""
    session = _SESSION.get()
    if session is not None:
        with session.lock:
            session.counts.clear()


def session_memo():
    session = _SESSION.get()
    return session.memo if session is not None and not session.closed else None


async def _pusher_census_ticks(holder, stopped):
    from utils.executors import db_executor, run_blocking

    while not await wait_for_event(stopped, 60):
        try:
            await run_blocking(db_executor, holder.flush)
        except Exception:
            logger.warning('privacy pusher census flush failed')


def _pusher_census_done(task):
    if not task.cancelled() and task.exception() is not None:
        logger.warning('privacy pusher census ticker stopped unexpectedly')


def with_session_census(plane):
    def decorate(function):
        @wraps(function)
        async def wrapped(*args, **kwargs):
            holder = SessionCensus(plane)
            token = _SESSION.set(holder)
            stopped = asyncio.Event()
            ticker = (
                create_named_task(_pusher_census_ticks(holder, stopped), name='privacy:pusher:census')
                if holder.plane == 'pusher'
                else None
            )
            if ticker is not None:
                ticker.add_done_callback(_pusher_census_done)
            try:
                return await function(*args, **kwargs)
            finally:
                try:
                    if ticker is not None:
                        stopped.set()
                        await drain_tasks([ticker], timeout=5.0, label='privacy:pusher:census')
                finally:
                    with holder.lock:
                        holder.closed = True
                        holder.counts.clear()
                        holder.memo.close()
                    _SESSION.reset(token)

        return wrapped

    return decorate
