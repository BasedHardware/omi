"""EXP-004: asynchronous, bounded, fail-closed relevance and owner measurement.

Admission IO happens only in the leaf worker. Tasks own strings and numeric
metadata, never conversation/candidate objects. No state or exception text is
logged or persisted. Failed attempts consume their dedupe claim and daily cap.
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Literal, cast

import redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from config.jev_decisions import RelevanceArm, percentage, uid_bucket
from database.jev_shadow import write_jev_shadow
from models.conversation_enums import ConversationSource
from utils.conversations import owner_jev, relevance_jev
from utils.conversations.relevance import JEV_DISCARD_THRESHOLD, RelevanceDecision
from utils.conversations.relevance_rules import transcript_word_count
from utils.executors import get_jev_shadow_executor, submit_with_context
from utils.llm.jev_client import ask_jev
from utils.metrics import (
    JEV_SHADOW_LATENCY,
    OWNER_JEV_SHADOW_SCORE,
    RELEVANCE_JEV_SHADOW_AGREEMENT,
    RELEVANCE_JEV_SHADOW_SCORE,
    record_jev_shadow_outcome,
)

Lane = Literal['relevance', 'owner']
DEADLINE_SECONDS = 2.5
_slots = {lane: threading.BoundedSemaphore(2) for lane in ('relevance', 'owner')}
_SOURCES = frozenset(source.value for source in ConversationSource)
_SUBJECT_KINDS = frozenset({'speaker', 'person', 'user', 'unknown', 'general_knowledge'})
_ADMIT_LUA = """
if redis.call('EXISTS', KEYS[2]) == 1 then return 2 end
local count = tonumber(redis.call('GET', KEYS[1]) or '0')
if count >= tonumber(ARGV[1]) then return 0 end
redis.call('INCR', KEYS[1])
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
redis.call('SET', KEYS[2], '1', 'EX', 5184000, 'NX')
return 1
"""


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _in_cohort(lane: Lane, conversation_id: str) -> bool:
    percent = (
        percentage('CONVERSATION_RELEVANCE_JEV_SHADOW_PERCENT')
        if lane == 'relevance'
        else percentage('MEMORY_OWNER_JEV_SHADOW_PERCENT')
    )
    return uid_bucket(conversation_id, f'{lane}-shadow-v1') < percent


def _get_shadow_redis(deadline: float) -> Any:
    """A lazy, attempt-owned pool avoids sharing mutable socket deadlines."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError
    # Leave budget for connect/auth/command reads; no health-check or retry IO.
    timeout = min(0.5, remaining / 8)
    port = os.getenv('REDIS_DB_PORT')
    return redis.Redis(
        host=cast(str, os.getenv('REDIS_DB_HOST')),
        port=int(port) if port is not None else 6379,
        username='default',
        password=os.getenv('REDIS_DB_PASSWORD'),
        ssl=False,
        socket_connect_timeout=timeout,
        socket_timeout=timeout,
        retry=Retry(NoBackoff(), 0),
        retry_on_timeout=False,
        health_check_interval=0,
        max_connections=1,
        lib_name='',
        lib_version='',
    )


def _admit(lane: Lane, uid: str, conversation_id: str, content_sha: str, version: str, deadline: float) -> str:
    try:
        cap = int(
            os.getenv('CONVERSATION_RELEVANCE_JEV_SHADOW_DAILY_CAP', '60000')
            if lane == 'relevance'
            else os.getenv('MEMORY_OWNER_JEV_SHADOW_DAILY_CAP', '60000')
        )
    except ValueError:
        return 'cap'
    if cap <= 0:
        return 'cap'
    now = datetime.now(timezone.utc)
    ttl = 86400 - (now.hour * 3600 + now.minute * 60 + now.second) + 60
    fingerprint = _sha(f'{uid}\0{conversation_id}\0{content_sha}\0{version}')
    try:
        with _get_shadow_redis(deadline) as client:
            result = client.eval(
                _ADMIT_LUA,
                2,
                f'jev:shadow:{lane}:{now:%Y%m%d}',
                f'jev:shadow:{lane}:claim:{fingerprint}',
                cap,
                ttl,
            )
        return 'admitted' if result == 1 else 'deduped' if result == 2 else 'cap'
    except Exception:
        return 'redis_unavailable'


def _submit(
    lane: Lane, uid: str, conversation_id: str, content_sha: str, state: str, name: str | None, record: dict[str, Any]
) -> None:
    if not _in_cohort(lane, conversation_id):
        record_jev_shadow_outcome(lane, 'cohort')
        return
    slot = _slots[lane]
    if not slot.acquire(blocking=False):
        record_jev_shadow_outcome(lane, 'dropped')
        return
    try:
        future = submit_with_context(
            get_jev_shadow_executor(),
            _run,
            lane,
            uid,
            conversation_id,
            content_sha,
            state,
            name,
            record,
            time.monotonic() + DEADLINE_SECONDS,
        )
        # A shutdown cancellation never enters the worker's finally block.
        future.add_done_callback(lambda task: slot.release() if task.cancelled() else None)
    except Exception:
        slot.release()
        record_jev_shadow_outcome(lane, 'dropped')


def _run(
    lane: Lane,
    uid: str,
    conversation_id: str,
    content_sha: str,
    state: str,
    name: str | None,
    record: dict[str, Any],
    deadline: float,
) -> None:
    try:
        if not _in_cohort(lane, conversation_id):
            record_jev_shadow_outcome(lane, 'cohort')
            return
        if time.monotonic() >= deadline:
            record_jev_shadow_outcome(lane, 'timeout')
            return
        admission = _admit(lane, uid, conversation_id, content_sha, record['question_version'], deadline)
        if admission != 'admitted':
            record_jev_shadow_outcome(lane, admission)
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            record_jev_shadow_outcome(lane, 'timeout')
            return
        outcomes: list[str] = []
        answers = ask_jev(
            state,
            relevance_jev.QUESTIONS if lane == 'relevance' else owner_jev.owner_questions(name),
            lane=relevance_jev.LANE if lane == 'relevance' else owner_jev.LANE,
            timeout_seconds=remaining,
            max_attempts=1,
            outcome_observer=outcomes.append,
        )
        JEV_SHADOW_LATENCY.labels(lane).observe(time.monotonic() - (deadline - DEADLINE_SECONDS))
        if time.monotonic() > deadline:
            record_jev_shadow_outcome(lane, 'timeout')
            return
        if answers is None:
            outcome = outcomes[-1] if outcomes and outcomes[-1] in {'timeout', 'http_429'} else 'jev_failed'
            record_jev_shadow_outcome(lane, outcome)
            return
        served_model = answers.served_model
        record['served_model'] = (
            served_model if served_model and re.fullmatch(r'typesafe/jev-1\.13(?:-\d{8})?', served_model) else None
        )
        if lane == 'relevance':
            p_discard = 1.0 - answers.noul(relevance_jev.QUESTION_NAME)
            record['p_discard'] = p_discard
            RELEVANCE_JEV_SHADOW_SCORE.observe(p_discard)
            RELEVANCE_JEV_SHADOW_AGREEMENT.labels(
                record['nano_verdict'] or 'none', 'true' if p_discard > JEV_DISCARD_THRESHOLD else 'false'
            ).inc()
        else:
            probabilities = answers.answers[owner_jev.QUESTION_NAME]['probabilities']
            if not all(option in probabilities for option in ('user', 'third_party', 'general_knowledge')):
                record_jev_shadow_outcome(lane, 'jev_failed')
                return
            for option in ('user', 'third_party', 'general_knowledge'):
                record[f'p_{option}'] = answers.choice_probability(owner_jev.QUESTION_NAME, option)
            OWNER_JEV_SHADOW_SCORE.observe(record['p_user'])
        record_id = _sha(f'{lane}|{conversation_id}|{content_sha}')[:32]
        write_jev_shadow(uid, record_id, record, deadline=deadline)
        record_jev_shadow_outcome(lane, 'ok')
    except TimeoutError:
        record_jev_shadow_outcome(lane, 'timeout')
    except Exception:
        record_jev_shadow_outcome(lane, 'jev_failed')
    finally:
        _slots[lane].release()


def submit_relevance_shadow(
    *,
    uid: str,
    conversation_id: str,
    transcript: str,
    decision: RelevanceDecision,
    arm: RelevanceArm,
    source: str,
    transcript_only: bool,
) -> None:
    """Copy the transcript and decision metadata after the relevance decision; never raises."""
    try:
        if not decision.model_tier_reached or not transcript_only or arm == 'jev':
            return
        if not relevance_jev.jev_tier_applies(transcript):
            return
        if not _in_cohort('relevance', conversation_id):
            record_jev_shadow_outcome('relevance', 'cohort')
            return
        transcript_copy = str(transcript)
        _submit(
            'relevance',
            uid,
            conversation_id,
            _sha(transcript_copy),
            relevance_jev.relevance_state(transcript_copy),
            None,
            {
                'lane': 'relevance',
                'conversation_id': conversation_id,
                'question_version': relevance_jev.QUESTION_VERSION,
                'threshold': JEV_DISCARD_THRESHOLD,
                'arm': arm,
                'nano_verdict': decision.nano_verdict,
                'nano_reason': (
                    decision.nano_reason
                    if decision.nano_reason in {'neighbor_fragment', 'model_discard', 'model_keep'}
                    else None
                ),
                'source': source if source in _SOURCES else 'unknown',
                'word_count': transcript_word_count(transcript_copy),
                'trigger': decision.trigger.value,
            },
        )
    except Exception:
        record_jev_shadow_outcome('relevance', 'dropped')


def owner_shadow_in_cohort(conversation_id: str) -> bool:
    return _in_cohort('owner', conversation_id)


def submit_owner_shadow(
    *,
    uid: str,
    conversation_id: str,
    candidate_content: str,
    state: str,
    user_name: str | None,
    pipeline_subject_kind: str,
    source: str,
    n_quotes: int,
    user_name_present: bool,
) -> None:
    """The caller has already excluded live-scored and non-third-party candidates."""
    try:
        _submit(
            'owner',
            uid,
            conversation_id,
            _sha(candidate_content),
            str(state),
            user_name,
            {
                'lane': 'owner',
                'conversation_id': conversation_id,
                'candidate_sha': _sha(candidate_content),
                'question_version': owner_jev.QUESTION_VERSION,
                'pipeline_subject_kind': (
                    pipeline_subject_kind if pipeline_subject_kind in _SUBJECT_KINDS else 'unknown'
                ),
                'source': source if source in _SOURCES else 'unknown',
                'n_quotes': n_quotes,
                'user_name_present': user_name_present,
            },
        )
    except Exception:
        record_jev_shadow_outcome('owner', 'dropped')
