"""Write-only, fail-open in-flight ledger for the capture pipeline.

One document per capture under ``users/{uid}/pipeline_ledger/{capture_id}``.
The ledger is a measurement surface: it never serves a read path, never gates a
transition, and a ledger failure must never fail the real write. Callers build
the next document with :func:`prepare` (one read plus a pure plan) and write it
inside their own transaction, so the ledger commits with the real transition
when the caller can join one.

Storage-neutral by design: the stage table, transition rules and document shape
are plain data, so the same contract can move to Postgres without changing
callers. The owning uid is the collection path, not a document field.

Fail-open boundary: :func:`prepare` catches every ledger error and returns
``None``. The caller's transaction then writes only its real state. The ledger
``set`` itself is a plain write to a new collection in the same project, so it
cannot fail independently of the transaction that carries it.
"""

from __future__ import annotations

import logging
import math
import time
from datetime import datetime, timezone
from typing import Any, Mapping, NamedTuple

from prometheus_client import REGISTRY, Counter, Histogram

from config.refactor_modes import pipeline_ledger_enabled
from database._client import get_firestore_client

logger = logging.getLogger(__name__)

COLLECTION = 'pipeline_ledger'
MAX_TRANSITIONS = 16
TERMINAL_TTL_SECONDS = 7 * 86400

CAPTURING = 'capturing'
SEALED = 'sealed'
TRANSCRIBED = 'transcribed'
NOTED = 'noted'
DONE = 'done'
NO_SPEECH = 'no_speech'
NOISE = 'noise'
FAILED_PREFIX = 'failed:'

END_TYPES = frozenset({'user_initiated', 'jev_initiated', 'silence_backstop', 'unknown'})
FAILURE_REASONS = frozenset(
    {
        'no_speech',
        'noise',
        'upload_failed',
        'privacy',
        'deleted',
        'timeout',
        'provider',
        'empty_output',
        'other',
    }
)


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

_ADVANCE_NAME = 'omi_pipeline_ledger_advance_total'
_STAGE_SECONDS_NAME = 'omi_pipeline_ledger_stage_seconds'
_ADVANCE = getattr(REGISTRY, '_names_to_collectors', {}).get(_ADVANCE_NAME) or Counter(
    _ADVANCE_NAME,
    'In-flight ledger advance attempts by stage and outcome.',
    ['stage', 'outcome'],
)
_STAGE_SECONDS = getattr(REGISTRY, '_names_to_collectors', {}).get(_STAGE_SECONDS_NAME) or Histogram(
    _STAGE_SECONDS_NAME,
    'Time spent in a ledger stage before its next transition.',
    ['stage'],
    buckets=(30, 60, 120, 300, 600, 1800, 3600, 7200, 21600, 86400),
)


class Plan(NamedTuple):
    """The next ledger document, or why no write is needed."""

    doc: dict[str, Any] | None
    outcome: str


def is_terminal(stage: str) -> bool:
    return stage in TERMINAL_STAGES or stage.startswith(FAILED_PREFIX)


def failed_stage(reason: str | None) -> str:
    """Bounded low-cardinality failure terminal; unknown reasons collapse to ``other``."""
    bounded = reason if reason in FAILURE_REASONS else 'other'
    return f'{FAILED_PREFIX}{bounded}'


def stage_label(stage: str) -> str:
    """Metric label: failure reasons never become their own series."""
    return 'failed' if stage.startswith(FAILED_PREFIX) else stage


def _epoch(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        moment = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        return moment.timestamp()
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return float(value)
    return None


def _bounded_end_type(value: Any) -> str:
    return value if value in END_TYPES else 'unknown'


def plan_advance(
    existing: Mapping[str, Any] | None,
    stage: str,
    *,
    now: float | None = None,
    reason: str | None = None,
    end_type: str | None = None,
    end_at: Any = None,
) -> Plan:
    """Pure transition plan. Never raises for a legal stage name.

    ``duplicate`` means the capture is already at this stage (safe to call
    repeatedly). ``illegal`` means a backward or unknown transition. ``terminal``
    means the capture already reached a terminal and cannot move again.
    """
    current = time.time() if now is None else now
    if stage not in STAGE_TABLE and not is_terminal(stage):
        return Plan(None, 'illegal')
    previous = (existing or {}).get('stage')
    if previous == stage:
        return Plan(None, 'duplicate')
    if isinstance(previous, str) and is_terminal(previous):
        return Plan(None, 'terminal')
    if isinstance(previous, str) and not is_terminal(stage):
        if STAGE_RANK.get(stage, -1) <= STAGE_RANK.get(previous, -1):
            return Plan(None, 'illegal')

    entry: dict[str, Any] = {'stage': stage, 'at': current}
    if reason is not None:
        entry['reason'] = reason
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
        'capture_id': (existing or {}).get('capture_id'),
        'stage': stage,
        'entered_at': current,
        'deadline_at': None if terminal or rule is None else current + rule.deadline_seconds,
        'attempt': int((existing or {}).get('attempt') or 0) + 1,
        'reason': reason if reason is not None else (existing or {}).get('reason'),
        'end_type': _bounded_end_type(end_type if end_type is not None else (existing or {}).get('end_type')),
        'end_at': _epoch(end_at) if end_at is not None else _epoch((existing or {}).get('end_at')),
        'transitions': transitions,
        'expires_at': current + TERMINAL_TTL_SECONDS if terminal else None,
        'updated_at': current,
    }
    return Plan(doc, 'written')


def _observe(stage: str, outcome: str) -> None:
    try:
        _ADVANCE.labels(stage=stage_label(stage), outcome=outcome).inc()
    except Exception:  # Metrics must never break a transition.
        pass


def _observe_stage_seconds(stage: str, elapsed: float) -> None:
    if elapsed < 0:
        return
    try:
        _STAGE_SECONDS.labels(stage=stage_label(stage)).observe(elapsed)
    except Exception:  # Metrics must never break a transition.
        pass


def ledger_ref(client: Any, uid: str, capture_id: str) -> Any:
    return client.collection('users').document(uid).collection(COLLECTION).document(capture_id)


def prepare(
    uid: str,
    capture_id: str,
    stage: str,
    *,
    now: float | None = None,
    reason: str | None = None,
    end_type: str | None = None,
    end_at: Any = None,
    firestore_client: Any = None,
) -> tuple[Any, dict[str, Any]] | None:
    """Read the current ledger doc and return ``(ref, next_doc)`` for the caller's transaction.

    Returns ``None`` when the switch is off, the transition is a duplicate or
    illegal, or any ledger read/plan fails. The caller writes the returned doc
    inside its own transaction; the read stays outside it so the real
    transaction remains write-only.
    """
    if not pipeline_ledger_enabled():
        _observe(stage, 'disabled')
        return None
    try:
        client = firestore_client if firestore_client is not None else get_firestore_client()
        ref = ledger_ref(client, uid, capture_id)
        snapshot = ref.get()
        existing = snapshot.to_dict() if getattr(snapshot, 'exists', False) else None
        plan = plan_advance(existing, stage, now=now, reason=reason, end_type=end_type, end_at=end_at)
        if plan.doc is None:
            _observe(stage, plan.outcome)
            return None
        plan.doc['capture_id'] = capture_id
        if existing and isinstance(existing.get('entered_at'), (int, float)):
            _observe_stage_seconds(str(existing.get('stage') or ''), plan.doc['entered_at'] - existing['entered_at'])
        _observe(stage, 'prepared')
        return ref, plan.doc
    except Exception as error:  # Fail open: the real transition is authoritative.
        _observe(stage, 'error')
        logger.warning(
            'event=pipeline_ledger outcome=error stage=%s exception_type=%s',
            stage_label(stage),
            type(error).__name__,
        )
        return None


def advance(
    uid: str,
    capture_id: str,
    stage: str,
    *,
    now: float | None = None,
    reason: str | None = None,
    end_type: str | None = None,
    end_at: Any = None,
    firestore_client: Any = None,
) -> bool:
    """Best-effort standalone write for callers that cannot join a transaction."""
    prepared = prepare(
        uid,
        capture_id,
        stage,
        now=now,
        reason=reason,
        end_type=end_type,
        end_at=end_at,
        firestore_client=firestore_client,
    )
    if prepared is None:
        return False
    ref, doc = prepared
    try:
        ref.set(doc)
        _observe(stage, 'written')
        return True
    except Exception as error:
        _observe(stage, 'error')
        logger.warning(
            'event=pipeline_ledger outcome=error stage=%s exception_type=%s',
            stage_label(stage),
            type(error).__name__,
        )
        return False
