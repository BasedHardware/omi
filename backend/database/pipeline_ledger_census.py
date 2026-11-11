"""Aggregate-only census over the C1 in-flight ledger.

Reads the ledger's ``admitted_at`` collection-group window (the index the C1 PR
retained for the global aggregate), joins each row to its conversation row for
the Home-visible predicate, and reduces every row to counts, shares, ages and
quantiles. No uid, conversation id, title, transcript or audio path leaves this
module. The Home classifier is the product :func:`home_step.classify`; this
module does not fork it.

The per-owner ``explain`` read uses the C1 ``ledger_ref`` and is owner-scoped.
"""

from __future__ import annotations

import datetime as dt
import time
from collections import Counter
from typing import Any, Iterator, Mapping

from google.cloud import firestore

from database import conversations as conversations_db
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
# A conversation created this close to the window end may not have been admitted
# yet. The coverage cohort stops here so the numerator and the denominator
# describe the same settled set of conversations instead of two different
# ``admitted_at``/``created_at`` cohorts.
COVERAGE_SETTLE_SECONDS = 300
# The conversation fields the Home predicate reads. Content (title/overview) is
# needed by the product classifier; the transcript is reduced to a boolean
# immediately and never leaves this module.
CONVERSATION_FIELDS = (
    'status',
    'created_at',
    'started_at',
    'finished_at',
    'structured.title',
    'structured.overview',
    'structured.title_provenance',
    'user_title',
    'sync_relevance_user_kept',
    'has_photos',
    'photos',
    'starred',
    'folder_user_set',
    'summary_due_at',
    'summary_completed_at',
    'summary_output_present',
    'summary_blocked_reason',
    'summary_retryable',
    'finalization_status',
    'record_upload_failed',
    'record_audio_partial',
    'record_lane_owner',
    'record_projection_revision',
    'home_transcription_deadline_at',
    'relevance_decision',
    'discarded',
    'deleted',
    'sync_merged_into',
    'dream_duplicate_of',
    'sync_bridge_pending',
    'no_speech_terminal',
    'transcript_segments',
)


class CensusSchemaMismatch(RuntimeError):
    """A ledger row is not the schema this census understands; fail closed."""


def _global_window(start: Any, end: Any, *, limit: int, firestore_client: Any) -> Iterator[dict[str, Any]]:
    """Yield ledger rows across owners with ``admitted_at`` in ``[start, end)``.

    Reads through the C1 :func:`pipeline_ledger.iter_global_window` helper, the
    documented fleet-global exception to the owner-scoped read. The owner id is
    attached only to join the conversation row; it is never returned.
    """
    for uid, row in pipeline_ledger.iter_global_window(start, end, limit=limit, firestore_client=firestore_client):
        row['_uid'] = uid
        yield row


def _conversation(client: Any, uid: str | None, conversation_id: str) -> dict[str, Any] | None:
    if not uid:
        return None
    row = conversations_db.get_conversation_raw_snapshot(
        uid,
        conversation_id,
        firestore_client=client,
        field_paths=list(CONVERSATION_FIELDS),
    )
    if row is None:
        return None
    # The classifier only needs transcript truthiness; reduce it now so the
    # array never travels further than this statement.
    row['transcript_segments'] = bool(row.get('transcript_segments'))
    return row


def _capture_creates(client: Any, start_epoch: float | None, end_epoch: float | None) -> int | None:
    """Exact count of conversations created in the window (the coverage denominator)."""
    start = pipeline_ledger.epoch(start_epoch)
    end = pipeline_ledger.epoch(end_epoch)
    if start is None or end is None:
        return None
    try:
        start_at = dt.datetime.fromtimestamp(start, tz=dt.timezone.utc)
        end_at = dt.datetime.fromtimestamp(end, tz=dt.timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    query = (
        client.collection_group('conversations')
        .where(filter=firestore.FieldFilter('created_at', '>=', start_at))
        .where(filter=firestore.FieldFilter('created_at', '<', end_at))
        # Ordering by the retained (created_at, id) collection-group index keeps
        # the count on an existing index; a count does not care about order.
        .order_by('created_at')
        .order_by('id')
    )
    return int(query.count().get()[0][0].value)


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


def census(
    start: Any,
    end: Any,
    *,
    now: float | None = None,
    firestore_client: Any = None,
    limit: int = pipeline_ledger.DEFAULT_WINDOW_LIMIT,
) -> dict[str, Any]:
    """Exact fleet aggregates for the ledger window ``[start, end)``."""
    current = time.time() if now is None else now
    client = firestore_client if firestore_client is not None else pipeline_ledger.get_firestore_client()
    rows = list(_global_window(start, end, limit=limit, firestore_client=client))
    by_stage: Counter[str] = Counter()
    stuck_by_stage: Counter[str] = Counter()
    stuck_users: dict[str, set[str]] = {stage: set() for stage in STUCK_STAGES}
    oldest_stuck: dict[str, float] = {stage: 0.0 for stage in STUCK_STAGES}
    new_stuck: Counter[str] = Counter()
    end_type_rows: Counter[str] = Counter()
    end_type_real: Counter[str] = Counter()
    end_type_visible: Counter[str] = Counter()
    end_type_observations: dict[str, list[tuple[float | None, float | None, bool]]] = {
        end_type: [] for end_type in END_TYPES
    }
    real_speech = speech_unknown = visible_real = home_unknown = clock_unknown = terminal_rows = 0
    clock_fallback = cohort_admits = excluded_admits = 0
    end_type_clock_fallback: Counter[str] = Counter()
    observations: list[tuple[float | None, float | None, bool]] = []
    latest_updated: float | None = None
    earliest_admitted: float | None = None
    window_start = pipeline_ledger.epoch(start)
    window_end = pipeline_ledger.epoch(end)
    coverage_end = None if window_end is None else window_end - COVERAGE_SETTLE_SECONDS
    for row in rows:
        if row.get('schema_version') != SCHEMA_VERSION:
            raise CensusSchemaMismatch('ledger schema_version mismatch')
        stage = row.get('stage')
        by_stage[pipeline_ledger.stage_label(stage if isinstance(stage, str) else 'other')] += 1
        updated = pipeline_ledger.epoch(row.get('updated_at'))
        if updated is not None and (latest_updated is None or updated > latest_updated):
            latest_updated = updated
        admitted = pipeline_ledger.epoch(row.get('admitted_at'))
        if admitted is not None and (earliest_admitted is None or admitted < earliest_admitted):
            earliest_admitted = admitted
        deadline = pipeline_ledger.epoch(row.get('deadline_at'))
        if not row.get('terminal') and deadline is not None and current > deadline:
            label = pipeline_ledger.stage_label(stage if isinstance(stage, str) else 'other')
            if label in STUCK_STAGES:
                stuck_by_stage[label] += 1
                owner = row.get('owner_key')
                if isinstance(owner, str):
                    stuck_users[label].add(owner)
                oldest_stuck[label] = max(oldest_stuck[label], current - deadline)
                if current - NEW_STUCK_WINDOW_SECONDS <= deadline < current:
                    new_stuck[label] += 1
        seconds = row.get('speech_seconds')
        real = (isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and seconds > 0) or row.get(
            'has_speech'
        ) is True
        # Each row lands in exactly one bucket: known real speech, or unknown.
        # ``plan_advance`` defaults ``speech_basis`` to ``unknown`` independently
        # of ``has_speech``, so the two sets are not disjoint in the store.
        unknown = (not real) and row.get('speech_basis') == 'unknown'
        real_speech += int(real)
        speech_unknown += int(unknown)
        conversation = _conversation(client, row.get('_uid'), row['capture_id'])
        visible, step = _home_visible(conversation, current)
        home_unknown += int(conversation is None or step is None)
        visible_real += int(real and visible)
        # Coverage counts the same cohort on both sides: conversations created
        # in the settled window. A row admitted here but created outside it is
        # reported separately instead of inflating the numerator.
        created = pipeline_ledger.epoch((conversation or {}).get('created_at'))
        if (
            created is not None
            and window_start is not None
            and coverage_end is not None
            and window_start <= created < coverage_end
        ):
            cohort_admits += 1
        else:
            excluded_admits += 1
        # The end-to-Home clock starts at ``end_at``. A row without it has no
        # end-to-Home duration; it is counted on its own basis and kept out of
        # the quantiles rather than silently borrowing ``admitted_at``.
        clock_start = pipeline_ledger.epoch(row.get('end_at'))
        event_at = pipeline_ledger.epoch(row.get('home_ready_at'))
        observation: tuple[float | None, float | None, bool]
        if clock_start is None:
            if pipeline_ledger.epoch(row.get('admitted_at')) is not None:
                clock_fallback += 1
            else:
                clock_unknown += 1
            observation = (None, None, False)
        elif event_at is not None and event_at >= clock_start:
            observation = (event_at - clock_start, None, True)
        else:
            observation = (None, current - clock_start, False)
        if clock_start is not None:
            observations.append(observation)
        # Only an ended row has an end type. An in-flight row's default
        # ``end_type='unknown'`` is "not ended yet", not "ended unknown".
        if row.get('terminal'):
            terminal_rows += 1
            end_type = str(row.get('end_type')) if row.get('end_type') in END_TYPES else 'unknown'
            end_type_rows[end_type] += 1
            end_type_real[end_type] += int(real)
            end_type_visible[end_type] += int(real and visible)
            if clock_start is not None:
                end_type_observations[end_type].append(observation)
            else:
                end_type_clock_fallback[end_type] += 1
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
        type_km = _km_quantiles(end_type_observations[end_type])
        end_types[end_type] = {
            'rows': count,
            'real_speech': real,
            'home_visible': visible,
            'share': visible / real if real else None,
            'p50_seconds': type_km.get(0.5),
            'p90_seconds': type_km.get(0.9),
            'p50_status': 'measured' if type_km.get(0.5) is not None else 'not_reached',
            'p90_status': 'measured' if type_km.get(0.9) is not None else 'not_reached',
            'clock_fallback': end_type_clock_fallback.get(end_type, 0),
            'sample_status': 'sufficient' if count >= MIN_END_TYPE_SAMPLE else 'insufficient_sample',
        }
    end_types['terminal_rows'] = terminal_rows
    end_types['unknown_share'] = end_type_rows.get('unknown', 0) / terminal_rows if terminal_rows else 0.0
    capture_creates = _capture_creates(client, start, coverage_end)
    coverage_ratio = cohort_admits / capture_creates if capture_creates else None
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
        'coverage': {
            'ledger_admits': total_rows,
            'cohort_admits': cohort_admits,
            'excluded_admits': excluded_admits,
            'capture_creates': capture_creates,
            'unmatched_creates': (capture_creates - cohort_admits) if capture_creates is not None else None,
            'ratio': coverage_ratio,
            'settle_seconds': COVERAGE_SETTLE_SECONDS,
            'basis': 'conversations_created_in_window',
            'ledger_write_failures': None,
            'ledger_disabled': None,
            'status': 'pass' if coverage_ratio is not None and coverage_ratio >= 0.995 else 'unknown',
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
            'clock_basis': 'end_at_only',
            'event': 'noted',
            'p50_seconds': km.get(0.5),
            'p90_seconds': km.get(0.9),
            'p50_status': 'measured' if km.get(0.5) is not None else 'not_reached',
            'p90_status': 'measured' if km.get(0.9) is not None else 'not_reached',
            'event_count': sum(1 for _, _, is_event in observations if is_event),
            'censored_count': sum(1 for _, _, is_event in observations if not is_event),
            'clock_fallback_count': clock_fallback,
            'clock_unknown_count': clock_unknown,
            'basis': 'kaplan_meier',
        },
        'end_types': end_types,
        'ledger_updated_at': latest_updated,
        'earliest_admitted_at': earliest_admitted,
        'retention': {
            'earliest_admitted_at': pipeline_ledger.retention_start(firestore_client=client),
            'basis': 'collection_group_min',
        },
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
        {'stage': entry.get('stage'), 'at': pipeline_ledger.epoch(entry.get('at')), 'reason': entry.get('reason')}
        for entry in (doc.get('transitions') or [])[: pipeline_ledger.MAX_TRANSITIONS]
        if isinstance(entry, Mapping)
    ]
    return {
        'schema_version': pipeline_ledger.SCHEMA_VERSION,
        'conversation_id': conversation_id,
        'stage': doc.get('stage'),
        'entered_at': pipeline_ledger.epoch(doc.get('entered_at')),
        'deadline_at': pipeline_ledger.epoch(doc.get('deadline_at')),
        'attempt': doc.get('attempt'),
        'reason': doc.get('reason'),
        'end_type': doc.get('end_type'),
        'end_at': pipeline_ledger.epoch(doc.get('end_at')),
        'transitions': transitions,
        'redaction': {'uids': False, 'content': False, 'titles': False, 'transcripts': False},
    }
