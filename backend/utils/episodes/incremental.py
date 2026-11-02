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
import re
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
    episode_moment_output_validator_enabled,
    episode_output_language_pinned,
)
from config.refactor_modes import serving_for, shadow_or_serve
from database.auth import get_user_name
from utils.episodes.moment_render import render_segments
from utils.llm.notes_packet import get_evidence
from utils.llm.notes_refactor_metrics import shadow
from utils.llm.output_language import resolve_output_language
from utils.episodes.state import IncrementalUpdate, parse_update
from utils.llm.clients import get_llm
from utils.llm.jev_client import ask_jev
from utils.llm.usage_tracker import track_usage
from utils.speakers.display import display_participants

logger = logging.getLogger(__name__)

MIN_VERBATIM_REJECTION_WORDS = 10
VERBATIM_OVERLAP_RATIO = 0.8
MAX_SHORT_QUOTE_WORDS = 8
_QUALITY_WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)?", re.UNICODE)
_QUOTED_TEXT = re.compile(r'["“]([^"”\n]+)["”]')
_SPEAKER_LABEL = re.compile(
    r"(?im)(?:^|[\n;])\s*(?:[-•*]\s*)?(?:you|owner|others?|unknown speaker|speaker(?:\s*[a-z0-9]+)?)\s*:"
)

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
- Dialogue labels like "You", "Speaker A" or "Speaker B" are voice markers, not names. NEVER copy a
  "Speaker" label or any number from one into any field; call that person "a speaker" or "another
  speaker" until their name is known, and never invent one.
- "title" and "moment_heading" must say what the speech was about; never a placeholder such as
  "New moment", "Conversation" or "Talking".
- "open_questions": at most 4 things left unresolved, or [].
- "items": only tasks or reminders someone (usually the owner) committed to, or that the owner asked
  Omi for. Each: {"id": existing id when you are editing an existing item, omitted for a new one,
  "text": imperative, at most 12 words, "kind": "task" or "reminder", "explicit": true only when the
  speaker addressed Omi directly, "due": ISO 8601 local time when a time was said, else null}.
  Do not list an existing item again unless you change it. Never invent a commitment.
- "drop_ids": ids of existing items the new speech cancels or shows are already done.
- Speech can be noisy transcription. Ignore filler, ads, TV and background talk.
- The "You" label (or the owner's own name) marks the person wearing Omi; report their words and
  actions in the third person, like everyone else's.

Reply with one JSON object only:
{"title": "", "moment_heading": "", "bullets": [], "people": [], "open_questions": [], "items": [], "drop_ids": []}
"""

PROMPT_PREFIX = _MOMENT_OPENING + _MOMENT_LEGACY_LANGUAGE + _MOMENT_RULES


def _moment_prompt(output_language: str) -> str:
    # Keep the resolved-language directive last so it governs titles, headings,
    # bullets and every other generated field regardless of the speech language.
    return (
        _MOMENT_OPENING
        + '- Be concrete: names, places, numbers, decisions.\n'
        + '- Use names only from confident speaker evidence; hedge likely matches as "likely X"; '
        'unknown voices are "a speaker". Never assign personal stories to a name without evidence.\n'
        + _MOMENT_RULES
        + f'\nWrite all output in {output_language}. Keep names and quoted words verbatim.\n'
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
    voice_order: tuple[str, ...] = ()
    truncated: bool = False


def _quality_words(value: str) -> tuple[str, ...]:
    return tuple(word.casefold() for word in _QUALITY_WORD.findall(value))


def validate_moment_output(update: IncrementalUpdate, transcript: str) -> tuple[str, ...]:
    """Reject bullets that are mostly transcript text, and transcript speaker labels.

    Short quotations and concise summaries can reuse transcript phrases. Only
    bullets with at least ten words and an 80% ordered word overlap are treated
    as transcript copies. Labels in transcript input are stripped before matching.
    """
    transcript_words = []
    for line in transcript.splitlines():
        clean = re.sub(r'^\s*[^:\n]{1,48}:\s*', '', line).strip()
        transcript_words.extend(_quality_words(clean))
    issues: list[str] = []
    for bullet in update.bullets:
        if _SPEAKER_LABEL.search(bullet):
            issues.append('speaker_label')
            continue
        overlap_text = _QUOTED_TEXT.sub(
            lambda match: ' ' if len(_quality_words(match.group(1))) <= MAX_SHORT_QUOTE_WORDS else match.group(0),
            bullet,
        )
        bullet_words = _quality_words(overlap_text)
        if len(bullet_words) < MIN_VERBATIM_REJECTION_WORDS or not transcript_words:
            continue
        previous = [0] * (len(transcript_words) + 1)
        for word in bullet_words:
            current = [0] * (len(transcript_words) + 1)
            for index, transcript_word in enumerate(transcript_words, start=1):
                if word == transcript_word:
                    current[index] = previous[index - 1] + 1
                else:
                    current[index] = max(previous[index], current[index - 1])
            previous = current
        if max(previous, default=0) / len(bullet_words) >= VERBATIM_OVERLAP_RATIO:
            issues.append('verbatim_overlap')
    return tuple(dict.fromkeys(issues))


def _resolve_owner_name(uid: str | None) -> str | None:
    if not uid:
        return None
    try:
        return get_user_name(uid, use_default=False)
    except Exception:
        return None


def render_moment(
    segments: Sequence[Mapping[str, Any]],
    *,
    uid: str | None = None,
    conversation_id: str | None = None,
    owner_name: str | None = None,
    voice_order: Sequence[str] | None = None,
) -> MomentText:
    """Speaker-labelled lines, consecutive lines from one voice joined, head and tail kept."""
    owner = owner_name or _resolve_owner_name(uid) or 'You'
    display = display_participants(
        segments, owner_name=owner, voice_order=voice_order, display_scope=conversation_id, defer_short_voices=True
    )
    legacy = _legacy_moment(segments, display)
    if shadow_or_serve('NOTES_PACKET_V2_MODE'):
        serving = serving_for('NOTES_PACKET_V2_MODE', uid)
        # Shadow compares renderers without the evidence read; only the serving cohort pays for it.
        evidence = get_evidence(uid, conversation_id) if serving else None
        text, words = render_segments(segments, evidence=evidence, owner_name=owner)
        shadow('moment_render', 'agree' if text == legacy[0] else 'disagree', rendered_chars=len(text), words=words)
        if serving:
            return MomentText(_bounded_moment(text), words, display.voice_order, len(text) > MOMENT_TEXT_MAX_CHARS)
    return MomentText(
        _bounded_moment(legacy[0]), legacy[1], display.voice_order, len(legacy[0]) > MOMENT_TEXT_MAX_CHARS
    )


def _legacy_moment(segments: Sequence[Mapping[str, Any]], display: Any) -> tuple[str, int]:
    # refactor: superseded by moment_render.render_segments when NOTES_PACKET_V2_MODE=serve
    lines: list[list[str]] = []
    previous_voice = None
    words = 0
    for segment in segments:
        text = str(segment.get('text') or '').strip()
        if not text:
            continue
        words += len(text.split())
        participant = display.for_segment(segment)
        label = participant.label
        voice = (
            ('user',)
            if participant.name and segment.get('is_user')
            else (
                ('person', segment['person_id'])
                if participant.name and segment.get('person_id')
                else ('voice', participant.key)
            )
        )
        if lines and previous_voice == voice:
            lines[-1][1] += ' ' + text
        else:
            lines.append([label, text])
        previous_voice = voice
    return '\n'.join(f'{label}: {text}' for label, text in lines), words


def _bounded_moment(rendered: str) -> str:
    if len(rendered) > MOMENT_TEXT_MAX_CHARS:
        marker = '\n[…]\n'
        keep = MOMENT_TEXT_MAX_CHARS - len(marker)
        head = keep // 3
        rendered = rendered[:head] + marker + rendered[-(keep - head) :]
    return rendered


def build_messages(
    state_json: str,
    moment: str,
    *,
    now: datetime,
    tz_name: str,
    output_language: str | None = None,
    repair_instruction: str | None = None,
) -> list[tuple[str, str]]:
    """Fixed prefix first; the clock, state and new speech last."""
    try:
        local = now.astimezone(ZoneInfo(tz_name))
    except Exception:
        local, tz_name = now, 'UTC'
    repair = f'{repair_instruction}\n' if repair_instruction else ''
    volatile = (
        f'Local time now: {local.strftime("%Y-%m-%d %H:%M")} ({tz_name})\n'
        f'{repair}'
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
    model_calls: int = 1


class ModelCallFailed(RuntimeError):
    def __init__(
        self,
        outcome: str,
        latency_seconds: float,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        model_calls: int = 1,
    ):
        super().__init__(outcome)
        self.outcome = outcome
        self.latency_seconds = latency_seconds
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.model_calls = model_calls


def _usage(reply: Any) -> tuple[int, int]:
    usage = getattr(reply, 'usage_metadata', None) or {}
    if isinstance(usage, Mapping):
        return int(usage.get('input_tokens') or 0), int(usage.get('output_tokens') or 0)
    return 0, 0


def _invoke_and_parse(uid: str, messages: list[tuple[str, str]], invoke, known_item_ids: Sequence[str]) -> ModelResult:
    started = time.monotonic()
    try:
        reply = (invoke or invoke_model)(uid, messages)
    except Exception as error:
        logger.warning('event=episode_moment outcome=llm_error exception_type=%s', type(error).__name__)
        raise ModelCallFailed('llm_error', time.monotonic() - started) from error
    latency = time.monotonic() - started
    input_tokens, output_tokens = _usage(reply)
    content = getattr(reply, 'content', reply)
    if isinstance(content, list):
        content = ''.join(part.get('text', '') if isinstance(part, Mapping) else str(part) for part in content)
    try:
        update = parse_update(str(content), known_item_ids=known_item_ids)
    except ValueError as error:
        raise ModelCallFailed('parse_error', latency, input_tokens=input_tokens, output_tokens=output_tokens) from error
    return ModelResult(update, input_tokens, output_tokens, latency)


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
    repair_instruction: str | None = None,
) -> ModelResult:
    """One cheap call. Raises ``ModelCallFailed`` (llm_error | parse_error); never partial state."""
    language = None
    if episode_output_language_pinned() or serving_for('NOTES_PACKET_V2_MODE', uid):
        language = output_language or resolve_output_language(uid, conversation_language)
    messages = build_messages(
        state_json, moment, now=now, tz_name=tz_name, output_language=language, repair_instruction=repair_instruction
    )
    first = _invoke_and_parse(uid, messages, invoke, known_item_ids)
    if not episode_moment_output_validator_enabled():
        return first

    # The validation retry uses the same bounded transcript and a fresh JSON
    # response. The issue names are fixed enums; no transcript text is logged.
    issues = validate_moment_output(first.update, moment)
    if not issues:
        return first

    repair = (
        'Quality correction required: rewrite any bullet that mostly copies the newest moment as a concise '
        'third-person summary. Short quotes and concise summaries may reuse speech. Do not start a bullet with '
        'a speaker label such as You:, Others:, or Speaker A:. '
        'Return the complete corrected JSON object.'
    )
    retry_messages = build_messages(
        state_json,
        moment,
        now=now,
        tz_name=tz_name,
        output_language=language,
        repair_instruction='\n'.join(part for part in (repair_instruction, repair) if part),
    )
    try:
        second = _invoke_and_parse(uid, retry_messages, invoke, known_item_ids)
    except ModelCallFailed as failure:
        raise ModelCallFailed(
            failure.outcome,
            first.latency_seconds + failure.latency_seconds,
            input_tokens=first.input_tokens + failure.input_tokens,
            output_tokens=first.output_tokens + failure.output_tokens,
            model_calls=first.model_calls + failure.model_calls,
        ) from failure
    retry_issues = validate_moment_output(second.update, moment)
    if retry_issues:
        raise ModelCallFailed(
            'quality_error',
            first.latency_seconds + second.latency_seconds,
            input_tokens=first.input_tokens + second.input_tokens,
            output_tokens=first.output_tokens + second.output_tokens,
            model_calls=first.model_calls + second.model_calls,
        )
    return ModelResult(
        second.update,
        first.input_tokens + second.input_tokens,
        first.output_tokens + second.output_tokens,
        first.latency_seconds + second.latency_seconds,
        first.model_calls + second.model_calls,
    )


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
