"""Pick the few speaker clips worth asking the user about.
Pure: no IO. Feeds decoded conversations from the last 48 hours and returns a ranked, capped list of prompts:
1. "Is this you?" on the loudest unnamed voice when owner was missed or has no voiceprint.
2. "Is this <name>?" on an automatic match nobody has reviewed.
3. "Is this you?" on an automatic owner label nobody has reviewed.
4. "Who is this?" on the unnamed voices that talked the most.
Only clean clips qualify: one speaker, consecutive segments >= MIN_CLIP_SECONDS, not decided, with stored audio.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from models.speaker_tag_prompts import SpeakerTagPrompt, SpeakerTagPromptKind, SpeakerTagPromptOrigin
from models.transcript_segment import legacy_conversation_segment_id
from utils.speaker_tag_prompts.coverage import prompt_window_covered

PROMPT_WINDOW = timedelta(hours=48)
MIN_CLIP_SECONDS = 5.0
MAX_CLIP_SECONDS = 10.0
MAX_GAP_SECONDS = 1.5
DEFAULT_LIMIT = 4
MAX_PER_CONVERSATION = 2
MAX_OWNER_CHECKS = 2
MAX_SUGGESTED_PEOPLE = 5
EXCERPT_CHARS = 160


@dataclass(frozen=True)
class _Run:
    speaker_id: int
    identity: str  # 'user' | 'person:<id>' | 'none'
    segment_ids: Tuple[str, ...]
    start: float
    end: float
    text: str

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class _Candidate:
    score: float
    prompt: SpeakerTagPrompt
    conversation: Mapping[str, Any]
    expected_text: str


def prompt_id(conversation_id: str, speaker_id: int, kind: SpeakerTagPromptKind) -> str:
    digest = hashlib.sha256(f'{conversation_id}:{speaker_id}:{kind.value}'.encode('utf-8')).hexdigest()
    return digest[:24]


def _as_utc(value: Any) -> Optional[datetime]:
    if isinstance(value, str) and value.strip():
        try:
            value = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
        except ValueError:
            return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)) if isinstance(value, datetime) else None


def speaker_id_of(segment: Mapping[str, Any]) -> int:
    raw = segment.get('speaker_id')
    if isinstance(raw, int) and not isinstance(raw, bool):
        return raw
    speaker = segment.get('speaker') or ''
    try:
        return int(str(speaker).split('_', 1)[1])
    except (ValueError, IndexError):
        return 0


def _identity(segment: Mapping[str, Any]) -> str:
    if segment.get('is_user'):
        return 'user'
    if segment.get('person_id'):
        return f"person:{segment['person_id']}"
    return 'none'


def _normalized_segments(conversation: Mapping[str, Any]) -> List[Dict[str, Any]]:
    segments = []
    for index, raw in enumerate(conversation.get('transcript_segments') or []):
        segment = dict(raw)
        if not segment.get('id'):
            segment['id'] = legacy_conversation_segment_id(conversation['id'], index)
        segment['speaker_id'] = speaker_id_of(segment)
        segments.append(segment)
    segments.sort(key=lambda s: (float(s.get('start') or 0), float(s.get('end') or 0)))
    return segments


def _manually_decided(conversation: Mapping[str, Any]) -> Tuple[set, set]:
    receipt = conversation.get('manual_speaker_assignments') or {}
    speakers = {str(key) for key in (receipt.get('speakers') or {})}
    segments = set(receipt.get('segments') or {})
    return speakers, segments


def _runs(segments: Sequence[Mapping[str, Any]], decided_segments: set) -> List[_Run]:
    """Maximal same-speaker, same-identity stretches with no other voice in between."""
    runs: List[_Run] = []
    current: List[Mapping[str, Any]] = []

    def flush() -> None:
        if current:
            runs.append(
                _Run(
                    speaker_id=current[0]['speaker_id'],
                    identity=_identity(current[0]),
                    segment_ids=tuple(s['id'] for s in current),
                    start=float(current[0].get('start') or 0),
                    end=max(float(s.get('end') or 0) for s in current),
                    text=' '.join((s.get('text') or '').strip() for s in current).strip(),
                )
            )
        current.clear()

    for segment in segments:
        if segment.get('audio_alignment') == 'unplaced':
            flush()
            continue
        if segment['id'] in decided_segments:
            flush()
            continue
        if current:
            previous = current[-1]
            gap = float(segment.get('start') or 0) - float(previous.get('end') or 0)
            if (
                segment['speaker_id'] != previous['speaker_id']
                or _identity(segment) != _identity(previous)
                or segment.get('audio_capture_run') != previous.get('audio_capture_run')
                or gap > MAX_GAP_SECONDS
            ):
                flush()
        current.append(segment)
    flush()
    return runs


def _clip_window(run: _Run) -> Tuple[float, float]:
    if run.duration <= MAX_CLIP_SECONDS:
        return run.start, run.end
    center = (run.start + run.end) / 2
    half = MAX_CLIP_SECONDS / 2
    return center - half, center + half


def _clip_overlaps_other_speaker(segments: Sequence[Mapping[str, Any]], run: _Run) -> bool:
    clip_start, clip_end = _clip_window(run)
    return any(
        segment['speaker_id'] != run.speaker_id
        and float(segment.get('start') or 0) < clip_end
        and float(segment.get('end') or 0) > clip_start
        for segment in segments
    )


def _excerpt(text: str) -> str:
    text = ' '.join(text.split())
    return text if len(text) <= EXCERPT_CHARS else text[: EXCERPT_CHARS - 1].rstrip() + '…'


def _eligible(conversation: Mapping[str, Any], now: datetime) -> Optional[datetime]:
    if conversation.get('deleted') or conversation.get('discarded') or conversation.get('is_locked'):
        return None
    if conversation.get('status') not in (None, 'completed'):
        return None
    if not conversation.get('audio_files'):
        return None
    started = _as_utc(conversation.get('started_at')) or _as_utc(conversation.get('created_at'))
    if started is None or started < now - PROMPT_WINDOW or started > now + timedelta(minutes=5):
        return None
    return started


def recent_person_ids(conversations: Iterable[Mapping[str, Any]]) -> List[str]:
    counts: Counter = Counter()
    for conversation in conversations:
        for segment in conversation.get('transcript_segments') or []:
            if segment.get('person_id') and not segment.get('is_user'):
                counts[segment['person_id']] += 1
    return [person_id for person_id, _ in counts.most_common()]


def select_prompts(
    conversations: Sequence[Mapping[str, Any]],
    *,
    now: datetime,
    owner_has_voice: bool,
    named_allowed: bool,
    answered: set,
    people: Mapping[str, str],
    limit: int = DEFAULT_LIMIT,
    verify: Optional[Callable[[Mapping[str, Any], SpeakerTagPrompt, str], bool]] = None,
    max_verifications: int = 4,
    on_skip: Optional[Callable[[str], None]] = None,
) -> List[SpeakerTagPrompt]:
    """Return at most ``limit`` prompts, best first. ``people`` maps person id to name."""
    recent_people = [pid for pid in recent_person_ids(conversations) if pid in people]
    candidates: List[_Candidate] = []

    for conversation in conversations:
        started = _eligible(conversation, now)
        if started is None:
            continue
        conversation_id = conversation['id']
        segments = _normalized_segments(conversation)
        decided_speakers, decided_segments = _manually_decided(conversation)
        talk: Dict[int, float] = {}
        for segment in segments:
            talk[segment['speaker_id']] = talk.get(segment['speaker_id'], 0.0) + max(
                0.0, float(segment.get('end') or 0) - float(segment.get('start') or 0)
            )
        has_owner = any(segment.get('is_user') for segment in segments)
        labeled_here = {s['person_id'] for s in segments if s.get('person_id')}

        best_run: Dict[Tuple[int, str], _Run] = {}
        for run in _runs(segments, decided_segments):
            if (
                not run.text
                or str(run.speaker_id) in decided_speakers
                or run.duration < MIN_CLIP_SECONDS
                or _clip_overlaps_other_speaker(segments, run)
            ):
                continue
            key = (run.speaker_id, run.identity)
            if key not in best_run or run.duration > best_run[key].duration:
                best_run[key] = run

        unnamed = sorted(
            (run for (_, identity), run in best_run.items() if identity == 'none'),
            key=lambda run: talk.get(run.speaker_id, 0.0),
            reverse=True,
        )
        freshness = max(0.0, 1.0 - (now - started) / PROMPT_WINDOW) * 0.5
        title = ((conversation.get('structured') or {}).get('title') or '').strip()

        def add(
            run: _Run, kind: SpeakerTagPromptKind, origin: SpeakerTagPromptOrigin, score: float, **extra: Any
        ) -> None:
            pid = prompt_id(conversation_id, run.speaker_id, kind)
            if pid in answered:
                return
            clip_start, clip_end = _clip_window(run)
            if not prompt_window_covered(conversation, clip_start, clip_end):
                if on_skip:
                    on_skip('uncovered')
                return
            excerpt = ' '.join(
                (segment.get('text') or '').strip()
                for segment in segments
                if segment['id'] in run.segment_ids
                and float(segment.get('start') or 0) >= clip_start
                and float(segment.get('end') or 0) <= clip_end
            )
            prompt = SpeakerTagPrompt(
                id=pid,
                kind=kind,
                origin=origin,
                conversation_id=conversation_id,
                conversation_title=title,
                conversation_started_at=started,
                speaker_id=run.speaker_id,
                segment_ids=list(run.segment_ids),
                clip_start=round(clip_start, 3),
                clip_end=round(clip_end, 3),
                excerpt=_excerpt(excerpt),
                **extra,
            )
            expected_text = ' '.join(
                (segment.get('text') or '').strip()
                for segment in segments
                if segment['id'] in run.segment_ids
                and float(segment.get('start') or 0) < clip_end
                and float(segment.get('end') or 0) > clip_start
            ).strip()
            if expected_text:
                candidates.append(_Candidate(score + freshness, prompt, conversation, expected_text))

        for (_, identity), run in best_run.items():
            if identity == 'user':
                add(run, SpeakerTagPromptKind.owner_check, SpeakerTagPromptOrigin.auto_user, 2.0)
            elif identity.startswith('person:') and named_allowed:
                person_id = identity.split(':', 1)[1]
                if person_id in people:
                    add(
                        run,
                        SpeakerTagPromptKind.confirm_person,
                        SpeakerTagPromptOrigin.auto_person,
                        2.5,
                        suggested_person_id=person_id,
                        suggested_person_name=people[person_id],
                    )

        for rank, run in enumerate(unnamed):
            if rank == 0 and (not has_owner or not owner_has_voice):
                add(run, SpeakerTagPromptKind.owner_check, SpeakerTagPromptOrigin.unnamed, 3.0)
            elif named_allowed:
                suggestions = [pid for pid in recent_people if pid not in labeled_here][:MAX_SUGGESTED_PEOPLE]
                add(
                    run,
                    SpeakerTagPromptKind.identify,
                    SpeakerTagPromptOrigin.unnamed,
                    1.0 + min(talk.get(run.speaker_id, 0.0), 120.0) / 120.0,
                    suggested_person_ids=suggestions,
                )

    candidates.sort(key=lambda candidate: candidate.score, reverse=True)
    chosen: List[SpeakerTagPrompt] = []
    per_conversation: Counter = Counter()
    per_speaker: set = set()
    owner_checks = 0
    attempted = 0
    for candidate in candidates:
        prompt = candidate.prompt
        speaker_key = (prompt.conversation_id, prompt.speaker_id)
        if per_conversation[prompt.conversation_id] >= MAX_PER_CONVERSATION or speaker_key in per_speaker:
            continue
        if prompt.kind == SpeakerTagPromptKind.owner_check and owner_checks >= MAX_OWNER_CHECKS:
            continue
        if verify is not None:
            if attempted >= max_verifications:
                break
            attempted += 1
            if not verify(candidate.conversation, prompt, candidate.expected_text):
                continue
        if prompt.kind == SpeakerTagPromptKind.owner_check:
            owner_checks += 1
        chosen.append(prompt)
        per_conversation[prompt.conversation_id] += 1
        per_speaker.add(speaker_key)
        if len(chosen) >= limit:
            break
    return chosen
