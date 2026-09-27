"""Capture-wedge detector for the self-heal job.

Reads ``vad_gate_metrics`` structured log entries through the read-only Cloud
Logging ``entries.list`` API — never a local or production database query —
and finds uids whose pendant streams wedge silent. Detection runs two bounded
reads over the trailing 10 minutes: one filtered to true zero-byte sessions,
then one filtered to positive-byte sessions for the candidate uids only. Every
failure mode is closed: a truncation, an oversized candidate set, or a read
error suppresses all pushes and cohort claims for the tick; nothing here
writes user data.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

import google.auth
from google.auth.transport.requests import AuthorizedSession

from database import capture_wedge_state
from utils.notification_dispatch import (
    NotificationDispatchStatus,
    NotificationIntent,
    NotificationKind,
    dispatch_notification,
)

logger = logging.getLogger(__name__)

LOGGING_ENTRIES_LIST_URL = 'https://logging.googleapis.com/v2/entries:list'
LOGGING_READ_SCOPE = 'https://www.googleapis.com/auth/logging.read'
LOG_PAGE_SIZE = 1000
LOG_MAX_ENTRIES = 10_000
LOG_REQUEST_TIMEOUT_SECONDS = 30
CANDIDATE_WINDOW = timedelta(minutes=10)
ZERO_STREAK_MIN = 6
MAX_CANDIDATES_PER_TICK = 50

WEDGE_NUDGE_TITLE = "Omi isn't receiving audio"
WEDGE_NUDGE_BODY = 'Your pendant connection looks stuck. Open Omi and reconnect the device. ' 'Nothing was deleted.'
WEDGE_NUDGE_DATA = {'push_type': 'capture_recovery', 'action': 'repair_device'}

_ACTION_MODES = frozenset({'detect', 'nudge', 'heal'})
_NUDGE_MODES = frozenset({'nudge', 'heal'})


def _emit(event: str, **fields: Any) -> None:
    sys.stdout.write(json.dumps({'event': event, **fields}, default=str) + '\n')
    sys.stdout.flush()


def _isoformat_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def zero_session_log_filter(window_start: datetime, now: datetime) -> str:
    """The verbatim Cloud Logging filter for true zero-byte sessions."""
    return (
        'resource.type="k8s_container" AND jsonPayload.event="vad_gate_metrics" '
        'AND jsonPayload.bytes_received=0 AND jsonPayload.chunks_total=0 '
        'AND jsonPayload.session_duration_sec=0 '
        f'AND timestamp>="{_isoformat_z(window_start)}" AND timestamp<="{_isoformat_z(now)}"'
    )


def positive_session_log_filter(candidate_uids: list[str], window_start: datetime, now: datetime) -> str:
    """The verbatim Cloud Logging filter for positive-byte sessions of candidate uids."""
    uid_clause = ' OR '.join('jsonPayload.uid=' + json.dumps(uid) for uid in sorted(candidate_uids))
    return (
        'resource.type="k8s_container" AND jsonPayload.event="vad_gate_metrics" '
        f'AND jsonPayload.bytes_received>0 AND ({uid_clause}) '
        f'AND timestamp>="{_isoformat_z(window_start)}" AND timestamp<="{_isoformat_z(now)}"'
    )


def read_vad_gate_metrics_entries(
    *,
    project_id: str,
    filter_string: str,
    session: Any = None,
    max_entries: int = LOG_MAX_ENTRIES,
) -> dict[str, Any]:
    """Page Cloud Logging for one bounded ``vad_gate_metrics`` filter.

    Returns ``{'entries', 'truncated', 'errors'}``. A non-200 response or a
    transport failure increments ``errors``; collecting ``max_entries`` with a
    ``nextPageToken`` still outstanding marks ``truncated``. Both are
    fail-closed signals for the caller — never logged and then ignored.
    """
    if session is None:
        credentials, _ = google.auth.default(scopes=[LOGGING_READ_SCOPE])
        session = AuthorizedSession(credentials)

    entries: list[dict[str, Any]] = []
    token = ''
    truncated = False
    errors = 0
    while True:
        body: dict[str, Any] = {
            'resourceNames': [f'projects/{project_id}'],
            'filter': filter_string,
            'orderBy': 'timestamp desc',
            'pageSize': LOG_PAGE_SIZE,
            'pageToken': token,
        }
        try:
            response = session.post(LOGGING_ENTRIES_LIST_URL, json=body, timeout=LOG_REQUEST_TIMEOUT_SECONDS)
            if response.status_code != 200:
                logger.error('selfheal wedge log read failed status=%s', response.status_code)
                errors += 1
                break
            payload = response.json()
        except Exception as error:
            logger.error('selfheal wedge log read failed type=%s', type(error).__name__)
            errors += 1
            break
        entries.extend(payload.get('entries') or [])
        token = payload.get('nextPageToken') or ''
        if len(entries) >= max_entries:
            truncated = bool(token)
            break
        if not token:
            break
    return {'entries': entries[:max_entries], 'truncated': truncated, 'errors': errors}


def _num(payload: Mapping[str, Any], key: str) -> float | int | None:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _is_true_zero_tuple(payload: Mapping[str, Any]) -> bool:
    return (
        _num(payload, 'bytes_received') == 0
        and _num(payload, 'chunks_total') == 0
        and _num(payload, 'session_duration_sec') == 0.0
    )


def zero_streak_candidates(entries: list[Mapping[str, Any]]) -> dict[str, int]:
    """Map each wedged uid to its zero-tuple streak from a zero-filtered read.

    Only ``jsonPayload`` entries count, only ``transcription_source == 'omi'``
    sessions, and a uid is rejected outright when any of its rows carries
    ``onboarding_session_id`` or a multi-channel marker.
    """
    streaks: dict[str, int] = {}
    rejected_uids: set[str] = set()
    for entry in entries:
        payload = entry.get('jsonPayload')
        if not isinstance(payload, Mapping):
            continue
        uid = payload.get('uid')
        if not isinstance(uid, str) or not uid:
            continue
        if payload.get('onboarding_session_id') or payload.get('multi_channel') or payload.get('is_multi_channel'):
            rejected_uids.add(uid)
            continue
        if payload.get('transcription_source') == 'omi' and _is_true_zero_tuple(payload):
            streaks[uid] = streaks.get(uid, 0) + 1
    return {uid: count for uid, count in streaks.items() if count >= ZERO_STREAK_MIN and uid not in rejected_uids}


def positive_bytes_uids(entries: list[Mapping[str, Any]]) -> set[str]:
    """uids that produced audio in the positive-filtered read — not wedged."""
    uids: set[str] = set()
    for entry in entries:
        payload = entry.get('jsonPayload')
        if not isinstance(payload, Mapping):
            continue
        uid = payload.get('uid')
        received = _num(payload, 'bytes_received')
        if isinstance(uid, str) and received is not None and received > 0:
            uids.add(uid)
    return uids


def _default_push(uid: str, title: str, body: str, data: Mapping[str, Any]) -> int:
    outcome = dispatch_notification(
        NotificationIntent(
            user_id=uid,
            title=title,
            body=body,
            source='selfheal_capture_wedge',
            kind=NotificationKind.CAPTURE_RECOVERY,
            data=dict(data),
        )
    )
    if outcome.status != NotificationDispatchStatus.DISPATCHED:
        return 0
    return 1 if outcome.delivered else 0


def run_capture_wedge_check(
    *,
    mode: str,
    dry_run: bool = False,
    uid_allowlist: frozenset[str] | None = None,
    now: datetime | None = None,
    project_id: str | None = None,
    firestore_client: Any = None,
    entries_reader: Callable[..., dict[str, Any]] | None = None,
    send_push: Callable[..., int] | None = None,
) -> dict[str, int]:
    """One wedge-detection pass; returns bounded counters for the tick event.

    ``detect`` counts and claims the first-seen cohort only. ``nudge``/``heal``
    also send the repair push after transactionally claiming the 24h cooldown.
    A read error, truncation, or an oversized candidate set short-circuits
    before any claim or push — the detector never acts on partial evidence.
    """
    now = now or datetime.now(timezone.utc)
    counts = {'candidates': 0, 'nudged': 0, 'undeliverable': 0, 'errors': 0}
    if mode not in _ACTION_MODES:
        return counts

    project_id = (
        project_id
        or os.getenv('SELFHEAL_LOGGING_PROJECT')
        or os.getenv('GOOGLE_CLOUD_PROJECT')
        or os.getenv('OMI_CUSTOMER_DATA_PROJECT')
    )
    if not project_id:
        logger.error('selfheal wedge check disabled: no logging project configured')
        counts['errors'] = 1
        return counts

    reader = entries_reader or read_vad_gate_metrics_entries
    window_start = now - CANDIDATE_WINDOW

    try:
        zero_result = reader(
            project_id=project_id,
            filter_string=zero_session_log_filter(window_start, now),
        )
    except Exception as error:
        logger.error('selfheal wedge zero read failed type=%s', type(error).__name__)
        counts['errors'] = 1
        return counts
    if zero_result.get('errors') or zero_result.get('truncated'):
        counts['errors'] = int(zero_result.get('errors') or 0) + (1 if zero_result.get('truncated') else 0)
        logger.error(
            'selfheal wedge zero read failed closed errors=%s truncated=%s',
            zero_result.get('errors'),
            zero_result.get('truncated'),
        )
        return counts

    streaks = zero_streak_candidates(list(zero_result.get('entries') or []))
    if len(streaks) > MAX_CANDIDATES_PER_TICK:
        counts['errors'] = 1
        logger.error(
            'selfheal wedge candidate set oversized count=%d cap=%d; failing closed',
            len(streaks),
            MAX_CANDIDATES_PER_TICK,
        )
        return counts

    if streaks:
        try:
            positive_result = reader(
                project_id=project_id,
                filter_string=positive_session_log_filter(list(streaks), window_start, now),
            )
        except Exception as error:
            logger.error('selfheal wedge positive read failed type=%s', type(error).__name__)
            counts['errors'] = 1
            return counts
        if positive_result.get('errors') or positive_result.get('truncated'):
            counts['errors'] = int(positive_result.get('errors') or 0) + (1 if positive_result.get('truncated') else 0)
            logger.error(
                'selfheal wedge positive read failed closed errors=%s truncated=%s',
                positive_result.get('errors'),
                positive_result.get('truncated'),
            )
            return counts
        delivered = positive_bytes_uids(list(positive_result.get('entries') or []))
        streaks = {uid: count for uid, count in streaks.items() if uid not in delivered}

    counts['candidates'] = len(streaks)
    day = now.strftime('%Y-%m-%d')
    push = send_push or _default_push

    for uid in sorted(streaks, key=lambda u: (-streaks[u], u)):
        _emit('selfheal_wedge_candidate', uid=uid, streak_count=streaks[uid])
        if not dry_run:
            try:
                if capture_wedge_state.claim_wedge_first_seen(uid, day, now=now, firestore_client=firestore_client):
                    _emit('selfheal_wedge_first_seen', uid=uid)
            except Exception as error:
                counts['errors'] += 1
                logger.error('selfheal wedge first-seen claim failed type=%s', type(error).__name__)
                continue

        if mode not in _NUDGE_MODES:
            continue
        if uid_allowlist is not None and uid not in uid_allowlist:
            continue
        if dry_run:
            _emit('selfheal_nudge', uid=uid, outcome='dry_run')
            continue
        try:
            claimed = capture_wedge_state.claim_wedge_nudge_cooldown(uid, now=now, firestore_client=firestore_client)
        except Exception as error:
            counts['errors'] += 1
            logger.error('selfheal wedge cooldown claim failed type=%s', type(error).__name__)
            continue
        if not claimed:
            _emit('selfheal_nudge', uid=uid, outcome='cooldown')
            continue
        try:
            sent = int(push(uid, WEDGE_NUDGE_TITLE, WEDGE_NUDGE_BODY, WEDGE_NUDGE_DATA))
        except Exception as error:
            counts['errors'] += 1
            logger.error('selfheal wedge nudge send failed type=%s', type(error).__name__)
            sent = 0
        if sent > 0:
            counts['nudged'] += 1
            _emit('selfheal_nudge', uid=uid, outcome='sent')
        else:
            counts['undeliverable'] += 1
            _emit('selfheal_nudge', uid=uid, outcome='undeliverable')

    return counts
