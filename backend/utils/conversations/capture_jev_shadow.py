"""Bounded, advisory Jev questions after capture finalization (EXP-003).

Only this module sees plaintext. Its records and metrics contain identifiers and
numeric decisions, never the state sent through the existing Jev gateway client.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from config.jev_decisions import JEV_MODEL, capture_jev_shadow_enabled
from database import conversations as conversations_db
from database import redis_db
from utils.conversations.shared_speech import transcript_words
from utils.executors import llm_executor, submit_with_context
from utils.llm.jev_client import ask_jev, truncate_state
from utils.metrics import (
    CAPTURE_JEV_SHADOW_AGREEMENT,
    CAPTURE_JEV_SHADOW_CALLS,
    CAPTURE_JEV_SHADOW_LATENCY,
    CAPTURE_JEV_SHADOW_SCORE,
    CAPTURE_JEV_SHADOW_SKIPS,
)

logger = logging.getLogger(__name__)
SAME_THRESHOLD = 0.675
RESUMMARY_THRESHOLD = 0.725
WORDING_VERSION = {'same_scene': 'capture_same_b1', 'resummary': 'capture_resummary_a1'}
MAX_EXCERPT_CHARS = 3000
DECISION_DEADLINE_SECONDS = 2.5
_slots = threading.BoundedSemaphore(2)
_expired_logged = False
_expiry_lock = threading.Lock()

SAME_QUESTION = {
    'decision': {
        'type': 'noul',
        'instructions': 'Should these two captures be folded into one user-visible event? Prefer fewer rows when the evidence is uncertain, but avoid joining unrelated scenes.',
        'criteria': {
            'true': 'Same meeting, call, in-person exchange, or uninterrupted social setting; partial and complementary captures count.',
            'false': 'Different meeting, background media versus a conversation, or another independent scene.',
        },
    }
}
RESUMMARY_QUESTION = {
    'decision': {
        'type': 'noul',
        'instructions': 'Does the joining capture contain material facts, decisions, requests, or context missing from the existing event summary, making a visible re-summary worthwhile?',
        'criteria': {
            'true': 'A user would notice and value at least one substantive addition or correction to the summary.',
            'false': 'It repeats covered content, adds only filler or minor wording, or has no reliable new material.',
        },
    }
}

# Two counters are admitted atomically so the sum across all processing hosts
# cannot exceed either daily cap. An unavailable Redis means no vendor call.
_ADMIT_LUA = """
if redis.call('EXISTS', KEYS[3]) == 1 then return 2 end
local global = tonumber(redis.call('GET', KEYS[1]) or '0')
local user = tonumber(redis.call('GET', KEYS[2]) or '0')
if global >= tonumber(ARGV[1]) or user >= tonumber(ARGV[2]) then return 0 end
redis.call('INCR', KEYS[1])
redis.call('INCR', KEYS[2])
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
redis.call('EXPIRE', KEYS[2], tonumber(ARGV[3]))
redis.call('SET', KEYS[3], '1', 'EX', 2592000)
return 1
"""


def _skip(decision: str, reason: str) -> None:
    CAPTURE_JEV_SHADOW_SKIPS.labels(decision, reason).inc()


def _gate(decision: str) -> bool:
    global _expired_logged
    enabled, reason = capture_jev_shadow_enabled()
    if not enabled:
        _skip(decision, reason)
        if reason == 'expired':
            with _expiry_lock:
                if not _expired_logged:
                    _expired_logged = True
                    logger.warning('capture Jev shadow expired; all model calls disabled')
    return enabled


def _allowlist() -> set[str]:
    return {uid.strip() for uid in os.getenv('CAPTURE_JEV_SHADOW_UID_ALLOWLIST', '').split(',') if uid.strip()}


def _in_cohort(uid: str) -> bool:
    if uid in _allowlist():
        return True
    try:
        percentage = float(os.getenv('CAPTURE_JEV_SHADOW_PERCENT', '0'))
        if not 0 <= percentage <= 100:
            return False
    except ValueError:
        return False
    bucket = int.from_bytes(hashlib.sha256(uid.encode()).digest()[:8], 'big') / 2**64 * 100
    return bucket < percentage


def _cap(uid: str, decision: str, first_id: str, second_id: str) -> str:
    now = datetime.now(timezone.utc)
    day = now.strftime('%Y%m%d')
    global_cap = max(0, int(os.getenv('CAPTURE_JEV_SHADOW_GLOBAL_DAILY_CAP', '20000')))
    user_cap = max(0, int(os.getenv('CAPTURE_JEV_SHADOW_USER_DAILY_CAP', '100')))
    ttl = 86400 - (now.hour * 3600 + now.minute * 60 + now.second) + 60
    pair = sorted((first_id, second_id)) if decision == 'same_scene' else (first_id, second_id)
    fingerprint = hashlib.sha256(f'{uid}\0{decision}\0{pair[0]}\0{pair[1]}'.encode()).hexdigest()
    result = redis_db.r.eval(
        _ADMIT_LUA,
        3,
        f'jev:capture:{day}:global',
        f'jev:capture:{day}:uid:{uid}',
        f'jev:capture:pair:{fingerprint}',
        global_cap,
        user_cap,
        ttl,
    )
    return 'admitted' if result == 1 else 'duplicate' if result == 2 else 'cap'


def _field(row: Any, key: str) -> Any:
    return row.get(key) if isinstance(row, Mapping) else getattr(row, key, None)


def _summary(row: Any) -> str:
    structured = _field(row, 'structured') or {}
    title = str(_field(structured, 'title') or '')[:160]
    overview = str(_field(structured, 'overview') or '')[: MAX_EXCERPT_CHARS - 160]
    return f'Title: {title}\nSummary: {overview}'


def _excerpt(row: Any) -> str:
    segments = _field(row, 'transcript_segments') or ()
    text = '\n'.join(str(_field(segment, 'text') or '') for segment in segments)
    return truncate_state(text, max_chars=MAX_EXCERPT_CHARS)


def _state(decision: str, first: Any, second: Any, sources: tuple[str, str]) -> str:
    timing = (
        f'A: {_field(first, "started_at")} to {_field(first, "finished_at")}; '
        f'B: {_field(second, "started_at")} to {_field(second, "finished_at")}.'
    )
    if decision == 'same_scene':
        return (
            'Decide event identity from independent captures. Source and timing are supporting evidence; '
            'speaker labels and speech-to-text can be wrong. A long capture can bridge unrelated scenes.\n'
            f'Sources: A={sources[0]}, B={sources[1]}. {timing}\n'
            f'A summary: {_summary(first)}\nA transcript: {_excerpt(first)}\n'
            f'B summary: {_summary(second)}\nB transcript: {_excerpt(second)}'
        )
    return (
        'An existing event has summary A. Capture B has just joined this same event. '
        'Judge whether to visibly revise summary A for B\'s material contribution; '
        'transcript errors and truncation are possible.\n'
        f'{timing}\nA summary: {_summary(first)}\nA transcript: {_excerpt(first)}\nB transcript: {_excerpt(second)}'
    )


def _category(first: Any, second: Any) -> str:
    source_a, source_b = str(_field(first, 'source') or ''), str(_field(second, 'source') or '')
    if source_a != source_b:
        return 'cross_source'
    device_a = _field(first, 'client_device_id') or (_field(first, 'external_data') or {}).get('device_id')
    device_b = _field(second, 'client_device_id') or (_field(second, 'external_data') or {}).get('device_id')
    if not device_a or not device_b:
        return 'same_source_unknown_device'
    return 'same_source_same_device' if device_a == device_b else 'same_source_different_device'


def _record(record: dict[str, Any]) -> None:
    logger.info('jev_capture_shadow %s', json.dumps(record, separators=(',', ':'), sort_keys=True))


def _decision_record(
    uid: str,
    decision: str,
    first_id: str,
    second_id: str,
    first: Any,
    second: Any,
    category: str,
    rule_fold: bool,
    elapsed: float,
    outcome: str,
    score: float | None = None,
    served_model: str | None = None,
) -> None:
    first_group = _field(first, 'capture_group') or {}
    second_group = _field(second, 'capture_group') or {}
    _record(
        {
            'event': 'jev_capture_shadow',
            'id': str(uuid.uuid4()),
            'uid': uid,
            'decision': decision,
            'first_id': first_id,
            'second_id': second_id,
            'category': category,
            'rule_fold': rule_fold if decision == 'same_scene' else None,
            'group_id': first_group.get('id') if first_group.get('id') == second_group.get('id') else None,
            'p': round(score, 6) if score is not None else None,
            'would_decide': (
                score >= (SAME_THRESHOLD if decision == 'same_scene' else RESUMMARY_THRESHOLD)
                if score is not None
                else None
            ),
            'outcome': outcome,
            'wording_version': WORDING_VERSION[decision],
            'model': JEV_MODEL,
            'served_model': served_model,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'first_started_at': str(_field(first, 'started_at') or ''),
            'first_finished_at': str(_field(first, 'finished_at') or ''),
            'second_started_at': str(_field(second, 'started_at') or ''),
            'second_finished_at': str(_field(second, 'finished_at') or ''),
            'latency_seconds': round(elapsed, 4),
        },
    )


def _run(uid: str, decision: str, first_id: str, second_id: str, deadline: float) -> None:
    try:
        if not _gate(decision):
            return
        if not _in_cohort(uid):
            _skip(decision, 'cohort')
            return
        if time.monotonic() >= deadline:
            _skip(decision, 'timeout')
            return
        first, _ = conversations_db.get_conversation_for_capture_check(uid, first_id)
        second, _ = conversations_db.get_conversation_for_capture_check(uid, second_id)
        if not first or not second or _field(first, 'discarded') or _field(second, 'discarded'):
            _skip(decision, 'error')
            return
        category = _category(first, second)
        first_group = _field(first, 'capture_group') or {}
        second_group = _field(second, 'capture_group') or {}
        rule_fold = False
        if decision == 'same_scene':
            rule_fold = bool(first_group.get('id') and first_group.get('id') == second_group.get('id'))
        elif not first_group.get('id') or first_group.get('id') != second_group.get('id'):
            _skip(decision, 'error')
            return
        if decision == 'resummary' and not _field(_field(first, 'structured') or {}, 'overview'):
            _skip(decision, 'too_short')
            return
        if (
            min(
                len(transcript_words(_field(first, 'transcript_segments'))),
                len(transcript_words(_field(second, 'transcript_segments'))),
            )
            < 10
        ):
            _skip(decision, 'too_short')
            return
        state = _state(decision, first, second, (str(_field(first, 'source')), str(_field(second, 'source'))))
        if not _gate(decision):
            return
        admission = _cap(uid, decision, first_id, second_id)
        if admission != 'admitted':
            _skip(decision, admission)
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _skip(decision, 'timeout')
            return
        jev_outcomes: list[str] = []
        answers = ask_jev(
            state,
            SAME_QUESTION if decision == 'same_scene' else RESUMMARY_QUESTION,
            lane='capture_same_scene' if decision == 'same_scene' else 'capture_resummary',
            timeout_seconds=min(remaining, DECISION_DEADLINE_SECONDS),
            max_attempts=1,
            outcome_observer=jev_outcomes.append,
        )
        elapsed = time.monotonic() - (deadline - DECISION_DEADLINE_SECONDS)
        CAPTURE_JEV_SHADOW_LATENCY.labels(decision).observe(elapsed)
        if time.monotonic() > deadline:
            CAPTURE_JEV_SHADOW_CALLS.labels(decision, 'timeout').inc()
            _skip(decision, 'timeout')
            _decision_record(uid, decision, first_id, second_id, first, second, category, rule_fold, elapsed, 'timeout')
            return
        if not _gate(decision):
            return
        if answers is None:
            CAPTURE_JEV_SHADOW_CALLS.labels(decision, 'unavailable').inc()
            _skip(decision, 'timeout' if jev_outcomes == ['timeout'] else 'error')
            _decision_record(
                uid,
                decision,
                first_id,
                second_id,
                first,
                second,
                category,
                rule_fold,
                elapsed,
                jev_outcomes[-1] if jev_outcomes else 'unavailable',
            )
            return
        score = answers.noul('decision')
        would = score >= (SAME_THRESHOLD if decision == 'same_scene' else RESUMMARY_THRESHOLD)
        CAPTURE_JEV_SHADOW_CALLS.labels(decision, 'success').inc()
        CAPTURE_JEV_SHADOW_SCORE.labels(decision).observe(score)
        if decision == 'same_scene':
            agreement = (
                'both_fold' if rule_fold and would else 'rule_only' if rule_fold else 'jev_only' if would else 'neither'
            )
            CAPTURE_JEV_SHADOW_AGREEMENT.labels(category, agreement).inc()
        _decision_record(
            uid,
            decision,
            first_id,
            second_id,
            first,
            second,
            category,
            rule_fold,
            elapsed,
            'success',
            score,
            answers.served_model,
        )
    except Exception:
        _skip(decision, 'error')
        logger.warning('capture Jev shadow failed decision=%s', decision)
    finally:
        _slots.release()


def _submit(uid: str, decision: str, first_id: str, second_id: str) -> None:
    if not _gate(decision):
        return
    if not _in_cohort(uid):
        _skip(decision, 'cohort')
        return
    if not _slots.acquire(blocking=False):
        _skip(decision, 'cap')
        return
    try:
        submit_with_context(
            llm_executor,
            _run,
            uid,
            decision,
            first_id,
            second_id,
            time.monotonic() + DECISION_DEADLINE_SECONDS,
        )
    except Exception:
        _slots.release()
        _skip(decision, 'error')


def submit_same_scene(uid: str, first_id: str, second_id: str) -> None:
    _submit(uid, 'same_scene', first_id, second_id)


def submit_resummary(uid: str, primary_id: str, joining_id: str) -> None:
    _submit(uid, 'resummary', primary_id, joining_id)
