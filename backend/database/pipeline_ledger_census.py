"""Aggregate-only census over the C1 in-flight ledger for one owner.

Reads the C1 :func:`pipeline_ledger.census_window` helper, joins each row to its
conversation row for the Home-visible predicate, and reduces every row to
counts, shares, ages and quantiles. No uid, conversation id, title, transcript
or audio path leaves this module. The Home classifier is the product
:func:`home_step.classify`; this module does not fork it.

The ledger is owner-scoped by contract, so the census is owner-scoped too. The
operator route supplies the owner; the gate runner is run for the canary test
account. A fleet-wide aggregate is a separate read the C1 PR deferred.
"""

from __future__ import annotations

import time
from collections import Counter
from typing import Any, Mapping

from prometheus_client import REGISTRY, Gauge

from database import pipeline_ledger
from utils.conversations import home_step
from utils.conversations.fragment_visibility import (
    is_rule_discard_decision,
    is_settling_fragment,
    is_user_curated,
)

SCHEMA_VERSION = 1
MIN_END_TYPE_SAMPLE = 20
STUCK_STAGES = ('capturing', 'sealed', 'transcribed', 'noted')
END_TYPES = ('user_initiated', 'jev_initiated', 'silence_backstop', 'unknown')
NEW_STUCK_WINDOW_SECONDS = 3600


class CensusSchemaMismatch(RuntimeError):
    """A ledger row is not the schema this census understands; fail closed."""


def _gauge(name: str, doc: str, labels: tuple[str, ...] = ()) -> Any:
    return getattr(REGISTRY, '_names_to_collectors', {}).get(name) or Gauge(name, doc, list(labels))


_STUCK_ROWS = _gauge('omi_pipeline_ledger_stuck_rows', 'Stuck ledger rows by stage.', ('stage',))
_STUCK_USERS = _gauge('omi_pipeline_ledger_stuck_users', 'Distinct owners with stuck rows by stage.', ('stage',))
_OLDEST_STUCK = _gauge('omi_pipeline_ledger_oldest_stuck_age_seconds', 'Oldest stuck row age by stage.', ('stage',))
_NEW_STUCK = _gauge('omi_pipeline_ledger_new_stuck_per_hour', 'Rows that became stuck in the last hour.', ('stage',))
_UNKNOWN_END_SHARE = _gauge('omi_pipeline_ledger_unknown_end_type_share', 'Share of rows with an unknown end type.')
_REFRESHED_AT = _gauge('omi_pipeline_ledger_refreshed_at_seconds', 'Unix time of the last census refresh.')


def refresh_gauges(result: Mapping[str, Any]) -> None:
    """Publish the census as bounded-label gauges; never a healthy zero for unknown data."""
    stuck = result.get('stuck') or {}
    new_stuck = (result.get('new_stuck_per_hour') or {}).get('by_stage') or {}
    for stage in STUCK_STAGES:
        _STUCK_ROWS.labels(stage=stage).set(float((stuck.get('by_stage') or {}).get(stage, 0)))
        _STUCK_USERS.labels(stage=stage).set(float((stuck.get('affected_users') or {}).get(stage, 0)))
        _OLDEST_STUCK.labels(stage=stage).set(float((stuck.get('oldest_age_seconds') or {}).get(stage, 0)))
        _NEW_STUCK.labels(stage=stage).set(float(new_stuck.get(stage, 0)))
    _UNKNOWN_END_SHARE.set(float((result.get('end_types') or {}).get('unknown_share', 0.0)))
    _REFRESHED_AT.set(float(result.get('generated_at') or time.time()))


def _epoch(value: Any) -> float | None:
    return pipeline_ledger._epoch(value)


def _conversation(client: Any, uid: str, conversation_id: str) -> dict[str, Any] | None:
    snapshot = client.collection('users').document(uid).collection('conversations').document(conversation_id).get()
    return snapshot.to_dict() if getattr(snapshot, 'exists', False) else None


def _home_visible(row: Mapping[str, Any] | None, now: float) -> tuple[bool, str | None]:
    """The product Home predicate, or ``(False, None)`` when the row is missing."""
    if not row:
        return False, None
    step = home_step.classify(row)
    if step != home_step.READY:
        return False, step
    if row.get('deleted') or row.get('discarded') or row.get('sync_merged_into'):
        return False, step
    if row.get('dream_duplicate_of') or (
        is_rule_discard_decision(row.get('relevance_decision')) and not is_user_curated(row)
    ):
        return False, step
    decision = row.get('relevance_decision')
    if isinstance(decision, Mapping) and decision.get('verdict') == 'discard' and not is_user_curated(row):
        return False, step
    bridge = row.get('sync_bridge_pending')
    if isinstance(bridge, Mapping) and not is_user_curated(row):
        expires = bridge.get('expires_at')
        if isinstance(expires, (int, float)) and expires > now:
            return False, step
    if is_settling_fragment(row, now=now):
        return False, step
    return True, step


def _km_quantiles(observations: list[tuple[float | None, float | None, bool]], quantiles=(0.5, 0.9)) -> dict:
    """Kaplan-Meier quantiles; ``(event seconds, censor seconds, is_event)``."""
    if not observations:
        return {q: None for q in quantiles}
    points: dict[float, list[int]] = {}
    for event_at, censored_at, is_event in observations:
        moment = event_at if is_event else censored_at
        if moment is None:
            continue
        bucket = points.setdefault(moment, [0, 0])
        bucket[0 if is_event else 1] += 1
    at_risk = sum(events + censored for events, censored in points.values())
    survival = 1.0
    result: dict[float, float | None] = {q: None for q in quantiles}
    pending = set(quantiles)
    for moment in sorted(points):
        events, censored = points[moment]
        if events:
            survival *= max(0.0, 1.0 - events / at_risk)
            for q in list(pending):
                if survival <= 1.0 - q:
                    result[q] = moment
                    pending.remove(q)
        at_risk -= events + censored
        if not pending or at_risk <= 0:
            break
    return result


def _stage_label(stage: Any) -> str:
    return pipeline_ledger.stage_label(stage if isinstance(stage, str) else 'other')


def _speech(row: Mapping[str, Any]) -> tuple[bool, bool]:
    """``(real_speech, speech_unknown)`` for one ledger row."""
    seconds = row.get('speech_seconds')
    real = (isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and seconds > 0) or row.get(
        'has_speech'
    ) is True
    return real, row.get('speech_basis') == 'unknown'


def census(
    uid: str,
    start: Any,
    end: Any,
    *,
    now: float | None = None,
    firestore_client: Any = None,
    limit: int = pipeline_ledger.DEFAULT_WINDOW_LIMIT,
) -> dict[str, Any]:
    """Exact owner-scoped aggregates for the ledger window ``[start, end)``."""
    current = time.time() if now is None else now
    client = firestore_client if firestore_client is not None else pipeline_ledger.get_firestore_client()
    rows = pipeline_ledger.census_window(start, end, uid=uid, limit=limit, firestore_client=client, include_key=True)
    by_stage: Counter[str] = Counter()
    stuck_by_stage: Counter[str] = Counter()
    stuck_users: dict[str, set[str]] = {stage: set() for stage in STUCK_STAGES}
    oldest_stuck: dict[str, float] = {stage: 0.0 for stage in STUCK_STAGES}
    new_stuck: Counter[str] = Counter()
    end_type_rows: Counter[str] = Counter()
    end_type_real: Counter[str] = Counter()
    end_type_visible: Counter[str] = Counter()
    real_speech = speech_unknown = visible_real = home_unknown = clock_unknown = 0
    observations: list[tuple[float | None, float | None, bool]] = []
    latest_updated: float | None = None
    for row in rows:
        if row.get('schema_version') != SCHEMA_VERSION:
            raise CensusSchemaMismatch('ledger schema_version mismatch')
        stage = row.get('stage')
        by_stage[_stage_label(stage)] += 1
        updated = _epoch(row.get('updated_at'))
        if updated is not None and (latest_updated is None or updated > latest_updated):
            latest_updated = updated
        deadline = _epoch(row.get('deadline_at'))
        if not row.get('terminal') and deadline is not None and current > deadline:
            label = _stage_label(stage)
            if label in STUCK_STAGES:
                stuck_by_stage[label] += 1
                owner = row.get('owner_key')
                if isinstance(owner, str):
                    stuck_users[label].add(owner)
                oldest_stuck[label] = max(oldest_stuck[label], current - deadline)
                if current - NEW_STUCK_WINDOW_SECONDS <= deadline < current:
                    new_stuck[label] += 1
        real, unknown = _speech(row)
        real_speech += int(real)
        speech_unknown += int(unknown)
        conversation = _conversation(client, uid, row['capture_id']) if row.get('capture_id') else None
        visible, step = _home_visible(conversation, current)
        home_unknown += int(conversation is None or step is None)
        visible_real += int(real and visible)
        end_type = row.get('end_type') if row.get('end_type') in END_TYPES else 'unknown'
        end_type_rows[end_type] += 1
        end_type_real[end_type] += int(real)
        end_type_visible[end_type] += int(real and visible)
        clock_start = _epoch(row.get('end_at')) or _epoch(row.get('admitted_at'))
        event_at = _epoch(row.get('home_ready_at'))
        if clock_start is None:
            clock_unknown += 1
        elif event_at is not None and event_at >= clock_start:
            observations.append((event_at - clock_start, None, True))
        else:
            observations.append((None, current - clock_start, False))
    denominator = real_speech + speech_unknown
    km = _km_quantiles(observations)
    total_rows = len(rows)
    end_types: dict[str, Any] = {}
    for end_type in END_TYPES:
        count, real, visible = (
            end_type_rows.get(end_type, 0),
            end_type_real.get(end_type, 0),
            end_type_visible.get(end_type, 0),
        )
        end_types[end_type] = {
            'rows': count,
            'real_speech': real,
            'home_visible': visible,
            'share': visible / real if real else None,
            'sample_status': 'sufficient' if count >= MIN_END_TYPE_SAMPLE else 'insufficient_sample',
        }
    end_types['unknown_share'] = end_type_rows.get('unknown', 0) / total_rows if total_rows else 0.0
    return {
        'schema_version': SCHEMA_VERSION,
        'generated_at': current,
        'rows': total_rows,
        'by_stage': dict(by_stage),
        'stuck': {
            'by_stage': {stage: stuck_by_stage.get(stage, 0) for stage in STUCK_STAGES},
            'affected_users': {stage: len(stuck_users[stage]) for stage in STUCK_STAGES},
            'oldest_age_seconds': {stage: round(oldest_stuck[stage], 3) for stage in STUCK_STAGES},
            'total': sum(stuck_by_stage.values()),
        },
        'new_stuck_per_hour': {
            'by_stage': {stage: new_stuck.get(stage, 0) for stage in STUCK_STAGES},
            'total': sum(new_stuck.values()),
        },
        'home_visible': {
            'denominator': denominator,
            'real_speech': real_speech,
            'visible': visible_real,
            'share': visible_real / real_speech if real_speech else None,
            'share_lower_bound': visible_real / denominator if denominator else None,
            'share_upper_bound': (visible_real + speech_unknown) / denominator if denominator else None,
            'speech_unknown': speech_unknown,
            'speech_unknown_share': speech_unknown / denominator if denominator else 0.0,
            'home_unknown': home_unknown,
            'basis': 'ledger_join_home_step',
        },
        'latency': {
            'clock_start': 'end_at',
            'event': 'noted',
            'p50_seconds': km.get(0.5),
            'p90_seconds': km.get(0.9),
            'p50_status': 'measured' if km.get(0.5) is not None else 'not_reached',
            'p90_status': 'measured' if km.get(0.9) is not None else 'not_reached',
            'event_count': sum(1 for _, _, is_event in observations if is_event),
            'censored_count': sum(1 for _, _, is_event in observations if not is_event),
            'clock_unknown_count': clock_unknown,
            'basis': 'kaplan_meier',
        },
        'end_types': end_types,
        'ledger_updated_at': latest_updated,
        'redaction': {
            'uids': False,
            'conversation_ids': False,
            'content': False,
            'titles': False,
            'transcripts': False,
        },
    }


def explain(uid: str, conversation_id: str, *, firestore_client: Any = None) -> dict[str, Any] | None:
    """One conversation's ledger transition list, owner-scoped and content-free."""
    client = firestore_client if firestore_client is not None else pipeline_ledger.get_firestore_client()
    snapshot = pipeline_ledger.ledger_ref(client, uid, conversation_id).get()
    if not getattr(snapshot, 'exists', False):
        return None
    doc = snapshot.to_dict() or {}
    transitions = [
        {'stage': entry.get('stage'), 'at': _epoch(entry.get('at')), 'reason': entry.get('reason')}
        for entry in (doc.get('transitions') or [])[: pipeline_ledger.MAX_TRANSITIONS]
        if isinstance(entry, Mapping)
    ]
    return {
        'schema_version': pipeline_ledger.SCHEMA_VERSION,
        'conversation_id': conversation_id,
        'stage': doc.get('stage'),
        'entered_at': _epoch(doc.get('entered_at')),
        'deadline_at': _epoch(doc.get('deadline_at')),
        'attempt': doc.get('attempt'),
        'reason': doc.get('reason'),
        'end_type': doc.get('end_type'),
        'end_at': _epoch(doc.get('end_at')),
        'transitions': transitions,
        'redaction': {'uids': False, 'content': False, 'titles': False, 'transcripts': False},
    }
