"""Pure selection of a bounded daily set of speaker questions.

Owner checks use supplied pooled voice evidence nearest distance .50 and its
centroid representative, with one complete excerpt per conversation. Paid
person cards retain longest-run selection and the optional pinned prior.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import AbstractSet, Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from models.speaker_tag_prompts import (
    SpeakerTagCandidate,
    SpeakerTagPrompt,
    SpeakerTagPromptKind,
    SpeakerTagPromptOrigin,
)
from models.transcript_segment import legacy_conversation_segment_id
from utils.manual_speaker_assignments import manual_rejected_speakers
from utils.speaker_tag_prompts.coverage import prompt_window_covered
from utils.speaker_tag_prompts.owner_confirmation import (
    FIELD,
    MAX_SECONDS,
    MIN_SECONDS,
    StaleOwnerConfirmation,
    source_key,
    validate_window,
    label_identity,
    baseline_origin,
)

PROMPT_WINDOW = timedelta(hours=48)
MIN_CLIP_SECONDS = MIN_SECONDS
MAX_CLIP_SECONDS = MAX_SECONDS
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
    return label_identity(segment)


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
    speakers.update(str(speaker_id) for speaker_id in manual_rejected_speakers(receipt))
    segments = set(receipt.get('segments') or {})
    return speakers, segments


def _runs(segments: Sequence[Mapping[str, Any]], decided_segments: set, *, split_identity: bool = True) -> List[_Run]:
    """Maximal same-speaker, same-identity stretches with no other voice in between."""
    runs: List[_Run] = []
    current: List[Mapping[str, Any]] = []

    def flush() -> None:
        if current:
            runs.append(
                _Run(
                    speaker_id=current[0]['speaker_id'],
                    identity=(
                        _identity(current[0]) if len({_identity(segment) for segment in current}) == 1 else 'mixed'
                    ),
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
                or (split_identity and _identity(segment) != _identity(previous))
                or segment.get('speaker_id_scope') != previous.get('speaker_id_scope')
                or source_key(segment) != source_key(previous)
                or segment.get('audio_capture_run') != previous.get('audio_capture_run')
                or gap > MAX_GAP_SECONDS
            ):
                flush()
        current.append(segment)
    flush()
    return runs


def complete_owner_runs(conversation: Mapping[str, Any]) -> List[_Run]:
    """Partition eligible speech into complete, uncropped, source-consistent excerpts."""
    if conversation.get(FIELD):
        return []
    segments = _normalized_segments(conversation)
    speakers, decided = _manually_decided(conversation)
    by_id = {s['id']: s for s in segments}
    result = []
    for run in _runs(segments, decided, split_identity=False):
        if str(run.speaker_id) in speakers:
            continue
        current = []
        for sid in run.segment_ids:
            segment = by_id[sid]
            if current and float(segment.get('end') or 0) - float(current[0]['start']) > MAX_CLIP_SECONDS:
                current = []
            current.append(segment)
            start, end = float(current[0].get('start') or 0), float(segment.get('end') or 0)
            if end - start > MAX_CLIP_SECONDS:
                current = []
                continue
            if end - start < MIN_CLIP_SECONDS:
                continue
            ids = tuple(s['id'] for s in current)
            text = ' '.join((s.get('text') or '').strip() for s in current).strip()
            try:
                validate_window(conversation, ids, start, end)
            except StaleOwnerConfirmation:
                current = []
                continue
            if text:
                identities = {_identity(segment) for segment in current}
                identity = next(iter(identities)) if len(identities) == 1 else 'mixed'
                result.append(_Run(run.speaker_id, identity, ids, start, end, text))
            current = []
    return result


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


def run_voice_candidates(segments: Sequence[Mapping[str, Any]], segment_ids: Iterable[str]) -> Dict[str, dict]:
    """person_id -> best recorded voice candidate across a run's segments."""
    wanted = set(segment_ids)
    best: Dict[str, dict] = {}
    for segment in segments:
        if segment.get('id') not in wanted or not isinstance(segment.get('voice_candidates'), list):
            continue
        for entry in segment['voice_candidates']:
            if not isinstance(entry, Mapping) or not isinstance(entry.get('person_id'), str):
                continue
            level = entry.get('level')
            if isinstance(level, bool) or not isinstance(level, int) or not 1 <= level <= 3:
                continue
            current = best.setdefault(entry['person_id'], {'level': level, 'suggest': False})
            current['level'] = max(current['level'], level)
            current['suggest'] = current['suggest'] or entry.get('suggest') is True
    return best


def ranked_candidates(
    voice: Mapping[str, dict],
    recent: Sequence[str],
    *,
    people: Mapping[str, str],
    pinned: AbstractSet[str],
    exclude: AbstractSet[str],
) -> List[SpeakerTagCandidate]:
    """By voice match when recorded (pinned first within a level), then the rest by recency."""
    order = {person_id: index for index, person_id in enumerate(recent)}
    matched = sorted(
        (pid for pid in voice if pid in people and pid not in exclude),
        key=lambda pid: (-voice[pid]['level'], pid not in pinned, order.get(pid, len(order))),
    )
    rest = [pid for pid in recent if pid in people and pid not in exclude and pid not in voice]
    return [
        SpeakerTagCandidate(
            person_id=pid,
            name=people[pid],
            match_level=voice[pid]['level'] if pid in voice else None,
            pinned=pid in pinned,
        )
        for pid in (matched + rest)[:MAX_SUGGESTED_PEOPLE]
    ]


def select_prompts(
    conversations: Sequence[Mapping[str, Any]],
    *,
    now: datetime,
    owner_has_voice: bool,
    named_allowed: bool,
    answered: set,
    people: Mapping[str, str],
    limit: int = DEFAULT_LIMIT,
    pinned: AbstractSet[str] = frozenset(),
    ignored: AbstractSet[str] = frozenset(),
    prior_enabled: bool = False,
    verify: Optional[Callable[[Mapping[str, Any], SpeakerTagPrompt, str], bool]] = None,
    max_verifications: int = 4,
    on_skip: Optional[Callable[[str], None]] = None,
    owner_evidence: Optional[Callable[[Mapping[str, Any], List[_Run]], Optional[Tuple[_Run, float]]]] = None,
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
        labeled_here = {s['person_id'] for s in segments if s.get('person_id')}

        best_run: Dict[Tuple[int, str], _Run] = {}
        for run in _runs(segments, decided_segments):
            if (
                not run.text
                or f'{conversation_id}:{run.speaker_id}' in ignored
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
                clip_start=clip_start if kind == SpeakerTagPromptKind.owner_check else round(clip_start, 3),
                clip_end=clip_end if kind == SpeakerTagPromptKind.owner_check else round(clip_end, 3),
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

        if owner_has_voice and owner_evidence is not None:
            owner = owner_evidence(
                conversation,
                [
                    run
                    for run in complete_owner_runs(conversation)
                    if f'{conversation_id}:{run.speaker_id}' not in ignored
                ],
            )
            if owner is not None:
                run, distance = owner
                baseline = baseline_origin([segment for segment in segments if segment['id'] in run.segment_ids])
                # Mixed is a server quality category, not a released wire enum.
                origin = SpeakerTagPromptOrigin.unnamed if baseline == 'mixed' else SpeakerTagPromptOrigin(baseline)
                add(run, SpeakerTagPromptKind.owner_check, origin, 4.0 - abs(distance - 0.50))

        for (_, identity), run in best_run.items():
            if identity.startswith('person:') and named_allowed:
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

        for run in unnamed:
            voice = run_voice_candidates(segments, run.segment_ids) if prior_enabled else {}
            near = next(
                (pid for pid, entry in voice.items() if entry['suggest'] and pid in pinned and pid in people), None
            )
            if named_allowed and near is not None and near not in labeled_here:
                add(
                    run,
                    SpeakerTagPromptKind.confirm_person,
                    SpeakerTagPromptOrigin.unnamed,
                    2.5,
                    suggested_person_id=near,
                    suggested_person_name=people[near],
                )
            elif named_allowed:
                offered = ranked_candidates(voice, recent_people, people=people, pinned=pinned, exclude=labeled_here)
                add(
                    run,
                    SpeakerTagPromptKind.identify,
                    SpeakerTagPromptOrigin.unnamed,
                    1.0 + min(talk.get(run.speaker_id, 0.0), 120.0) / 120.0,
                    suggested_person_ids=[candidate.person_id for candidate in offered],
                    candidates=offered,
                )

    candidates.sort(key=lambda candidate: candidate.score, reverse=True)
    chosen: List[SpeakerTagPrompt] = []
    per_conversation: Counter = Counter()
    per_speaker: set = set()
    owner_checks = 0
    owner_conversations = set()
    attempted = 0
    for candidate in candidates:
        prompt = candidate.prompt
        speaker_key = (prompt.conversation_id, prompt.speaker_id)
        if per_conversation[prompt.conversation_id] >= MAX_PER_CONVERSATION or speaker_key in per_speaker:
            continue
        if prompt.kind == SpeakerTagPromptKind.owner_check and (
            owner_checks >= MAX_OWNER_CHECKS or prompt.conversation_id in owner_conversations
        ):
            continue
        if verify is not None:
            if attempted >= max_verifications:
                break
            attempted += 1
            if not verify(candidate.conversation, prompt, candidate.expected_text):
                continue
        if prompt.kind == SpeakerTagPromptKind.owner_check:
            owner_checks += 1
            owner_conversations.add(prompt.conversation_id)
        chosen.append(prompt)
        per_conversation[prompt.conversation_id] += 1
        per_speaker.add(speaker_key)
        if len(chosen) >= limit:
            break
    return chosen
