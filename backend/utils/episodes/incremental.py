"""The cheap per-moment update and the Jev boundary question.

One call per moment: the previous compact state (a few hundred tokens) plus
that moment's new text. The earlier transcript is never re-read. The prompt is
a fixed instruction prefix followed by the volatile parts (clock, state, new
text, in that order), so providers that cache prefixes can reuse it.

Every failure is fail-open for the caller: the state stays as it was and the
conversation's own processing is untouched.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

from config.episodes import (
    INCREMENTAL_FEATURE,
    INCREMENTAL_TIMEOUT_SECONDS,
    JEV_LANE,
    JEV_TIMEOUT_SECONDS,
    MOMENT_TEXT_MAX_CHARS,
)
from config.refactor_modes import serving_for, shadow_or_serve
from utils.episodes.moment_render import render_segments
from utils.llm.notes_packet import get_evidence
from utils.llm.notes_refactor_metrics import shadow
from utils.llm.output_language import resolve_output_language
from utils.episodes.state import IncrementalUpdate, parse_update
from utils.llm.clients import get_llm
from utils.llm.jev_client import ask_jev
from utils.llm.usage_tracker import track_usage

logger = logging.getLogger(__name__)

_MOMENT_OPENING = """You keep the running notes for one live episode of a person's day, as heard by their Omi.
You receive the episode state so far (JSON) and the newest moment of speech. Return the updated state.

Rules:
"""
_MOMENT_LEGACY_LANGUAGE = '- Write in the language the people speak. Be concrete: names, places, numbers, decisions.\n'
_MOMENT_RULES = """- "bullets": the whole episode so far, at most 8 short lines, newest information folded in, oldest
  trivia dropped. Do not repeat a bullet in other words.
- "title": a short topic for the whole episode (at most 6 words), not for this moment only.
- "moment_heading": at most 4 words naming what this newest moment was about.
- "people": names of the people taking part or addressed, never "Speaker 2".
- "open_questions": at most 4 things left unresolved, or [].
- "items": only tasks or reminders someone (usually the owner) committed to, or that the owner asked
  Omi for. Each: {"id": existing id when you are editing an existing item, omitted for a new one,
  "text": imperative, at most 12 words, "kind": "task" or "reminder", "explicit": true only when the
  speaker addressed Omi directly, "due": ISO 8601 local time when a time was said, else null}.
  Do not list an existing item again unless you change it. Never invent a commitment.
- "drop_ids": ids of existing items the new speech cancels or shows are already done.
- Speech can be noisy transcription. Ignore filler, ads, TV and background talk.

Reply with one JSON object only:
{"title": "", "moment_heading": "", "bullets": [], "people": [], "open_questions": [], "items": [], "drop_ids": []}
"""

PROMPT_PREFIX = _MOMENT_OPENING + _MOMENT_LEGACY_LANGUAGE + _MOMENT_RULES


def _moment_prompt(output_language: str) -> str:
    return (
        _MOMENT_OPENING + f'- Write all fields, including title and moment_heading, in {output_language}. '
        'Be concrete: names, places, numbers, decisions.\n'
        '- Use names only from confident speaker evidence; hedge likely matches as "likely X"; '
        'unknown voices are "a speaker". Never assign personal stories to a name without evidence.\n' + _MOMENT_RULES
    )


BOUNDARY_QUESTION = 'same_occasion'
BOUNDARY_QUESTIONS: dict[str, dict[str, Any]] = {
    BOUNDARY_QUESTION: {
        'type': 'noul',
        'instructions': (
            'Does the NEW speech continue the same real-world occasion as the EPISODE so far (the same '
            'gathering, meal, outing, meeting, work session, call or trip resuming after a lull), so the '
            'user would want them shown as one episode?'
        ),
        'criteria': {
            'true': 'The same occasion carries on: the same people, place or activity continues, even if the topic drifts.',
            'false': 'The user moved on: a new call, meeting, visit or activity, or unrelated audio, with different people or purpose.',
        },
    },
}


@dataclass(frozen=True)
class MomentText:
    text: str
    words: int


def speaker_label(segment: Mapping[str, Any]) -> str:
    if segment.get('is_user'):
        return 'Owner'
    name = segment.get('person_name') or segment.get('speaker_name')
    if isinstance(name, str) and name.strip() and not name.strip().lower().startswith('speaker'):
        return name.strip()
    speaker_id = segment.get('speaker_id')
    return f'Speaker {speaker_id}' if speaker_id is not None else 'Speaker'


def render_moment(
    segments: Sequence[Mapping[str, Any]],
    *,
    uid: str | None = None,
    conversation_id: str | None = None,
) -> MomentText:
    """Speaker-labelled lines, consecutive lines from one voice joined, head and tail kept."""
    legacy = _legacy_moment(segments)
    if shadow_or_serve('NOTES_PACKET_V2_MODE'):
        serving = serving_for('NOTES_PACKET_V2_MODE', uid)
        # Shadow compares renderers without the evidence read; only the serving cohort pays for it.
        evidence = get_evidence(uid, conversation_id) if serving else None
        text, words = render_segments(segments, evidence=evidence)
        shadow('moment_render', 'agree' if text == legacy[0] else 'disagree', rendered_chars=len(text), words=words)
        if serving:
            return MomentText(_bounded_moment(text), words)
    return MomentText(_bounded_moment(legacy[0]), legacy[1])


def _legacy_moment(segments: Sequence[Mapping[str, Any]]) -> tuple[str, int]:
    # refactor: superseded by moment_render.render_segments when NOTES_PACKET_V2_MODE=serve
    lines: list[list[str]] = []
    words = 0
    for segment in segments:
        text = str(segment.get('text') or '').strip()
        if not text:
            continue
        words += len(text.split())
        label = speaker_label(segment)
        if lines and lines[-1][0] == label:
            lines[-1][1] += ' ' + text
        else:
            lines.append([label, text])
    return '\n'.join(f'{label}: {text}' for label, text in lines), words


def _bounded_moment(rendered: str) -> str:
    if len(rendered) > MOMENT_TEXT_MAX_CHARS:
        marker = '\n[…]\n'
        keep = MOMENT_TEXT_MAX_CHARS - len(marker)
        head = keep // 3
        rendered = rendered[:head] + marker + rendered[-(keep - head) :]
    return rendered


def build_messages(
    state_json: str, moment: str, *, now: datetime, tz_name: str, output_language: str | None = None
) -> list[tuple[str, str]]:
    """Fixed prefix first; the clock, state and new speech last."""
    try:
        local = now.astimezone(ZoneInfo(tz_name))
    except Exception:
        local, tz_name = now, 'UTC'
    volatile = (
        f'Local time now: {local.strftime("%Y-%m-%d %H:%M")} ({tz_name})\n'
        f'Episode state so far:\n{state_json}\n\n'
        f'Newest moment:\n{moment}'
    )
    prefix = PROMPT_PREFIX
    if output_language:
        prefix = _moment_prompt(output_language)
    return [('system', prefix), ('user', volatile)]


@dataclass
class ModelResult:
    update: IncrementalUpdate
    input_tokens: int
    output_tokens: int
    latency_seconds: float


class ModelCallFailed(RuntimeError):
    def __init__(self, outcome: str, latency_seconds: float):
        super().__init__(outcome)
        self.outcome = outcome
        self.latency_seconds = latency_seconds


def _usage(reply: Any) -> tuple[int, int]:
    usage = getattr(reply, 'usage_metadata', None) or {}
    if isinstance(usage, Mapping):
        return int(usage.get('input_tokens') or 0), int(usage.get('output_tokens') or 0)
    return 0, 0


def invoke_model(uid: str, messages: list[tuple[str, str]]) -> Any:
    with track_usage(uid, INCREMENTAL_FEATURE):
        llm = get_llm('episode_incremental', uid=uid, request_timeout=INCREMENTAL_TIMEOUT_SECONDS, max_retries=0)
        return llm.invoke(messages)


def run_incremental_update(
    uid: str,
    state_json: str,
    moment: str,
    *,
    known_item_ids: Sequence[str],
    now: datetime,
    tz_name: str,
    invoke=None,
    output_language: str | None = None,
    conversation_language: str | None = None,
) -> ModelResult:
    """One cheap call. Raises ``ModelCallFailed`` (llm_error | parse_error); never partial state."""
    language = None
    if serving_for('NOTES_PACKET_V2_MODE', uid):
        language = output_language or resolve_output_language(uid, conversation_language)
    messages = build_messages(state_json, moment, now=now, tz_name=tz_name, output_language=language)
    started = time.monotonic()
    try:
        reply = (invoke or invoke_model)(uid, messages)
    except Exception as error:
        logger.warning('event=episode_moment outcome=llm_error exception_type=%s', type(error).__name__)
        raise ModelCallFailed('llm_error', time.monotonic() - started) from error
    latency = time.monotonic() - started
    content = getattr(reply, 'content', reply)
    if isinstance(content, list):
        content = ''.join(part.get('text', '') if isinstance(part, Mapping) else str(part) for part in content)
    try:
        update = parse_update(str(content), known_item_ids=known_item_ids)
    except ValueError as error:
        raise ModelCallFailed('parse_error', latency) from error
    input_tokens, output_tokens = _usage(reply)
    return ModelResult(update, input_tokens, output_tokens, latency)


def boundary_state(
    episode: Mapping[str, Any],
    moment: str,
    *,
    gap_seconds: float,
    source_changed: bool,
    episode_source: Optional[str],
    moment_source: Optional[str],
    speakers_changed: bool,
) -> str:
    facts = {
        'episode_topic': episode.get('title') or '',
        'episode_bullets': list(episode.get('bullets') or [])[-5:],
        'episode_people': list(episode.get('people') or []),
        'minutes_since_last_speech': round(max(0.0, gap_seconds) / 60, 1),
        'device_changed': source_changed,
        'episode_device': episode_source or 'unknown',
        'new_device': moment_source or 'unknown',
        'voices_changed': speakers_changed,
    }
    return 'EPISODE so far:\n' + json.dumps(facts, ensure_ascii=False) + '\n\nNEW speech:\n' + moment[:2_500]


def ask_same_occasion(state: str, *, ask=None) -> Optional[float]:
    """P(the new speech continues the episode), or None when Jev has no answer."""
    try:
        answers = (ask or ask_jev)(
            state, BOUNDARY_QUESTIONS, lane=JEV_LANE, timeout_seconds=JEV_TIMEOUT_SECONDS, max_attempts=1
        )
        if answers is None:
            return None
        value = answers.noul(BOUNDARY_QUESTION)
        return value if 0.0 <= value <= 1.0 else None
    except Exception as error:
        logger.warning('event=episode_boundary outcome=jev_error exception_type=%s', type(error).__name__)
        return None
