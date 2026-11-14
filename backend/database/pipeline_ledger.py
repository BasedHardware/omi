"""Write-only, fail-open in-flight ledger for the capture pipeline.

One document per capture under ``users/{uid}/pipeline_ledger/{capture_id}``.
The ledger is a measurement surface: it never serves a read path, never gates a
transition, and a ledger failure must never fail the real write. The stage
table, transition rules and document shape are plain data, so the contract can
move to Postgres without changing callers.

:func:`advance` runs its own Firestore transaction *after* the real transition
commits and catches every error. The trade-off is explicit: the ledger is not
atomic with the real transition, so a crash between the two loses that row; the
independent admission counter makes the loss visible. The ledger transaction
reads the document before writing it, so concurrent writers are serialized by
Firestore's optimistic concurrency (a CAS fence). The document never stores
titles, transcript or overview text, audio paths, secrets or raw content;
``owner_key`` is a truncated hash for distinct-user counts only.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import time
from datetime import datetime, timezone
from typing import Any, Iterator, Mapping, NamedTuple

from google.cloud import firestore
from prometheus_client import REGISTRY, Counter, Gauge, Histogram

from config.refactor_modes import pipeline_ledger_enabled
from database._client import get_firestore_client, run_transactional
from utils.observability.reasons import (
    PipelineLedgerFailureReason,
    PipelineLedgerOutcome,
    ReasonFamily,
    reason_label,
)

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
COLLECTION = 'pipeline_ledger'
MAX_TRANSITIONS = 16
DEFAULT_TERMINAL_TTL_SECONDS = 93600  # 26h: 24h exact census + 2h grace.
MAX_TERMINAL_TTL_SECONDS = 7 * 86400
DEFAULT_WINDOW_LIMIT = 5000

CAPTURING, SEALED, TRANSCRIBED, NOTED, DONE = 'capturing', 'sealed', 'transcribed', 'noted', 'done'
NO_SPEECH, NOISE, FAILED_PREFIX = 'no_speech', 'noise', 'failed:'

END_TYPES = frozenset({'user_initiated', 'jev_initiated', 'silence_backstop', 'unknown'})
SPEECH_BASES = frozenset({'vad', 'transcript', 'unknown'})
# Closed vocabulary for ``reason`` and ``terminal_reason``. Arbitrary text and
# user errors never reach the document.
REASONS = frozenset(
    'capture_started sealed transcribed noted done no_speech noise upload_failed privacy deleted timeout '
    'provider empty_output other'.split()
)
FAILURE_REASONS = frozenset('no_speech noise upload_failed privacy deleted timeout provider empty_output other'.split())


class StageRule(NamedTuple):
    """One nonterminal stage: how long it may sit and which stage it exits to."""

    deadline_seconds: int
    exit_stage: str


# Every nonterminal stage has a deadline and an exit. Terminals have neither.
STAGE_TABLE: dict[str, StageRule] = {
    CAPTURING: StageRule(6 * 3600, SEALED),
    SEALED: StageRule(3600, TRANSCRIBED),
    TRANSCRIBED: StageRule(1800, NOTED),
    NOTED: StageRule(1800, DONE),
}
TERMINAL_STAGES = frozenset({DONE, NO_SPEECH, NOISE})
STAGE_RANK = {CAPTURING: 0, SEALED: 1, TRANSCRIBED: 2, NOTED: 3, DONE: 4}
# A terminal may be re-opened only to these stages, and only with an explicit
# higher revision. A ``failed:*`` terminal may be re-opened to any nonterminal
# stage on a retry.
REOPEN_STAGES = frozenset({TRANSCRIBED, NOTED, DONE})


def _metric(name: str, kind: Any, doc: str, labels: tuple[str, ...] = ()) -> Any:
    return getattr(REGISTRY, '_names_to_collectors', {}).get(name) or kind(name, doc, list(labels))


_ADMIT = _metric('omi_pipeline_ledger_admit_total', Counter, 'Captures that entered the ledger pipeline.')
_WRITE = _metric('omi_pipeline_ledger_write_total', Counter, 'Ledger write outcomes.', ('outcome',))
_WRITE_FAILURES = _metric(
    'omi_pipeline_ledger_write_failures_total', Counter, 'Ledger write failures by bounded reason.', ('reason',)
)
_ROWS = _metric('omi_pipeline_ledger_rows', Gauge, 'Process-local ledger rows by stage.', ('stage',))
_TRANSITION = _metric(
    'omi_pipeline_ledger_transition_total', Counter, 'Accepted ledger stage transitions.', ('from', 'to')
)
_UNKNOWN_END = _metric(
    'omi_pipeline_ledger_unknown_end_type_total', Counter, 'Terminal ledger rows whose end type is unknown.'
)
_STAGE_SECONDS = _metric(
    'omi_pipeline_ledger_stage_seconds',
    Histogram,
    'Time spent in a ledger stage before its next transition.',
    ('stage',),
)


class Plan(NamedTuple):
    """The next ledger document, or why no write is needed."""

    doc: dict[str, Any] | None
    outcome: str


class LedgerWindowTruncated(RuntimeError):
    """The bounded ledger window hit its row limit; callers must fail closed."""


def is_terminal(stage: str) -> bool:
    return stage in TERMINAL_STAGES or stage.startswith(FAILED_PREFIX)


def failed_stage(reason: str | None) -> str:
    """Bounded low-cardinality failure terminal; unknown reasons collapse to ``other``."""
    return f'{FAILED_PREFIX}{reason if reason in FAILURE_REASONS else "other"}'


def stage_label(stage: str) -> str:
    """Metric label: failure reasons never become their own series."""
    if stage.startswith(FAILED_PREFIX):
        return 'failed'
    return stage if stage in STAGE_RANK or stage in TERMINAL_STAGES or stage == 'none' else 'other'


def bounded_reason(reason: Any) -> str:
    """Closed vocabulary; arbitrary text and user errors collapse to ``other``."""
    return reason if reason in REASONS else 'other'


def owner_key(uid: str) -> str:
    """Truncated hash for distinct-user counts; never the raw uid."""
    return hashlib.sha256(uid.encode()).hexdigest()[:16]


def terminal_ttl_seconds() -> int:
    """Terminal retention, clamped to the C2 census floor and the 7-day ceiling."""
    try:
        value = int(os.getenv('PIPELINE_LEDGER_TERMINAL_TTL_SECONDS', str(DEFAULT_TERMINAL_TTL_SECONDS)))
    except (TypeError, ValueError):
        value = DEFAULT_TERMINAL_TTL_SECONDS
    return max(DEFAULT_TERMINAL_TTL_SECONDS, min(MAX_TERMINAL_TTL_SECONDS, value))


def _epoch(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        moment = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        return moment.timestamp()
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return float(value)
    return None


# Public read helper for the C2 census; the write path keeps using ``_epoch``.
epoch = _epoch


def _pick(value: Any, existing: Mapping[str, Any] | None, key: str, default: Any = None) -> Any:
    return value if value is not None else (existing or {}).get(key, default)


def _bounded_end_type(value: Any) -> str:
    return value if value in END_TYPES else 'unknown'


def _bounded_speech_basis(value: Any) -> str:
    return value if value in SPEECH_BASES else 'unknown'


def _bounded_speech_seconds(value: Any) -> float | None:
    seconds = _epoch(value)
    return seconds if seconds is not None and seconds >= 0 else None


def plan_advance(
    existing: Mapping[str, Any] | None,
    stage: str,
    *,
    now: float | None = None,
    reason: str | None = None,
    end_type: str | None = None,
    end_at: Any = None,
    last_speech_at: Any = None,
    quiet_due_at: Any = None,
    revision: int | None = None,
    reopen: bool = False,
    speech_seconds: Any = None,
    has_speech: bool | None = None,
    speech_basis: str | None = None,
    home_ready_at: Any = None,
    episode_done_at: Any = None,
) -> Plan:
    """Pure transition plan. Never raises for a legal stage name.

    ``duplicate`` means the capture is already at this stage (safe to call
    repeatedly). ``stale`` means a supplied revision is not newer than the
    stored one. ``illegal`` means a backward or unknown transition.
    ``terminal`` means the capture already reached a terminal and cannot move
    again without an explicit, higher-revision re-open.
    """
    current = time.time() if now is None else now
    if stage.startswith(FAILED_PREFIX):
        # A caller cannot mint an arbitrary terminal reason: only the closed
        # failure vocabulary is stored, everything else collapses to ``other``.
        stage = failed_stage(stage[len(FAILED_PREFIX) :])
    if stage not in STAGE_TABLE and not is_terminal(stage):
        return Plan(None, 'illegal')
    previous = (existing or {}).get('stage')
    previous_revision = int((existing or {}).get('revision') or 0)
    previous_terminal = bool((existing or {}).get('terminal')) or (isinstance(previous, str) and is_terminal(previous))

    if revision is not None:
        if revision < previous_revision:
            return Plan(None, 'stale')
        if revision == previous_revision:
            return Plan(None, 'duplicate' if previous == stage else 'stale')
    elif previous == stage and not reopen:
        return Plan(None, 'duplicate')

    if previous_terminal:
        if not reopen or revision is None or revision <= previous_revision:
            return Plan(None, 'terminal')
        if isinstance(previous, str) and previous.startswith(FAILED_PREFIX):
            if is_terminal(stage):
                return Plan(None, 'terminal')
        elif stage not in REOPEN_STAGES:
            return Plan(None, 'terminal')
    elif isinstance(previous, str) and not is_terminal(stage):
        if STAGE_RANK.get(stage, -1) < STAGE_RANK.get(previous, -1):
            return Plan(None, 'illegal')

    next_revision = revision if revision is not None else previous_revision + 1
    if stage == NOTED and home_ready_at is None:
        home_ready_at = current
    if stage == DONE and episode_done_at is None:
        episode_done_at = current
    entry: dict[str, Any] = {'stage': stage, 'at': current, 'revision': next_revision}
    if reason is not None:
        entry['reason'] = bounded_reason(reason)
    if end_type is not None:
        entry['end_type'] = _bounded_end_type(end_type)
    if end_at is not None:
        entry['end_at'] = _epoch(end_at)

    transitions = list((existing or {}).get('transitions') or [])
    transitions.append(entry)
    transitions = transitions[-MAX_TRANSITIONS:]

    terminal = is_terminal(stage)
    rule = STAGE_TABLE.get(stage)
    doc: dict[str, Any] = {
        'schema_version': SCHEMA_VERSION,
        'owner_key': _pick(None, existing, 'owner_key'),
        'stage': stage,
        'entered_at': current,
        'deadline_at': None if terminal or rule is None else current + rule.deadline_seconds,
        'attempt': int((existing or {}).get('attempt') or 0) + 1,
        'reason': bounded_reason(reason) if reason is not None else (existing or {}).get('reason'),
        'end_type': _bounded_end_type(_pick(end_type, existing, 'end_type')),
        'end_at': _epoch(_pick(end_at, existing, 'end_at')),
        'last_speech_at': _epoch(_pick(last_speech_at, existing, 'last_speech_at')),
        'quiet_due_at': _epoch(_pick(quiet_due_at, existing, 'quiet_due_at')),
        'admitted_at': (existing or {}).get('admitted_at') or current,
        'created_at': (existing or {}).get('created_at') or current,
        'updated_at': current,
        'revision': next_revision,
        'terminal': terminal,
        'terminal_reason': stage if terminal else (existing or {}).get('terminal_reason'),
        'speech_seconds': _bounded_speech_seconds(_pick(speech_seconds, existing, 'speech_seconds')),
        'has_speech': _pick(has_speech, existing, 'has_speech'),
        'speech_basis': _bounded_speech_basis(_pick(speech_basis, existing, 'speech_basis', 'unknown')),
        'home_ready_at': _epoch(_pick(home_ready_at, existing, 'home_ready_at')),
        'episode_done_at': _epoch(_pick(episode_done_at, existing, 'episode_done_at')),
        'transitions': transitions,
        # Firestore TTL policies require a timestamp field, not a numeric epoch.
        'expires_at': datetime.fromtimestamp(current + terminal_ttl_seconds(), tz=timezone.utc) if terminal else None,
    }
    return Plan(doc, 'written')


def _observe_write(outcome: str) -> None:
    try:
        _WRITE.labels(outcome=reason_label(ReasonFamily.PIPELINE_LEDGER, outcome, PipelineLedgerOutcome)).inc()
    except Exception:  # Metrics must never break a transition.
        pass


def _observe_failure(error: BaseException) -> None:
    name = type(error).__name__.lower()
    reason = (
        'timeout'
        if 'deadline' in name or 'timeout' in name
        else (
            'unavailable'
            if 'unavailable' in name or 'connection' in name
            else (
                'permission'
                if 'permission' in name or 'unauthenticated' in name
                else 'invalid' if 'invalid' in name or 'precondition' in name else 'other'
            )
        )
    )
    try:
        _WRITE_FAILURES.labels(
            reason=reason_label(ReasonFamily.PIPELINE_LEDGER, reason, PipelineLedgerFailureReason)
        ).inc()
    except Exception:
        pass


def observe_admission() -> None:
    """Independent coverage denominator; never coupled to a ledger write."""
    try:
        _ADMIT.inc()
    except Exception:
        pass


def ledger_ref(client: Any, uid: str, capture_id: str) -> Any:
    return client.collection('users').document(uid).collection(COLLECTION).document(capture_id)


def _commit(client: Any, ref: Any, uid: str, stage: str, **kwargs: Any) -> str:
    observed: dict[str, Any] = {}

    @firestore.transactional
    def commit(transaction: Any) -> str:
        snapshot = ref.get(transaction=transaction)
        existing = snapshot.to_dict() if getattr(snapshot, 'exists', False) else None
        plan = plan_advance(existing, stage, **kwargs)
        if plan.doc is None:
            observed['outcome'] = plan.outcome
            return plan.outcome
        plan.doc['owner_key'] = owner_key(uid)
        transaction.set(ref, plan.doc)
        observed.update(
            outcome='written',
            previous=(existing or {}).get('stage'),
            entered_at=(existing or {}).get('entered_at'),
            terminal=plan.doc['terminal'],
            end_type=plan.doc['end_type'],
        )
        return 'written'

    outcome = run_transactional(client, commit, transient=True)
    if observed.get('outcome') == 'written':
        previous = observed.get('previous')
        try:
            _TRANSITION.labels(**{'from': stage_label(previous or 'none'), 'to': stage_label(stage)}).inc()
            if previous:
                _ROWS.labels(stage=stage_label(previous)).dec()
            _ROWS.labels(stage=stage_label(stage)).inc()
            entered_at = observed.get('entered_at')
            if isinstance(entered_at, (int, float)):
                _STAGE_SECONDS.labels(stage=stage_label(previous or '')).observe(time.time() - entered_at)
            if observed.get('terminal') and observed.get('end_type') == 'unknown':
                _UNKNOWN_END.inc()
        except Exception:  # Metrics must never break a transition.
            pass
    return outcome


def advance(uid: str, capture_id: str, stage: str, *, firestore_client: Any = None, **fields: Any) -> bool:
    """Best-effort ledger write in its own CAS transaction.

    ``fields`` are the :func:`plan_advance` keyword arguments (``now``,
    ``reason``, ``end_type``, ``end_at``, ``last_speech_at``, ``quiet_due_at``,
    ``revision``, ``reopen``, ``speech_seconds``, ``has_speech``,
    ``speech_basis``, ``home_ready_at``, ``episode_done_at``). Returns ``True``
    only when a new document was committed. Every error is swallowed: the real
    transition already committed and stays authoritative.
    """
    if not pipeline_ledger_enabled():
        _observe_write('disabled')
        return False
    try:
        client = firestore_client if firestore_client is not None else get_firestore_client()
        outcome = _commit(client, ledger_ref(client, uid, capture_id), uid, stage, **fields)
        _observe_write('ok' if outcome == 'written' else outcome)
        return outcome == 'written'
    except Exception as error:  # Fail open: the real transition is authoritative.
        _observe_write('error')
        _observe_failure(error)
        logger.warning(
            'event=pipeline_ledger outcome=error stage=%s exception_type=%s',
            stage_label(stage),
            type(error).__name__,
        )
        return False


CENSUS_FIELDS = (
    'schema_version',
    'owner_key',
    'stage',
    'entered_at',
    'deadline_at',
    'attempt',
    'reason',
    'end_type',
    'end_at',
    'admitted_at',
    'created_at',
    'updated_at',
    'revision',
    'terminal',
    'terminal_reason',
    'speech_seconds',
    'has_speech',
    'speech_basis',
    'home_ready_at',
    'episode_done_at',
    'expires_at',
)


def iter_window(
    start: Any, end: Any, *, uid: str, limit: int = DEFAULT_WINDOW_LIMIT, firestore_client: Any = None
) -> Iterator[dict[str, Any]]:
    """Yield one owner's ledger rows with ``admitted_at`` in ``[start, end)``.

    Read-only, owner-scoped and bounded. The query is scoped to
    ``users/{uid}/pipeline_ledger`` so a caller can never read another owner's
    rows. Rows are projected to :data:`CENSUS_FIELDS`; raw capture/conversation
    ids and the transition history never leave the store. The whole window is
    materialized before the first yield, so a truncated window raises
    :class:`LedgerWindowTruncated` without handing the caller a prefix. C2 must
    read through this helper, never the private store.

    The fleet-global aggregate is the one documented exception and reads through
    :func:`iter_global_window`; it is not a per-owner read.
    """
    start_epoch, end_epoch = _epoch(start), _epoch(end)
    if start_epoch is None or end_epoch is None or end_epoch <= start_epoch or limit <= 0:
        raise ValueError('invalid ledger window')
    client = firestore_client if firestore_client is not None else get_firestore_client()
    query = (
        client.collection('users')
        .document(uid)
        .collection(COLLECTION)
        .where(filter=firestore.FieldFilter('admitted_at', '>=', start_epoch))
        .where(filter=firestore.FieldFilter('admitted_at', '<', end_epoch))
        .limit(limit + 1)
    )
    snapshots = list(query.stream())
    if len(snapshots) > limit:
        raise LedgerWindowTruncated(f'ledger window exceeded {limit} rows')
    for snapshot in snapshots:
        doc = snapshot.to_dict() or {}
        yield {key: doc.get(key) for key in CENSUS_FIELDS}


def iter_global_window(
    start: Any, end: Any, *, limit: int = DEFAULT_WINDOW_LIMIT, firestore_client: Any = None
) -> Iterator[tuple[str | None, dict[str, Any]]]:
    """Yield ``(owner_uid, row)`` across owners with ``admitted_at`` in ``[start, end)``.

    The documented fleet-global exception to :func:`iter_window`'s owner scope:
    the C2 census aggregates every owner. Same projection, bound and
    fail-closed truncation. The uid is returned only to join the conversation
    row; it is never part of a census response.
    """
    start_epoch, end_epoch = _epoch(start), _epoch(end)
    if start_epoch is None or end_epoch is None or end_epoch <= start_epoch or limit <= 0:
        raise ValueError('invalid ledger window')
    client = firestore_client if firestore_client is not None else get_firestore_client()
    query = (
        client.collection_group(COLLECTION)
        .where(filter=firestore.FieldFilter('admitted_at', '>=', start_epoch))
        .where(filter=firestore.FieldFilter('admitted_at', '<', end_epoch))
        .limit(limit + 1)
    )
    snapshots = list(query.stream())
    if len(snapshots) > limit:
        raise LedgerWindowTruncated(f'ledger window exceeded {limit} rows')
    for snapshot in snapshots:
        doc = snapshot.to_dict() or {}
        parts = str(getattr(snapshot.reference, 'path', '')).split('/')
        uid = parts[1] if len(parts) >= 4 and parts[0] == 'users' else None
        row = {key: doc.get(key) for key in CENSUS_FIELDS}
        row['capture_id'] = snapshot.id
        yield uid, row


def retention_start(*, firestore_client: Any = None) -> float | None:
    """The ledger's global earliest ``admitted_at``, or ``None`` when it is empty.

    One bounded read on the retained collection-group index. The window's own
    minimum is always ``>= start``, so only this value can prove full lookback.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    query = client.collection_group(COLLECTION).order_by('admitted_at').limit(1)
    for snapshot in query.stream():
        return _epoch((snapshot.to_dict() or {}).get('admitted_at'))
    return None


def census_window(
    start: Any, end: Any, *, uid: str, limit: int = DEFAULT_WINDOW_LIMIT, firestore_client: Any = None
) -> list[dict[str, Any]]:
    """Materialized :func:`iter_window`; raises on truncation."""
    return list(iter_window(start, end, uid=uid, limit=limit, firestore_client=firestore_client))
