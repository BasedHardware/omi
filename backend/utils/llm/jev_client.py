"""Backend client for the Jev decision model, through the LLM gateway (#14835).

Jev takes one shared ``state`` string and a set of typed ``questions`` and
returns a probability per yes/no ("noul") question and a distribution per
choice question. It generates no text, so there is no prompt output to parse.

The call goes to the gateway's ``/v1/systemone`` surface on the pinned
``omi:auto:jev-decisions`` lane; the gateway holds the OpenRouter credential and
records accounting. This client never reaches a provider directly.

Every failure — gateway not configured, timeout, transport error, non-2xx,
an answer that does not match the questions asked, or a different model
version than the pinned one — returns ``None``. Callers treat ``None`` as "no
answer" and keep their existing safe default. Nothing here raises.
"""

from __future__ import annotations

import logging
import math
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Optional, cast

import httpx

from config.jev_decisions import (
    JEV_AUTO_LANE_ID,
    JEV_CLIENT_MAX_ATTEMPTS,
    JEV_CLIENT_TIMEOUT_SECONDS,
    JEV_MAX_STATE_CHARS,
    JEV_MODEL,
)
from utils.llm.gateway_client import LLM_GATEWAY_URL_ENV_VAR, get_llm_gateway_base_url, llm_gateway_headers
from utils.metrics import record_jev_decision

logger = logging.getLogger(__name__)

SYSTEMONE_PATH = '/v1/systemone'
TRUNCATION_MARKER = '\n[... truncated ...]\n'
_RETRYABLE_STATUS_CODES = frozenset({500, 502, 503, 504})


@dataclass(frozen=True)
class JevAnswers:
    """Validated answers for exactly the questions that were asked."""

    served_model: Optional[str]
    answers: Mapping[str, Mapping[str, Any]]

    def noul(self, name: str) -> float:
        """Probability that the answer to a noul (yes/no) question is true."""
        return float(self.answers[name]['noul'])

    def choice_probability(self, name: str, option: str) -> float:
        """Probability of one option of a choice question (0.0 when absent)."""
        probabilities = cast(Mapping[str, Any], self.answers[name]['probabilities'])
        return float(probabilities.get(option, 0.0))


class _AttemptFailed(Exception):
    def __init__(self, outcome: str, *, retryable: bool) -> None:
        super().__init__(outcome)
        self.outcome = outcome
        self.retryable = retryable


def truncate_state(state: str, *, max_chars: int = JEV_MAX_STATE_CHARS) -> str:
    """Bound a state to the route's context window, keeping its head and tail.

    Head carries the framing a state builder puts first; the tail is the most
    recent speech. Both matter more than the middle of a long transcript.
    """
    if len(state) <= max_chars:
        return state
    keep = max_chars - len(TRUNCATION_MARKER)
    head = keep * 2 // 3
    tail = keep - head
    return state[:head] + TRUNCATION_MARKER + state[len(state) - tail :]


def ask_jev(
    state: str,
    questions: Mapping[str, Mapping[str, Any]],
    *,
    lane: str,
    timeout_seconds: float = JEV_CLIENT_TIMEOUT_SECONDS,
    max_attempts: int = JEV_CLIENT_MAX_ATTEMPTS,
) -> Optional[JevAnswers]:
    """Ask Jev ``questions`` about ``state``. ``None`` on any failure.

    ``lane`` is the bounded product decision name used for metrics and gateway
    usage attribution (``conversation_relevance`` or ``memory_owner``).
    """
    started = time.monotonic()
    outcome = 'success'
    try:
        if not os.getenv(LLM_GATEWAY_URL_ENV_VAR, '').strip():
            outcome = 'unconfigured'
            return None
        body = {'model': JEV_AUTO_LANE_ID, 'state': truncate_state(state), 'questions': dict(questions)}
        attempts = max(1, max_attempts)
        for attempt in range(1, attempts + 1):
            try:
                raw = _post_once(body, lane=lane, timeout_seconds=timeout_seconds)
            except _AttemptFailed as exc:
                outcome = exc.outcome
                if exc.retryable and attempt < attempts:
                    continue
                return None
            answers = _validated_answers(raw, questions)
            if answers is None:
                outcome = 'malformed'
                return None
            outcome = 'success'
            return answers
        return None
    except Exception as exc:  # never let a decision helper change the caller's outcome
        outcome = 'transport_error'
        logger.warning('jev decision failed lane=%s reason=%s', lane, type(exc).__name__)
        return None
    finally:
        if outcome != 'success':
            logger.info('jev decision unavailable lane=%s outcome=%s', lane, outcome)
        record_jev_decision(lane=lane, outcome=outcome, latency_seconds=time.monotonic() - started)


def _post_once(body: Mapping[str, Any], *, lane: str, timeout_seconds: float) -> object:
    timeout = httpx.Timeout(timeout_seconds, connect=min(1.0, timeout_seconds))
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f'{get_llm_gateway_base_url()}{SYSTEMONE_PATH}',
                headers=llm_gateway_headers(feature=f'jev_{lane}'),
                json=dict(body),
            )
    except httpx.TimeoutException as exc:
        raise _AttemptFailed('timeout', retryable=True) from exc
    except httpx.HTTPError as exc:
        raise _AttemptFailed('transport_error', retryable=True) from exc
    if response.status_code == 429:
        raise _AttemptFailed('http_error', retryable=False)
    if response.status_code in _RETRYABLE_STATUS_CODES:
        raise _AttemptFailed('http_error', retryable=True)
    if response.status_code >= 400:
        # A 4xx (bad request, lane absent on an older gateway) will not change on retry.
        raise _AttemptFailed('http_error', retryable=False)
    try:
        return cast(object, response.json())
    except ValueError:
        return None


def _validated_answers(raw: object, questions: Mapping[str, Mapping[str, Any]]) -> Optional[JevAnswers]:
    if not isinstance(raw, Mapping):
        return None
    body = cast(Mapping[str, Any], raw)
    served_model = body.get('model')
    if served_model is not None and not _is_pinned_model(served_model):
        return None
    answers = body.get('answers')
    if not isinstance(answers, Mapping):
        return None
    answer_map = cast(Mapping[str, Any], answers)
    validated: dict[str, Mapping[str, Any]] = {}
    for name, question in questions.items():
        answer = answer_map.get(name)
        if not isinstance(answer, Mapping):
            return None
        typed_answer = cast(Mapping[str, Any], answer)
        question_type = question.get('type')
        if question_type == 'noul':
            if not _is_probability(typed_answer.get('noul')):
                return None
        elif question_type == 'choice':
            probabilities = typed_answer.get('probabilities')
            if not isinstance(probabilities, Mapping) or not all(
                _is_probability(value) for value in cast(Mapping[str, Any], probabilities).values()
            ):
                return None
        validated[name] = typed_answer
    return JevAnswers(served_model=served_model if isinstance(served_model, str) else None, answers=validated)


def _is_pinned_model(value: object) -> bool:
    """The served model must be the pinned version or one of its dated snapshots."""
    return isinstance(value, str) and (value == JEV_MODEL or value.startswith(f'{JEV_MODEL}-'))


def _is_probability(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value)) and 0.0 <= float(value) <= 1.0
