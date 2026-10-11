"""Bounded screen OCR decision through the existing company-paid Jev gateway lane."""

from __future__ import annotations

import math
import os
import random
from dataclasses import dataclass
from typing import Literal

from utils.llm.jev_client import ask_jev
from utils.observability.fallback import record_fallback

QUESTION_VERSION = 'screen_task_main_pane_review_v1'
QUESTIONS = {
    'needs_extraction': {
        'type': 'noul',
        'instructions': (
            'Does the open main pane contain a specific unfinished action or question for THIS user, '
            'their commitment or reminder, or evidence changing/completing an existing task? '
            'Treat uncertainty as yes. Ignore sidebars and task/inbox/PR overview lists. '
            "Read the full conversation; the user's own instruction to an assistant is not a task for the user. "
            'An open pull request or issue with a personal review/approval-required indicator counts '
            'as a direct request; a pull-request list does not.'
        ),
        'criteria': {
            'true': (
                'yes: a specific request to this user, a commitment by this user, a self-reminder, '
                'or an update to a listed existing task is visible in an open conversation, email, document or note; '
                'also an open pull request or issue with a personal review or approval required indicator'
            ),
            'false': (
                'no: it is a list or overview (chat list, inbox list, thread overview), a feed, article, newsletter, '
                'marketing email, documentation, code, dashboard, board, calendar or video; or only small talk; '
                'or the request is addressed to someone else; or the user already did or declined it'
            ),
        },
    }
}


@dataclass(frozen=True)
class ScreenTaskGateDecision:
    should_extract: bool
    outcome: Literal['passed', 'rejected', 'fail_open']
    audit_sample: bool = False


def _probability_env(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
        return value if math.isfinite(value) and 0 <= value <= 1 else default
    except ValueError:
        return default


def decide_screen_task(state: str, *, audit_draw: float | None = None) -> ScreenTaskGateDecision:
    # One attempt: caller latency is bounded and a missing decision must preserve recall.
    answers = ask_jev(state, QUESTIONS, lane='screen_task', timeout_seconds=2.0, max_attempts=1)
    if answers is None:
        record_fallback(
            component='screen_task_gate',
            from_mode='jev',
            to_mode='gemini_3_8',
            reason='gate_unavailable',
            outcome='recovered',
        )
        return ScreenTaskGateDecision(True, 'fail_open')
    if answers.noul('needs_extraction') >= _probability_env('SCREEN_TASK_JEV_THRESHOLD', 0.5):
        return ScreenTaskGateDecision(True, 'passed')
    sampled = (random.random() if audit_draw is None else audit_draw) < _probability_env(
        'SCREEN_TASK_JEV_AUDIT_RATE', 0.01
    )
    return ScreenTaskGateDecision(sampled, 'rejected', sampled)
