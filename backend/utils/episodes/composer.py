"""Episode composer: one strong summary per closed episode.

The live incremental notes (``incremental.py``) are a cheap preview written by a small
model that only sees a few minutes at a time. Once an episode is closed and every retained
member conversation has finished processing, the composer reads the members' own summaries
plus the episode's full transcript in one ``episode_composer`` call and replaces the
episode's title, notes and moments with a whole-episode summary and a handful of chapters.

It runs again when the episode's evidence changes (a late member finishes, sync upgrades a
transcript, a member is discarded): the ``composed_fingerprint`` over retained members and
their transcripts remains the composed-state stamp. A narrower speech/name/membership trigger
and a bounded background quiet window avoid paying for label-only updates. Kill switch: ``EPISODE_COMPOSER`` (on unless set off). Never
raises to callers.

``EPISODE_COMPOSER_THRIFT`` (on unless set off) keeps paid composes: a parse failure gets
one repair retry over the bad output alone, a short episode may ship a title and lede with no
chapters, a superseded result is stored and the episode marked pending, and paid failures stop
at two per evidence. Off restores the previous discard-and-retry behavior and the four-failure
cap. Every run and every paid call carries a bounded trigger label (close, read, member_final,
settle, repair).
repaired or synced more than ``EPISODE_LATE_COMPOSE_AFTER_HOURS`` (48h) after capture is
deferred: it keeps the first member's title and composes when its page is first opened
(``schedule_opened``), with a read-side grace exit. Kill switches: ``EPISODE_COMPOSER`` and
``EPISODE_COMPOSER_THRIFT`` (both on unless set off). Never raises to callers.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Callable, Mapping, Optional, Sequence, Union
from uuid import uuid4
from zoneinfo import ZoneInfo


from utils.conversations import phase_shadow

from config.episodes import (
    COMPOSER_FEATURE,
    COMPOSER_SETTLE_SECONDS,
    COMPOSER_MAX_SETTLE_SECONDS,
    episode_compose_settle_enabled,
    episode_compose_keep_paid_enabled,
    COMPOSER_LEASE_SECONDS,
    COMPOSER_CALL_BUDGET_SECONDS,
    COMPOSER_MAX_PAID_TURNS,
    COMPOSER_MAX_FAILURES,
    COMPOSER_MAX_PAID_FAILURES,
    COMPOSER_MAX_DETAILS,
    COMPOSER_MAX_PARAGRAPH_CHARS,
    COMPOSER_MAX_POINT_CHARS,
    COMPOSER_MAX_POINTS,
    COMPOSER_READ_THROTTLE_SECONDS,
    COMPOSER_RETRY_MINUTES,
    COMPOSER_MAX_CHAPTERS,
    COMPOSER_MAX_TRANSCRIPT_CHARS,
    COMPOSER_MIN_SECTION_SECONDS,
    COMPOSER_SHORT_EPISODE_SECONDS,
    COMPOSER_TIMEOUT_SECONDS,
    RECOVERY_NOTES_MIN_INTERVAL_SECONDS,
    COMPOSER_VERSION,
    episode_composer_enabled,
    episode_single_member_compose_enabled,
    episode_late_compose_after_hours,
    episode_late_compose_enabled,
    episode_late_compose_grace_hours,
)
from database import conversations as conversations_db
from database import episodes as episodes_db
from utils.conversations.recorded_time import conversation_span
from utils.episodes import metrics, policy
from utils.episodes.state import is_placeholder_heading, trim_text
from utils.episodes.visibility import hidden_member
from utils.speakers.display import sanitize_speaker_text
from utils.llm.clients import get_llm
from utils.llm.usage_tracker import track_usage
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

_DONE = {'completed'}
_TURN_SECONDS = 60
_TURN_GAP_SECONDS = 15
_WINDOW_SECONDS = 600
_CLOCK_SLACK_MINUTES = 2

_OUTPUT_RULES = """Return JSON only:
{{"title": "<= 7 words, specific to what happened",
 "emoji": "one emoji",
 "lede": "one or two sentences: what this stretch of the day was and what came out of it",
 "chapters": [{{"start": "HH:MM:SS", "end": "HH:MM:SS", "title": "<= 6 words",
   "points": [{{"text": "one specific point", "details": ["a supporting specific"]}}]}}],
 "follow_ups": ["a concrete next step someone committed to or clearly needs to take"],
 "people": ["names of people who mattered, only if named"]}}
chapters are the body of the page: 1 to {max_chapters} significant stretches in time order. start and end are the clock labels of the chapter's first and last transcript lines, copied exactly. Each chapter has 2 to 5 points; a point may carry 0 to 3 details. Points carry the substance the way good meeting notes do: names, numbers, product and feature names, the exact problem or idea, what was decided and why, open questions. Never repeat the lede inside a chapter. Attribute a statement, request or decision to a person only when the transcript makes the speaker clear; otherwise write it without a name.
Skip noise, background chatter, mumbling and filler entirely. Never write meta-commentary such as "no decision was recorded" or "nothing else was discussed": leave it out. Never write speaker labels or quote filler. Never title anything "New moment" or similar. follow_ups is empty when there are none."""

# The repair retry sees only the malformed reply, never the transcripts: the facts are
# already in the reply, and re-sending the episode would pay for the same input twice.
REPAIR_SYSTEM_PROMPT = """You repair a malformed JSON reply from an episode summarizer. Return JSON only, in exactly this shape:
{{"title": "<= 7 words", "emoji": "one emoji", "lede": "one or two sentences", "chapters": [{{"start": "HH:MM:SS", "end": "HH:MM:SS", "title": "<= 6 words", "points": [{{"text": "one specific point", "details": ["a supporting specific"]}}]}}], "follow_ups": ["a concrete next step"], "people": ["names of people who mattered"]}}
Keep every fact, name, number and clock label that is already in the reply. Do not invent anything. Use an empty list for a field the reply does not have. Return only the JSON object, with no prose and no code fence."""

SYSTEM_PROMPT = (
    """You write the page people read for an "episode": one continuous stretch of {owner}'s day captured by a wearable. It can span several recordings. {owner} is the wearer; call them {owner}, never "the user" or "someone".
You get each recording's existing summary and action items, and the full transcript (or its densest stretches when it is very long). The transcript is automatic and noisy: speaker labels can be wrong, and short fragments in other languages are usually mis-transcribed background noise. Use the summaries as a map and the transcript as the source of truth.
Write in {language}. """
    + _OUTPUT_RULES
)


class ComposeFailed(RuntimeError):
    pass


def _utc(value: Any) -> Optional[datetime]:
    return policy.utc(value)


def _retained_ids(episode: Mapping[str, Any]) -> list[str]:
    hidden = set(episode.get('discarded_conversation_ids') or []) | set(episode.get('duplicate_conversation_ids') or [])
    return [cid for cid in dict.fromkeys(episode.get('conversation_ids') or []) if cid and cid not in hidden]


def _segments(row: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        s for s in row.get('transcript_segments') or [] if isinstance(s, Mapping) and str(s.get('text') or '').strip()
    ]


def _span(row: Mapping[str, Any]) -> tuple[Optional[datetime], Optional[datetime]]:
    span = conversation_span(row)
    if span is not None:
        return span.recorded_start, span.recorded_end
    return _utc(row.get('started_at')) or _utc(row.get('created_at')), _utc(row.get('finished_at'))


def fingerprint(members: Sequence[Mapping[str, Any]]) -> str:
    """Changes when membership, any member's transcript text or timing, or its own summary changes."""
    parts = []
    for row in members:
        structured = row.get('structured') or {}
        items = [
            (item.get('description') if isinstance(item, Mapping) else str(item))
            for item in structured.get('action_items') or []
        ]
        speech = [
            (
                round(float(s.get('start') or 0), 1),
                str(s.get('text')).strip(),
                bool(s.get('is_user')),
                s.get('speaker'),
                s.get('person_id'),
                s.get('person_name'),
                s.get('id'),
                s.get('end'),
            )
            for s in _segments(row)
        ]
        evidence = json.dumps([structured, items, speech, _origin(row), _span(row)], default=str, ensure_ascii=False)
        parts.append([str(row.get('id')), hashlib.sha256(evidence.encode()).hexdigest()[:24]])
    raw = json.dumps([COMPOSER_VERSION, parts], separators=(',', ':'))
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def evidence_trigger(row: Mapping[str, Any]) -> str:
    """Only speech and resolved names buy a new compose; labels and summaries remain prompt inputs."""
    raw = json.dumps(
        [(str(s.get('text')).strip(), str(s.get('person_name') or '').strip()) for s in _segments(row)],
        ensure_ascii=False,
        separators=(',', ':'),
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _evidence(members: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    return {str(row['id']): evidence_trigger(row) for row in members}


def _trigger_unchanged(episode: Mapping[str, Any], evidence: Mapping[str, str]) -> bool:
    return (
        episode.get('composed_evidence') == evidence
        and episode.get('composed_membership') == sorted(_retained_ids(episode))
        and episode.get('composer_version') == COMPOSER_VERSION
        and episode.get('composed_notes') == notes_hash(episode)
        and not episode.get('summary_needs_regeneration')
    )


def notes_hash(state: Mapping[str, Any]) -> str:
    """Detects a later per-moment write (a closing tail, a sync replay) over composed notes."""
    raw = json.dumps(
        [state.get('title'), state.get('bullets'), [m.get('heading') for m in state.get('moments') or []]],
        default=str,
        ensure_ascii=False,
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _speaker(segment: Mapping[str, Any], owner: str) -> str:
    if segment.get('is_user'):
        return owner
    name = str(segment.get('person_name') or '').strip()
    if name:
        return name
    label = str(segment.get('speaker') or 'Someone').replace('SPEAKER_', 'Speaker ')
    return label


def _origin(row: Mapping[str, Any]) -> Optional[datetime]:
    """The instant a member's segment offsets count from."""
    return _utc(row.get('started_at')) or _span(row)[0]


def speech_times(row: Mapping[str, Any]) -> list[datetime]:
    """Every segment's start: moments end on speech, which a merged line's own clock would cut short."""
    origin = _origin(row) or datetime.now(timezone.utc)
    return [origin + timedelta(seconds=float(segment.get('start') or 0)) for segment in _segments(row)]


def transcript_lines(row: Mapping[str, Any], owner: str, tz: ZoneInfo) -> list[tuple[datetime, str]]:
    """One line per speaker turn: batch units cut speech every few seconds, and repeating the clock and
    the name on each fragment costs more tokens than the words. A turn still restarts each
    ``_TURN_SECONDS`` so a chapter can open inside a long monologue."""
    origin = _origin(row)
    out: list[tuple[datetime, str]] = []
    open_at, open_speaker, last_end, words = None, None, 0.0, []

    def close() -> None:
        if open_at is not None and words:
            local = open_at.astimezone(tz)
            out.append((open_at, f"[{local:%H:%M:%S}] {open_speaker}: {' '.join(words)}"))

    for segment in _segments(row):
        start = float(segment.get('start') or 0)
        at = (origin or datetime.now(timezone.utc)) + timedelta(seconds=start)
        speaker = _speaker(segment, owner)
        if (
            open_at is None
            or speaker != open_speaker
            or start - last_end > _TURN_GAP_SECONDS
            or (at - open_at).total_seconds() >= _TURN_SECONDS
        ):
            close()
            open_at, open_speaker, words = at, speaker, []
        words.append(str(segment.get('text')).strip())
        last_end = max(start, float(segment.get('end') or start))
    close()
    return out


def _fit(lines: list[tuple[datetime, str]], budget: int) -> list[str]:
    """Keep the densest 10-minute windows that fit, in time order, marking what was left out."""
    total = sum(len(text) + 1 for _, text in lines)
    if total <= budget:
        return [text for _, text in lines]
    windows: dict[int, list[tuple[datetime, str]]] = {}
    for at, text in lines:
        windows.setdefault(int(at.timestamp()) // _WINDOW_SECONDS, []).append((at, text))
    ranked = sorted(windows, key=lambda k: -sum(len(t) for _, t in windows[k]))
    keep, used = set(), 0
    for key in ranked:
        size = sum(len(t) + 1 for _, t in windows[key])
        if used + size > budget:
            continue
        keep.add(key)
        used += size
    out, skipped = [], 0
    for key in sorted(windows):
        if key in keep:
            if skipped:
                out.append(f'[... {skipped} quieter minutes left out ...]')
                skipped = 0
            out.extend(text for _, text in windows[key])
        else:
            skipped += _WINDOW_SECONDS // 60
    if skipped:
        out.append(f'[... {skipped} quieter minutes left out ...]')
    return out


def build_messages(
    members: Sequence[Mapping[str, Any]], *, owner: str, tz: ZoneInfo, language: str
) -> list[tuple[str, str]]:
    per_member = max(4000, COMPOSER_MAX_TRANSCRIPT_CHARS // max(1, len(members)))
    all_lines = [transcript_lines(row, owner, tz) for row in members]
    total = sum(len(t) + 1 for lines in all_lines for _, t in lines)
    blocks = []
    for index, (row, lines) in enumerate(zip(members, all_lines)):
        structured = row.get('structured') or {}
        start, end = _span(row)
        when = f'{start.astimezone(tz):%H:%M}-{end.astimezone(tz):%H:%M}' if start and end else 'time unknown'
        items = [
            (item.get('description') if isinstance(item, Mapping) else str(item))
            for item in structured.get('action_items') or []
        ]
        budget = COMPOSER_MAX_TRANSCRIPT_CHARS if total <= COMPOSER_MAX_TRANSCRIPT_CHARS else per_member
        text = '\n'.join(_fit(lines, budget)) or '(no speech)'
        blocks.append(
            f'=== Recording {index + 1} ({when}) ===\n'
            f'Existing summary title: {structured.get("title") or ""}\n'
            f'Existing summary: {structured.get("overview") or ""}\n'
            f'Existing action items: {json.dumps([i for i in items if i], ensure_ascii=False)}\n'
            f'Transcript:\n{text}'
        )
    system = SYSTEM_PROMPT.format(owner=owner, language=language, max_chapters=COMPOSER_MAX_CHAPTERS)
    return [('system', system), ('human', '\n\n'.join(blocks))]


def build_repair_messages(content: str) -> list[tuple[str, str]]:
    """The one repair retry: the bad output alone, never the transcripts."""
    return [('system', REPAIR_SYSTEM_PROMPT.format()), ('human', str(content or ''))]


def _content(reply: Any) -> str:
    content = getattr(reply, 'content', reply)
    if isinstance(content, list):
        content = ''.join(part.get('text', '') if isinstance(part, Mapping) else str(part) for part in content)
    return str(content)


def _recorded_seconds(members: Sequence[Mapping[str, Any]]) -> float:
    """Total recorded member time; a short episode may ship a lede with no chapters."""
    total = 0.0
    for row in members:
        start, end = _span(row)
        if start is not None and end is not None:
            total += max(0.0, (end - start).total_seconds())
    return total


def _short_episode(members: Sequence[Mapping[str, Any]]) -> bool:
    return (
        bool(members)
        and all(all(_span(row)) for row in members)
        and _recorded_seconds(members) <= COMPOSER_SHORT_EPISODE_SECONDS
    )


def parse(content: str) -> dict[str, Any]:
    match = re.search(r'\{.*\}', content or '', re.S)
    if not match:
        raise ComposeFailed('parse_error')
    try:
        data = json.loads(match.group(0))
    except ValueError as error:
        raise ComposeFailed('parse_error') from error
    if not isinstance(data, dict):
        raise ComposeFailed('parse_error')
    for key in ('lede', 'overview'):
        if isinstance(data.get(key), list):
            data[key] = ' '.join(str(part) for part in data[key] if str(part).strip())
    if not str(data.get('lede') or '').strip():
        data['lede'] = str(data.get('overview') or '').strip()
    for key in ('chapters', 'follow_ups', 'people'):
        if not isinstance(data.get(key), list):
            data[key] = []
    data['chapters'] = [chapter for chapter in data['chapters'] if isinstance(chapter, Mapping)]
    if not str(data.get('title') or '').strip() or not str(data.get('lede') or '').strip():
        raise ComposeFailed('parse_error')
    return data


def line_span(lines: Sequence[tuple[datetime, str]]) -> tuple[Optional[datetime], Optional[datetime]]:
    """The span the model saw: first and last transcript line clock, the same origin as the labels."""
    if not lines:
        return None, None
    return min(at for at, _ in lines), max(at for at, _ in lines)


def _clock(value: Any, lo: datetime, hi: datetime, tz: ZoneInfo) -> Optional[datetime]:
    """Resolve a local HH:MM[:SS] to an instant inside the episode's transcript span (two-minute slack)."""
    match = re.match(r'^\s*(\d{1,2}):(\d{2})(?::(\d{2}))?', str(value or ''))
    if not match:
        return None
    hour, minute, second = int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)
    if hour > 23 or minute > 59 or second > 59:
        return None
    slack = timedelta(minutes=_CLOCK_SLACK_MINUTES)
    floor = lo.replace(second=0, microsecond=0) - slack
    for day in sorted({lo.astimezone(tz).date() + timedelta(days=d) for d in (-1, 0, 1, 2)}):
        candidate = datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=tz).astimezone(timezone.utc)
        if floor <= candidate <= hi + slack:
            return candidate
    return None


def _speech_end(row: Mapping[str, Any]) -> Optional[datetime]:
    """When a member's last transcript segment ends, on the same clock as its lines."""
    origin, segments = _origin(row), _segments(row)
    if origin is None or not segments:
        return None
    return origin + timedelta(seconds=max(float(s.get('end') or s.get('start') or 0) for s in segments))


def _line(value: Any, limit: int) -> str:
    return trim_text(re.sub(r'\s+', ' ', sanitize_speaker_text(str(value or ''))).strip().strip('•-* ').strip(), limit)


def _points(chapter: Mapping[str, Any]) -> list[dict[str, Any]]:
    points = []
    raw_points = chapter.get('points')
    for raw in raw_points if isinstance(raw_points, list) else []:
        if isinstance(raw, Mapping):
            text, details = _line(raw.get('text'), COMPOSER_MAX_POINT_CHARS), raw.get('details')
            details = details if isinstance(details, list) else []
        else:
            text, details = _line(raw, COMPOSER_MAX_POINT_CHARS), []
        if not text:
            continue
        kept = [d for d in (_line(d, COMPOSER_MAX_POINT_CHARS) for d in details if not isinstance(d, Mapping)) if d]
        points.append({'text': text, 'details': kept[:COMPOSER_MAX_DETAILS]})
    if not points and str(chapter.get('summary') or '').strip():
        points.append({'text': _line(chapter.get('summary'), COMPOSER_MAX_POINT_CHARS), 'details': []})
    return points[:COMPOSER_MAX_POINTS]


def wire_points(value: Any) -> list[dict[str, Any]]:
    """The stored points of a moment as the client sees them; anything malformed is dropped."""
    out = []
    for point in value if isinstance(value, list) else []:
        if not isinstance(point, Mapping):
            continue
        text = _line(point.get('text'), COMPOSER_MAX_POINT_CHARS)
        raw = point.get('details')
        if text:
            details = [
                d for d in (_line(d, COMPOSER_MAX_POINT_CHARS) for d in (raw if isinstance(raw, list) else [])) if d
            ]
            out.append({'text': text, 'details': details[:COMPOSER_MAX_DETAILS]})
    return out[:COMPOSER_MAX_POINTS]


def to_updates(
    data: Mapping[str, Any],
    members: Sequence[Mapping[str, Any]],
    tz: ZoneInfo,
    spans: Optional[Sequence[tuple[str, Optional[datetime], Optional[datetime]]]] = None,
    times: Optional[Mapping[str, Sequence[datetime]]] = None,
) -> dict[str, Any]:
    """``spans`` are (member id, first line, last line) and ``times`` each member's line instants, on the
    transcript clock the model saw."""
    if times is None:
        times = {str(row.get('id')): speech_times(row) for row in members}
    if spans is None:
        spans = [(cid, min(ts), max(ts)) if ts else (cid, None, None) for cid, ts in times.items()]
    known: list[tuple[str, datetime, datetime]] = [
        (cid, a, b) for cid, a, b in spans if a is not None and b is not None
    ]
    origins = {str(row.get('id')): _origin(row) for row in members}
    speech_ends = {str(row.get('id')): _speech_end(row) for row in members}
    drafts = []
    if known:
        lo, hi = min(a for _, a, _ in known), max(b for _, _, b in known)
        for chapter in (data.get('chapters') or [])[:COMPOSER_MAX_CHAPTERS]:
            if not isinstance(chapter, Mapping):
                continue
            heading = _line(chapter.get('title'), 60)
            start = _clock(chapter.get('start'), lo, hi, tz)
            if not heading or is_placeholder_heading(heading) or start is None:
                continue
            owner = next(
                (cid for cid, a, b in known if a - timedelta(minutes=1) <= start <= b + timedelta(minutes=1)), None
            )
            if owner is None:
                at: datetime = start
                owner = min(
                    known, key=lambda s: min(abs((s[1] - at).total_seconds()), abs((s[2] - at).total_seconds()))
                )[0]
            drafts.append((start, _clock(chapter.get('end'), lo, hi, tz), owner, heading, _points(chapter)))
    drafts.sort(key=lambda d: d[0])
    moments = []
    for index, (start, end, owner, heading, points) in enumerate(drafts):
        following = drafts[index + 1][0] if index + 1 < len(drafts) else None
        if end is None or (end - start).total_seconds() < COMPOSER_MIN_SECTION_SECONDS:
            # The model's clocks are turn starts, so a section can read as seconds long. Its length
            # is then the last line it owns: before the next chapter, on its own recording.
            inside = [t for t in times.get(owner) or [] if t >= start and (following is None or t < following)]
            end = max(inside) if inside else start
        # The moment stays inside its own recording's speech, whose transcript it opens.
        limit = speech_ends.get(owner) or max(times.get(owner) or [start])
        start = min(start, limit)
        if end <= start:
            end = start + timedelta(seconds=30)
        end = max(start, min(end, limit))
        origin = origins.get(owner)
        moments.append(
            {
                'id': uuid4().hex[:12],
                'conversation_id': owner,
                'started_at': start,
                'ended_at': end,
                'start_offset': max(0.0, (start - origin).total_seconds()) if origin else 0.0,
                'end_offset': max(0.0, (end - origin).total_seconds()) if origin else 0.0,
                'heading': heading,
                'points': points,
                'composed': True,
            }
        )
    lede = _line(data.get('lede') or data.get('overview'), COMPOSER_MAX_PARAGRAPH_CHARS)
    follow_ups = [f for f in (_line(f, COMPOSER_MAX_POINT_CHARS) for f in data.get('follow_ups') or []) if f][:8]
    people = [_line(p, 60) for p in data.get('people') or [] if _line(p, 60)][:12]
    activity = {str(row.get('id')): end for row in members if (end := _span(row)[1])}
    updates: dict[str, Any] = {
        'title': _line(data.get('title'), 80),
        # Released clients read bullets; the lede is the one-paragraph summary they show.
        'bullets': [lede] if lede else [],
        'lede': lede,
        'follow_ups': follow_ups,
        'moments': moments,
        'people': people,
        'open_questions': [],
    }
    emoji = str(data.get('emoji') or '').strip()
    if emoji:
        updates['emoji'] = emoji.split()[0][:16]
    if activity:
        updates['member_activity'] = activity
    return updates


_BULLET_LINE = re.compile(r'^(\s*)(?:[-*+•]|\d+[.)])\s+(.*)$')


def _markdown_points(body: Any) -> list[dict[str, Any]]:
    """A section body as the episode page's points: top-level bullets, nested details, prose paragraphs."""
    points: list[dict[str, Any]] = []
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            text = _line(' '.join(paragraph), COMPOSER_MAX_POINT_CHARS)
            if text:
                points.append({'text': text, 'details': []})
            paragraph.clear()

    for raw in str(body or '').splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith('#'):
            flush()
            continue
        match = _BULLET_LINE.match(line)
        if match is None:
            paragraph.append(line.strip())
            continue
        flush()
        text = _line(match.group(2), COMPOSER_MAX_POINT_CHARS)
        if not text:
            continue
        if match.group(1) and points:
            points[-1]['details'].append(text)
        else:
            points.append({'text': text, 'details': []})
    flush()
    for point in points:
        point['details'] = point['details'][:COMPOSER_MAX_DETAILS]
    return points[:COMPOSER_MAX_POINTS]


def _section_offsets(member: Mapping[str, Any], sections: Sequence[Mapping[str, Any]]) -> list[tuple[float, float]]:
    """Each section's (start, end) seconds into its conversation, from its cited segments.

    A section with no usable citation inherits the gap between its neighbours, so the
    sections partition the conversation once instead of overlapping or inventing time.
    """
    segments = _segments(member)
    by_id = {str(segment.get('id')): segment for segment in segments if segment.get('id')}
    total = max((float(segment.get('end') or segment.get('start') or 0) for segment in segments), default=0.0)
    known: list[Optional[tuple[float, float]]] = []
    for section in sections:
        cited = [by_id[str(sid)] for sid in section.get('source_segment_ids') or [] if str(sid) in by_id]
        if cited:
            known.append(
                (
                    min(float(segment.get('start') or 0) for segment in cited),
                    max(float(segment.get('end') or segment.get('start') or 0) for segment in cited),
                )
            )
        else:
            known.append(None)
    if not any(known):
        # No citations at all: split the conversation evenly so the sections still read in order.
        step = total / len(sections) if sections else 0.0
        return [(index * step, (index + 1) * step) for index in range(len(sections))]
    next_start = [total] * len(sections)
    upcoming = total
    for index in reversed(range(len(sections))):
        next_start[index] = upcoming
        interval = known[index]
        if interval is not None:
            upcoming = interval[0]
    offsets: list[tuple[float, float]] = []
    previous_end = 0.0
    for index, interval in enumerate(known):
        start, end = interval if interval is not None else (previous_end, next_start[index])
        start = max(0.0, min(float(start), total))
        end = max(start, min(float(end), total))
        if end <= start:
            end = min(total, start + 30.0) if total > start else start + 30.0
        offsets.append((start, end))
        previous_end = end
    return offsets


def has_notes(member: Mapping[str, Any]) -> bool:
    """Whether a member's own notes can stand in for a composed episode."""
    return _readable_body(single_member_updates(member))


def _readable_body(state: Mapping[str, Any]) -> bool:
    return bool(str(state.get('lede') or '').strip() or any(m.get('points') for m in state.get('moments') or []))


def single_member_updates(member: Mapping[str, Any]) -> dict[str, Any]:
    """A one-conversation episode from that conversation's own notes: no model call.

    The episode page and the conversation detail must agree, so the mapping is explicit:
    title and emoji from the notes, the lede from the gist (or the overview when the notes
    have no sections), one chapter per section with its bullets as points, follow-ups from
    the open action items, and people from the participants.
    """
    structured = member.get('structured') or {}
    sections = [section for section in structured.get('sections') or [] if isinstance(section, Mapping)]
    cid = str(member.get('id'))
    origin = _origin(member)
    span_start, span_end = _span(member)
    moments = []
    for section, (start, end) in zip(sections, _section_offsets(member, sections)):
        heading = _line(section.get('heading'), 60)
        points = _markdown_points(section.get('body_markdown'))
        if not heading and not points:
            continue
        started = origin + timedelta(seconds=start) if origin else span_start
        ended = origin + timedelta(seconds=end) if origin else span_end
        if started is None or ended is None:
            continue
        moments.append(
            {
                'id': uuid4().hex[:12],
                'conversation_id': cid,
                'started_at': started,
                'ended_at': ended,
                'start_offset': start,
                'end_offset': end,
                'heading': heading,
                'points': points,
                'composed': True,
            }
        )
    gist = _line(structured.get('gist'), COMPOSER_MAX_PARAGRAPH_CHARS)
    # The overview is the section render whenever sections exist, so it is only a lede
    # when there is nothing else to read; otherwise the gist is the one-line lede.
    lede = gist or ('' if sections else _line(structured.get('overview'), COMPOSER_MAX_PARAGRAPH_CHARS))
    follow_ups = [
        text
        for item in structured.get('action_items') or []
        if isinstance(item, Mapping) and not item.get('completed')
        for text in [_line(item.get('description'), COMPOSER_MAX_POINT_CHARS)]
        if text
    ][:8]
    people = [
        name
        for person in structured.get('participants') or []
        if isinstance(person, Mapping)
        for name in [_line(person.get('name'), 60)]
        if name
    ][:12]
    updates: dict[str, Any] = {
        'title': _line(structured.get('title'), 80),
        'bullets': [lede] if lede else [],
        'lede': lede,
        'follow_ups': follow_ups,
        'moments': moments,
        'people': people,
        'open_questions': [],
    }
    emoji = str(structured.get('emoji') or '').strip()
    if emoji:
        updates['emoji'] = emoji.split()[0][:16]
    if span_end is not None:
        updates['member_activity'] = {cid: span_end}
    return updates


def invoke_model(uid: str, messages: list[Any], *, tools: Optional[list[dict[str, Any]]] = None) -> Any:
    with track_usage(uid, COMPOSER_FEATURE):
        llm = get_llm('episode_composer', uid=uid, request_timeout=COMPOSER_TIMEOUT_SECONDS, max_retries=1)
        if tools:
            llm = llm.bind(tools=tools)
        return llm.invoke(messages)


def _usage(reply: Any) -> tuple[int, int]:
    meta = getattr(reply, 'usage_metadata', None) or {}
    return int(meta.get('input_tokens') or 0), int(meta.get('output_tokens') or 0)


def compose(
    uid: str,
    episode_id: str,
    *,
    collaborators: Any = None,
    force: bool = False,
    background: bool = False,
    trigger: str = 'close',
) -> str:
    """Compose a closed episode once its members are done. Returns an outcome label; never raises."""
    if not episode_composer_enabled():
        return 'disabled'
    from utils.episodes import metrics
    from utils.episodes import service

    c = collaborators or service.Collaborators()
    started = time.monotonic()
    try:
        outcome = _compose(uid, episode_id, c, force=force, background=background, service=service, trigger=trigger)
    except Exception as error:  # Never break finalization or reads.
        logger.warning('event=episode_compose outcome=error exception_type=%s', type(error).__name__)
        outcome = 'error'
    metrics.record_compose(outcome, time.monotonic() - started, trigger=trigger)
    return outcome


def _named(uid: str, row: Mapping[str, Any], c: Any) -> list[dict[str, Any]]:
    """Segments with stored person names, so a rename changes the evidence fingerprint too."""
    from utils.episodes import service

    owner: Any = service  # the same seam the live notes use (people lookup, owner gate)
    return owner._named_segments(uid, _segments(row), c)


def _members(
    uid: str,
    episode: Mapping[str, Any],
    c: Any,
    *,
    revisions: Optional[dict[str, Optional[datetime]]] = None,
) -> tuple[str, list[dict[str, Any]]]:
    """('ok' | 'waiting', retained visible members sorted by start)."""
    members = []
    for cid in _retained_ids(episode):
        row = conversations_db.get_conversation(uid, cid, firestore_client=c.firestore_client)
        if revisions is not None:
            # get_conversation carries the snapshot's canonical update_time in
            # updated_at, including after decoding and Home projection.
            revisions[cid] = row.get('updated_at') if row else None
        if not row or hidden_member(row) or not conversations_db.is_visible_conversation(row):
            continue
        if str(row.get('status') or '') not in _DONE:
            return 'waiting', []
        members.append({**row, 'id': cid, 'transcript_segments': _named(uid, row, c)})
    members.sort(key=lambda row: _span(row)[0] or datetime.max.replace(tzinfo=timezone.utc))
    return 'ok', members


_Updates = Union[Mapping[str, Any], Callable[[Mapping[str, Any]], Mapping[str, Any]]]


def _write(
    uid: str,
    episode_id: str,
    c: Any,
    updates: _Updates,
    *,
    guard: Optional[Callable[[Mapping[str, Any]], Optional[str]]] = None,
    expected_member_revisions: Optional[Mapping[str, Optional[datetime]]] = None,
) -> str:
    """CAS write with bounded retries. ``guard(current)`` returns an outcome to stop, or None."""
    outcome = 'conflict'
    for _attempt in range(3):
        current = episodes_db.get_episode(uid, episode_id, firestore_client=c.firestore_client)
        if not current:
            return 'no_episode'
        if policy.is_live(current):
            return 'live'
        stop = guard(current) if guard else None
        if stop:
            return stop
        payload = dict(updates(current) if callable(updates) else updates)
        try:
            episodes_db.update_episode(
                uid,
                episode_id,
                expected_version=int(current.get('state_version') or 0),
                updates=payload,
                firestore_client=c.firestore_client,
                expected_member_revisions=expected_member_revisions,
            )
            return 'written'
        except episodes_db.EpisodeConflict as error:
            if str(error) == 'member_revision_changed':
                # The normal recompute path will pick up the new evidence. Do
                # not retry the stale payload or the window-only fallback.
                return 'superseded'
            outcome = 'conflict' if str(error) == 'state_version_changed' else 'refused'
    return outcome


def _record_failure(
    uid: str, episode_id: str, c: Any, print_: str, *, count: int = 1, lease_token: str | None = None
) -> None:
    """Back off after failed paid attempts. The count is per evidence: new evidence starts at one.

    ``count`` is the number of paid calls this attempt burned (a parse failure plus its
    repair retry is two), so the cap counts money, not compose runs.
    """
    try:
        _write(
            uid,
            episode_id,
            c,
            lambda current: {
                'compose_failures': (
                    int(current.get('compose_failures') or 0) + count
                    if current.get('compose_failed_fingerprint') == print_
                    else count
                ),
                'compose_failed_fingerprint': print_,
                'compose_failed_at': datetime.now(timezone.utc),
                **_release(current, print_, lease_token),
            },
            guard=lambda current: (
                'superseded'
                if lease_token is not None and (current.get('compose_lease') or {}).get('token') != lease_token
                else None
            ),
        )
    except Exception:
        pass


def _release(current: Mapping[str, Any], print_: str, lease_token: str | None = None) -> dict[str, Any]:
    """Clear the lease only if it is still ours; a newer compose's lease stays."""
    lease = current.get('compose_lease')
    return (
        {'compose_lease': None}
        if isinstance(lease, Mapping)
        and lease.get('fingerprint') == print_
        and (lease_token is None or lease.get('token') == lease_token)
        else {}
    )


def _max_failures() -> int:
    """Paid failures allowed on one evidence: two with keep-paid on, the legacy four off."""
    return COMPOSER_MAX_PAID_FAILURES if episode_compose_keep_paid_enabled() else COMPOSER_MAX_FAILURES


def _backed_off(episode: Mapping[str, Any], print_: Optional[str] = None) -> bool:
    """Failed paid attempts on the same evidence back off 10/20/40 min, then stop until it changes."""
    failures = int(episode.get('compose_failures') or 0)
    if not failures:
        return False
    if print_ is not None and episode.get('compose_failed_fingerprint') != print_:
        return False
    if failures >= _max_failures():
        return True
    failed_at = _utc(episode.get('compose_failed_at'))
    backoff = timedelta(minutes=COMPOSER_RETRY_MINUTES * (2 ** (failures - 1)))
    return bool(failed_at and datetime.now(timezone.utc) - failed_at < backoff)


# --------------------------------------------------------------------------- late composes
#
# A recording repaired or synced more than ``EPISODE_LATE_COMPOSE_AFTER_HOURS`` (48h)
# after capture is "late". Repair waves deliver members hours apart, so composing at
# finalize pays once per arrival for an episode nobody is looking at. A late episode
# instead keeps the first member's title and composes when its page is first opened
# (``schedule_opened``). Two exits keep it from waiting forever: the read-side safety
# net composes it after ``EPISODE_LATE_COMPOSE_GRACE_HOURS`` (7 days), and
# ``EPISODE_COMPOSER_THRIFT`` off restores composing at finalize.


def is_late(episode: Mapping[str, Any], *, now: Optional[datetime] = None) -> bool:
    """Whether the capture is older than the late threshold at this moment."""
    started = _utc(episode.get('started_at'))
    if started is None:
        return False
    at = now or datetime.now(timezone.utc)
    return (at - started).total_seconds() > episode_late_compose_after_hours() * 3600


def is_deferred(episode: Optional[Mapping[str, Any]]) -> bool:
    """Whether this episode is waiting for its first open instead of composing at finalize."""
    return bool(episode and episode.get('compose_deferred_at'))


def _opened_deferral(episode: Mapping[str, Any]) -> bool:
    at = _utc(episode.get('compose_deferred_at'))
    return at is not None and _utc(episode.get('compose_opened_deferred_at')) == at


def _deferred_within_grace(episode: Mapping[str, Any], *, now: Optional[datetime] = None) -> bool:
    """A deferred episode the read-side safety net must leave alone until the grace window ends."""
    at = _utc(episode.get('compose_deferred_at'))
    if at is None or _opened_deferral(episode):
        return False
    current = now or datetime.now(timezone.utc)
    return (current - at).total_seconds() < episode_late_compose_grace_hours() * 3600


def _first_member_title(uid: str, episode: Mapping[str, Any], c: Any) -> str:
    """The first retained, visible member's own summary title: the row's title until composed."""
    for cid in _retained_ids(episode):
        row = conversations_db.get_conversation(uid, cid, firestore_client=getattr(c, 'firestore_client', None))
        if not row or hidden_member(row) or not conversations_db.is_visible_conversation(row):
            continue
        title = str((row.get('structured') or {}).get('title') or '').strip()
        if title:
            return title
    return ''


def defer_late_compose(uid: str, episode: Mapping[str, Any], c: Any) -> bool:
    """Defer a late episode's compose to its first open. Returns whether it is deferred.

    A failed stamp falls through to today's behavior (compose at finalize), so a write
    fault never strands an episode's notes.
    """
    if not episode_late_compose_enabled() or not episode_composer_enabled():
        return False
    if not is_late(episode):
        return False
    if episode.get('composed_fingerprint') and not needs_compose(episode, opened=True):
        return False
    if is_deferred(episode):
        return not _opened_deferral(episode)
    title = _first_member_title(uid, episode, c)
    now = datetime.now(timezone.utc)
    # A composed episode keeps its composed title; only an uncomposed row falls back.
    fallback = title if title and not episode.get('composed_fingerprint') else ''

    def stamp(current: Mapping[str, Any]) -> dict[str, Any]:
        return {
            'compose_deferred_at': now,
            'compose_opened_deferred_at': None,
            # The row reads as the first member's summary until the composer replaces it.
            **({'title': fallback} if fallback else {}),
        }

    try:
        result = _write(
            uid,
            str(episode['id']),
            c,
            stamp,
            guard=lambda current: (
                'unchanged' if current.get('composed_fingerprint') != episode.get('composed_fingerprint') else None
            ),
        )
    except Exception as error:
        logger.warning('event=episode_compose_defer outcome=error exception_type=%s', type(error).__name__)
        record_fallback(
            component='conversation_notes',
            from_mode='episode_compose_deferred',
            to_mode='episode_compose_immediate',
            reason='enqueue_failed',
            outcome='degraded',
            log=logger,
        )
        return False
    if result != 'written':
        return False
    metrics.record_compose_trigger_skipped('late_deferred')
    return True


def schedule_after_close(
    uid: str,
    episode_id: str,
    *,
    episode: Optional[Mapping[str, Any]] = None,
    collaborators: Any = None,
    trigger: str = 'close',
) -> bool:
    """Close/finalize scheduling: a late episode waits for its first open instead."""
    if not episode_id:
        return False
    if episode_late_compose_enabled() and episode_composer_enabled():
        c = collaborators or SimpleNamespace(firestore_client=None)
        try:
            row = episode or episodes_db.get_episode(
                uid, str(episode_id), firestore_client=getattr(c, 'firestore_client', None)
            )
            if row and not policy.is_live(row) and defer_late_compose(uid, row, c):
                return False
        except Exception as error:
            logger.warning('event=episode_compose_defer outcome=error exception_type=%s', type(error).__name__)
    return schedule(uid, episode_id, collaborators=collaborators, trigger=trigger)


def schedule_opened(uid: str, episode: Optional[Mapping[str, Any]], *, collaborators: Any = None) -> bool:
    """The episode page was opened: a deferred late episode composes now, at most once per window."""
    if not episode_late_compose_enabled() or not is_deferred(episode) or not episode or policy.is_live(episode):
        return False
    if not needs_compose(episode, opened=True):
        return False
    # Remember the deferral epoch that the user opened. A member finishing after
    # the bounded client poll must still schedule normally, even on another replica.
    if not _opened_deferral(episode):
        try:
            c = collaborators or SimpleNamespace(firestore_client=None)
            _write(
                uid,
                str(episode['id']),
                c,
                {'compose_opened_deferred_at': episode['compose_deferred_at']},
                guard=lambda current: (
                    'superseded' if current.get('compose_deferred_at') != episode['compose_deferred_at'] else None
                ),
            )
        except Exception as error:
            logger.warning('event=episode_compose_open_stamp outcome=error exception_type=%s', type(error).__name__)
            record_fallback(
                component='conversation_notes',
                from_mode='episode_compose_deferred',
                to_mode='episode_compose_immediate',
                reason='enqueue_failed',
                outcome='degraded',
                log=logger,
            )
    return schedule(uid, str(episode['id']), collaborators=collaborators, throttle=True, trigger='read')


def _write_single_member(
    uid: str,
    episode_id: str,
    c: Any,
    episode: Mapping[str, Any],
    members: Sequence[Mapping[str, Any]],
    print_: str,
    member_ids: list[str],
    member_revisions: Mapping[str, Optional[datetime]],
) -> str:
    """Persist the code-built notes for a one-conversation episode. Never raises to callers."""
    composed = single_member_updates(members[0])

    def finish(current: Mapping[str, Any]) -> dict[str, Any]:
        return {
            **composed,
            'composed_fingerprint': print_,
            'composed_member_ids': member_ids,
            **_trigger_stamp(episode, members),
            'composed_notes': notes_hash(composed),
            'composed_at': datetime.now(timezone.utc),
            'composer_version': COMPOSER_VERSION,
            'summary_needs_regeneration': False,
            'compose_failures': 0,
            'compose_deferred_at': None,
        }

    def guard(current: Mapping[str, Any]) -> Optional[str]:
        return 'superseded' if current.get('state_version') != episode.get('state_version') else None

    written = _write(uid, episode_id, c, finish, guard=guard, expected_member_revisions=member_revisions)
    if written == 'refused':
        # Older data can refuse a window change: keep the notes on the window it already has.
        written = _write(
            uid,
            episode_id,
            c,
            lambda current: {k: v for k, v in finish(current).items() if k != 'member_activity'},
            guard=guard,
            expected_member_revisions=member_revisions,
        )
    if written == 'written':
        return 'composed_single'
    return written if written in {'live', 'no_episode', 'conflict', 'refused', 'superseded'} else 'conflict'


def _compose(
    uid: str, episode_id: str, c: Any, *, force: bool, background: bool, service: Any, trigger: str = 'close'
) -> str:
    episode = episodes_db.get_episode(uid, episode_id, firestore_client=c.firestore_client)
    if not episode:
        return 'no_episode'
    if policy.is_live(episode):
        return 'live'
    member_revisions: dict[str, Optional[datetime]] = {}
    state, members = _members(uid, episode, c, revisions=member_revisions)
    if state == 'waiting':
        return 'waiting'
    member_ids = sorted(str(row['id']) for row in members)
    if not members or not any(_segments(row) for row in members):
        # Nothing to say: clear notes that may describe a member since hidden, and stamp it so
        # neither reads nor finalizers keep retrying.
        cleared = {
            'title': '',
            'bullets': [],
            'lede': '',
            'follow_ups': [],
            'moments': [],
            'people': [],
            'open_questions': [],
        }
        stamp = {
            **cleared,
            'composed_fingerprint': fingerprint(members),
            'composed_member_ids': member_ids,
            **_trigger_stamp(episode, members),
            'composed_notes': notes_hash(cleared),
            'composer_version': COMPOSER_VERSION,
            'summary_needs_regeneration': False,
            'compose_deferred_at': None,
        }
        written = _write(
            uid,
            episode_id,
            c,
            stamp,
            guard=lambda current: (
                'superseded' if current.get('state_version') != episode.get('state_version') else None
            ),
            expected_member_revisions=member_revisions,
        )
        return 'empty' if written == 'written' else written
    print_ = fingerprint(members)
    single = episode_single_member_compose_enabled() and len(members) == 1
    if (
        episode_compose_settle_enabled()
        and not force
        and _trigger_unchanged(episode, _evidence(members))
        and _readable_body(episode)
        and (not single or episode.get('composed_fingerprint') == print_)
    ):
        metrics.record_compose_trigger_skipped('evidence_unchanged')
        if episode.get('compose_pending_since'):
            _write(uid, episode_id, c, _trigger_stamp(episode, members))
        return 'unchanged'
    if (
        not force
        and episode.get('composed_fingerprint') == print_
        and episode.get('composed_notes') == notes_hash(episode)
        and not episode.get('summary_needs_regeneration')
        and _readable_body(episode)
    ):
        if episode.get('compose_pending_since') or (
            episode_compose_settle_enabled() and episode.get('composed_evidence') is None
        ):
            _write(uid, episode_id, c, _trigger_stamp(episode, members))
        return 'unchanged'
    if single and has_notes(members[0]):
        # No model call, so no lease, settle window or failure backoff: the notes are already paid for.
        return _write_single_member(uid, episode_id, c, episode, members, print_, member_ids, member_revisions)
    if not force and _backed_off(episode, print_):
        return 'backoff'
    if episode_compose_settle_enabled() and background and not force:
        observed = _observe_evidence(uid, episode, c, _evidence(members))
        if observed is not None:
            episode = observed
            delay = settle_delay(episode)
            if delay > 0:
                if _defer(uid, episode_id, c, delay):
                    return 'settling'
                # Pending evidence is already persisted. Preserve progress when the queue is full
                # by using the normal immediate compose path, including its paid-once lease.
                record_fallback(
                    component='conversation_notes',
                    from_mode='episode_compose_settling',
                    to_mode='episode_compose_immediate',
                    reason='capacity_full',
                    outcome='degraded',
                    log=logger,
                )
    invoke = (c.extras or {}).get('compose_invoke')
    if invoke is None and getattr(c, 'invoke', None) is not None:
        # Collaborators that fake the incremental model never reach the real composer model.
        return 'disabled'
    invoke = invoke or invoke_model

    # One paid call per evidence across replicas: claim a short lease for this fingerprint.
    now = datetime.now(timezone.utc)
    lease_token = uuid4().hex
    lease_until = now + timedelta(seconds=COMPOSER_LEASE_SECONDS)

    def lease_guard(current: Mapping[str, Any]) -> Optional[str]:
        lease = current.get('compose_lease') or {}
        until = _utc(lease.get('until')) if isinstance(lease, Mapping) else None
        if until and until > now and lease.get('fingerprint') == print_ and not force:
            return 'leased'
        if (
            current.get('composed_fingerprint') == print_
            and current.get('composed_notes') == notes_hash(current)
            and _readable_body(current)
        ):
            return 'unchanged' if not force else None
        return None

    claimed = _write(
        uid,
        episode_id,
        c,
        {'compose_lease': {'fingerprint': print_, 'token': lease_token, 'until': lease_until}},
        guard=lease_guard,
    )
    if claimed != 'written':
        return claimed if claimed in {'leased', 'unchanged', 'live', 'no_episode', 'conflict'} else 'conflict'

    try:
        tz = ZoneInfo(service._tz(uid, c))
    except Exception:
        tz = ZoneInfo('UTC')
    owner = service._owner_name(uid, c)
    named = members  # already carry stored person names (``_members``)
    language = str(episode.get('output_language') or 'English')
    language = {'en': 'English'}.get(language, language)
    mode = 'full'
    keep_paid = episode_compose_keep_paid_enabled()
    call_started = datetime.now(timezone.utc)
    input_tokens = output_tokens = tool_calls = paid_calls = 0
    repaired = False

    def call(payload: list[Any], **kwargs: Any) -> Any:
        nonlocal input_tokens, output_tokens, paid_calls
        # Do not start a turn unless both provider attempts fit inside our claim.
        if (
            paid_calls >= COMPOSER_MAX_PAID_TURNS
            or datetime.now(timezone.utc) + timedelta(seconds=COMPOSER_CALL_BUDGET_SECONDS) > lease_until
        ):
            raise ComposeFailed('compose_deadline')
        current = episodes_db.get_episode(uid, episode_id, firestore_client=c.firestore_client) or {}
        if (current.get('compose_lease') or {}).get('token') != lease_token:
            raise ComposeFailed('lease_lost')
        paid_calls += 1
        reply_ = invoke(uid, payload, **kwargs)
        call_input, call_output = _usage(reply_)
        input_tokens += call_input
        output_tokens += call_output
        metrics.record_compose_reply(mode, call_input, call_output)
        return reply_

    def parse_or_repair(reply_: Any) -> dict[str, Any]:
        nonlocal repaired
        content = _content(reply_)
        try:
            return parse(content)
        except ComposeFailed as error:
            if not keep_paid or str(error) != 'parse_error':
                raise
            metrics.record_compose_call(trigger, 'parse_error')
            repaired = True
            return parse(_content(call(build_repair_messages(content))))

    try:
        reply = call(build_messages(named, owner=owner, tz=tz, language=language))
        data = parse_or_repair(reply)
        metrics.record_compose_tools(mode, tool_calls)
        times = {str(row['id']): speech_times(row) for row in members}
        spans = [(cid, min(ts), max(ts)) if ts else (cid, None, None) for cid, ts in times.items()]
        composed = to_updates(data, members, tz, spans, times)
        if not any(m['points'] for m in composed['moments']):
            if not (keep_paid and _short_episode(members)):
                # Speech was there: a page with no sections is a failed compose, unless the
                # episode is short enough that the lede is the whole page.
                raise ComposeFailed('no_sections')
    except ComposeFailed as error:
        metrics.record_compose_call('repair' if repaired else trigger, str(error))
        _record_failure(uid, episode_id, c, print_, count=max(1, paid_calls), lease_token=lease_token)
        raise
    except Exception:
        metrics.record_compose_call('repair' if repaired else trigger, 'error')
        _record_failure(uid, episode_id, c, print_, count=max(1, paid_calls), lease_token=lease_token)
        raise
    metrics.record_compose_call('repair' if repaired else trigger, 'ok')

    # The model call took seconds: re-read the evidence. A discard, a transcript upgrade or a
    # membership change since then makes this result stale; its own trigger composes again.
    fresh_episode = episodes_db.get_episode(uid, episode_id, firestore_client=c.firestore_client) or episode
    fresh_revisions: dict[str, Optional[datetime]] = {}
    fresh_state, fresh = _members(uid, fresh_episode, c, revisions=fresh_revisions)
    superseded = fresh_state != 'ok' or fingerprint(fresh) != print_
    member_changed = bool(set(member_ids) - set(_retained_ids(fresh_episode)))
    # Waiting members collapse _members to []; check visibility of the original
    # paid set separately so an actual removal/hidden member still cannot leak.
    for cid in member_ids:
        row = conversations_db.get_conversation(uid, cid, firestore_client=c.firestore_client)
        # Preserve the fingerprint snapshot's revisions; never adopt later reads.
        if (
            not row
            or cid not in fresh_revisions
            or row.get('updated_at') != fresh_revisions[cid]
            or hidden_member(row)
            or not conversations_db.is_visible_conversation(row)
        ):
            member_changed = True
    if member_changed or (superseded and not keep_paid):
        _write(uid, episode_id, c, lambda current: _release(current, print_, lease_token))
        return 'superseded'

    kept_pending = {'value': superseded}

    def finish(current: Mapping[str, Any]) -> dict[str, Any]:
        usage = dict(current.get('usage') or {})
        usage['composer_calls'] = int(usage.get('composer_calls') or 0) + paid_calls
        usage['composer_input_tokens'] = int(usage.get('composer_input_tokens') or 0) + input_tokens
        usage['composer_output_tokens'] = int(usage.get('composer_output_tokens') or 0) + output_tokens
        usage['composer_tool_calls'] = int(usage.get('composer_tool_calls') or 0) + tool_calls
        payload = {
            **composed,
            'usage': usage,
            'composed_fingerprint': print_,
            'composed_member_ids': member_ids,
            **_trigger_stamp(episode, members),
            'composed_notes': notes_hash(composed),
            'composed_at': datetime.now(timezone.utc),
            'composer_version': COMPOSER_VERSION,
            'summary_needs_regeneration': False,
            'compose_failures': 0,
            # The deferral is one-shot: a later arrival defers again on its own.
            'compose_deferred_at': None,
            **_release(current, print_, lease_token),
        }
        membership_changed = sorted(_retained_ids(current)) != sorted(_retained_ids(episode))
        if superseded or membership_changed:
            # Keep the paid result and mark the episode pending: a settled compose refreshes it
            # with the evidence that arrived during the call instead of throwing this one away.
            kept_pending['value'] = True
            payload['compose_pending_since'] = call_started
            payload['compose_activity_at'] = call_started
            payload['compose_pending_evidence'] = _evidence(fresh) if fresh_state == 'ok' else None
            payload['compose_pending_membership'] = sorted(_retained_ids(current))
        return payload

    def finish_guard(current: Mapping[str, Any]) -> Optional[str]:
        if (current.get('compose_lease') or {}).get('token') != lease_token or datetime.now(
            timezone.utc
        ) >= lease_until:
            return 'superseded'
        if set(member_ids) - set(_retained_ids(current)):
            return 'superseded'
        if superseded:
            # Never clobber a compose that landed after this call started.
            composed_at = _utc(current.get('composed_at'))
            return 'unchanged' if composed_at and composed_at > call_started else None
        if sorted(_retained_ids(current)) != sorted(_retained_ids(episode)):
            return None if keep_paid else 'superseded'
        return None

    written = _write(uid, episode_id, c, finish, guard=finish_guard, expected_member_revisions=fresh_revisions)
    if written == 'refused':
        # Older data can refuse a window change: keep the paid notes on the window it already has.
        written = _write(
            uid,
            episode_id,
            c,
            lambda current: {k: v for k, v in finish(current).items() if k != 'member_activity'},
            guard=finish_guard,
            expected_member_revisions=fresh_revisions,
        )
    if written in {'conflict', 'refused'}:
        _record_failure(uid, episode_id, c, print_, lease_token=lease_token)
        return 'conflict'
    if written != 'written':
        _write(uid, episode_id, c, lambda current: _release(current, print_, lease_token))
        return written
    if kept_pending['value']:
        # Retain the paid result and let the quiet-window timer refresh it.
        if episode_compose_settle_enabled():
            _defer(uid, episode_id, c, COMPOSER_SETTLE_SECONDS)
            return 'kept_pending'
        return 'superseded'
    # A transcript change that landed between the evidence re-read and the write: compose again.
    after_state, after = _members(
        uid, episodes_db.get_episode(uid, episode_id, firestore_client=c.firestore_client) or episode, c
    )
    if after_state != 'ok' or fingerprint(after) != print_:
        return 'stale'
    return 'composed'


def _trigger_stamp(episode: Mapping[str, Any], members: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    # Keep collecting stamps during rollback so re-enabling never requires a paid migration wave.
    return {
        'composed_evidence': _evidence(members),
        'composed_membership': sorted(_retained_ids(episode)),
        'compose_pending_since': None,
        'compose_activity_at': None,
        'compose_pending_evidence': None,
        'compose_pending_membership': None,
        'compose_deferred_at': None,
        'compose_opened_deferred_at': None,
    }


def _observe_evidence(
    uid: str, episode: Mapping[str, Any], c: Any, evidence: Mapping[str, str]
) -> Optional[dict[str, Any]]:
    """Persist arrival activity; failure bypasses settling, never the compose or its lease."""
    now = datetime.now(timezone.utc)
    membership = sorted(_retained_ids(episode))
    if (
        episode.get('compose_pending_since')
        and episode.get('compose_pending_evidence') == evidence
        and episode.get('compose_pending_membership') == membership
    ):
        return dict(episode)

    def observe(current: Mapping[str, Any]) -> dict[str, Any]:
        return {
            'compose_pending_since': current.get('compose_pending_since') or now,
            'compose_activity_at': now,
            'compose_pending_evidence': dict(evidence),
            'compose_pending_membership': membership,
        }

    try:
        outcome = _write(uid, str(episode['id']), c, observe)
        if outcome != 'written':
            raise ComposeFailed('settle_state_conflict')
        return episodes_db.get_episode(uid, str(episode['id']), firestore_client=c.firestore_client) or dict(episode)
    except Exception as error:
        logger.warning('event=episode_compose_settle outcome=bypassed exception_type=%s', type(error).__name__)
        record_fallback(
            component='conversation_notes',
            from_mode='episode_compose_settling',
            to_mode='episode_compose_immediate',
            reason='enqueue_failed',
            outcome='degraded',
            log=logger,
        )
        return None


def settle_delay(episode: Mapping[str, Any], *, now: Optional[datetime] = None) -> float:
    """A ten-minute quiet window, bounded by 25 minutes from the first uncomposed arrival."""
    now = now or datetime.now(timezone.utc)
    first = _utc(episode.get('compose_pending_since')) or now
    activity = max(
        at
        for at in (
            _utc(episode.get('compose_activity_at')) or first,
            _utc(episode.get('closed_at')) or first,
            _utc(episode.get('last_activity_at')) or first,
        )
    )
    due = min(
        activity + timedelta(seconds=COMPOSER_SETTLE_SECONDS), first + timedelta(seconds=COMPOSER_MAX_SETTLE_SECONDS)
    )
    return max(0.0, (due - now).total_seconds())


@phase_shadow.compare('episode_composer')
def needs_compose(
    episode: Optional[Mapping[str, Any]],
    *,
    visible_member_ids: Optional[Sequence[str]] = None,
    opened: bool = False,
) -> bool:
    """Cheap read-side check; the fingerprint decides for real inside ``compose``.

    ``visible_member_ids``, when the caller already read the members, catches a member
    discarded or deleted directly on its conversation after the compose. A visible change
    (members, notes drift, a regeneration request) always qualifies; the failure backoff
    only holds back retries of an episode that was never composed.

    ``opened`` is the episode page's own read: it composes a deferred late episode now.
    Every other read leaves a deferred episode alone until its grace window ends.
    """
    if not episode or policy.is_live(episode) or not episode_composer_enabled():
        return False
    if episode_late_compose_enabled() and not opened and _deferred_within_grace(episode):
        return False
    # A restart loses the local queue. Rollback must still drain persisted pending evidence.
    if episode.get('compose_pending_since'):
        return True
    if episode_compose_settle_enabled():
        membership = episode.get('composed_membership')
        if membership is not None and membership != sorted(_retained_ids(episode)):
            return True
    composed = episode.get('composed_member_ids')
    if visible_member_ids is not None and composed is not None and sorted(composed) != sorted(visible_member_ids):
        return True
    if episode.get('composed_fingerprint') and episode.get('composed_notes') != notes_hash(episode):
        return True
    if episode.get('summary_needs_regeneration'):
        return True
    if episode.get('composed_fingerprint') and episode.get('composer_version') != COMPOSER_VERSION:
        return not _backed_off(episode)  # A new composer: recompose once on read, backing off on failure.
    return not episode.get('composed_fingerprint') and not _backed_off(episode)


_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='episode-compose')
_inflight: set[tuple[str, str]] = set()
_recent: dict[tuple[str, str], float] = {}
_rerun: set[tuple[str, str]] = set()
_inflight_lock = threading.Lock()
# Due work holds no executor slot. The tracked backend task drains it and is cancelled at shutdown.
_deferred: dict[tuple[str, str], tuple[float, Any]] = {}
_foreground: set[tuple[str, str]] = set()


def _defer(uid: str, episode_id: str, c: Any, delay: float) -> bool:
    """Return whether work was retained; a full queue must leave the caller free to compose now."""
    key = (uid, str(episode_id))
    with _inflight_lock:
        due = time.monotonic() + delay
        previous = _deferred.get(key)
        if previous:
            due = min(due, previous[0])
        if key not in _deferred and len(_deferred) >= 10_000:
            return False
        _deferred[key] = (due, c)
        return True


def _schedule_due() -> None:
    now = time.monotonic()
    with _inflight_lock:
        due = [key for key, (at, _) in _deferred.items() if at <= now and key not in _inflight]
        work = [(key, _deferred.pop(key)[1]) for key in due]
    for (uid, episode_id), c in work:
        schedule(uid, episode_id, collaborators=c, trigger='settle')


async def retry_settled_composes() -> None:
    """Process-local deferral, like the existing executor; reads/finalizes recover work after restart."""
    try:
        while True:
            _schedule_due()
            await asyncio.sleep(1)
    finally:
        with _inflight_lock:
            _deferred.clear()


def schedule(
    uid: str, episode_id: str, *, collaborators: Any = None, throttle: bool = False, trigger: str = 'close'
) -> bool:
    """Compose in the background once per (uid, episode) at a time. Returns whether it was queued.

    ``throttle`` (read-side callers) skips an episode this process queued in the last few minutes,
    so an episode still waiting on a member is not re-read on every list request. ``trigger`` is
    the bounded origin label (close|read|member_final|settle) carried to the compose metric.
    """
    if not episode_composer_enabled() or not episode_id:
        return False
    key = (uid, str(episode_id))
    now = time.monotonic()
    with _inflight_lock:
        enabled = episode_compose_settle_enabled()
        deferred = key in _deferred
        if enabled and throttle:
            _deferred.pop(key, None)
            if key in _inflight:
                _foreground.add(key)
                _rerun.add(key)
                return False
        if key in _inflight:
            if not throttle:
                _rerun.add(key)  # Evidence may have changed under the running compose.
            return False
        if deferred and enabled and not throttle:
            return False
        if throttle and not (enabled and deferred) and now - _recent.get(key, -1e9) < COMPOSER_READ_THROTTLE_SECONDS:
            return False
        if len(_recent) > 10_000:
            _recent.clear()
        _recent[key] = now
        _inflight.add(key)

    def run() -> None:
        foreground = throttle
        outcome = 'error'
        try:
            for _attempt in range(3):
                if episode_compose_settle_enabled():
                    outcome = compose(
                        uid, str(episode_id), collaborators=collaborators, background=not foreground, trigger=trigger
                    )
                else:
                    outcome = compose(uid, str(episode_id), collaborators=collaborators, trigger=trigger)
                if outcome in {'stale', 'superseded'} and not foreground and episode_compose_settle_enabled():
                    # The cap allows one attempt during a long upload, not three paid retries in a burst.
                    now_at = datetime.now(timezone.utc)
                    _write(
                        uid,
                        str(episode_id),
                        collaborators or SimpleNamespace(firestore_client=None),
                        {
                            'compose_pending_since': now_at,
                            'compose_activity_at': now_at,
                        },
                    )
                with _inflight_lock:
                    again = outcome != 'kept_pending' and (key in _rerun or outcome in {'stale', 'superseded'})
                    _rerun.discard(key)
                    if outcome == 'waiting' and trigger == 'read':
                        _recent.pop(key, None)
                    foreground = foreground or key in _foreground
                    _foreground.discard(key)
                    if outcome not in {'settling', 'kept_pending'}:
                        _deferred.pop(key, None)
                if outcome == 'settling' and not foreground:
                    break
                if not again:
                    break
        finally:
            with _inflight_lock:
                # A read/finalize can arrive after the loop decides to stop but before it releases
                # inflight ownership. Hand it off instead of dropping its promotion until the timer.
                enabled = episode_compose_settle_enabled()
                promote = (
                    enabled and outcome != 'kept_pending' and (key in _foreground or (foreground and key in _deferred))
                )
                reschedule = enabled and (key in _rerun or promote)
                if promote:
                    _deferred[key] = (time.monotonic(), collaborators)
                _inflight.discard(key)
                _rerun.discard(key)
                _foreground.discard(key)
            if reschedule:
                schedule(uid, str(episode_id), collaborators=collaborators, throttle=promote, trigger=trigger)

    try:
        _executor.submit(run)
        return True
    except RuntimeError:
        with _inflight_lock:
            _inflight.discard(key)
        return False


def after_finalized(
    uid: str, conversation_id: str, outcome: str, collaborators: Any = None, *, row: Optional[Mapping[str, Any]] = None
) -> str:
    """A member finished: once its episode is closed and every member is done, compose it."""
    schedule_for_conversation(uid, conversation_id, collaborators=collaborators, row=row)
    return outcome


def schedule_for_conversation(
    uid: str, conversation_id: str, *, collaborators: Any = None, row: Optional[Mapping[str, Any]] = None
) -> None:
    if not episode_composer_enabled():
        return
    try:
        c = collaborators
        client = getattr(c, 'firestore_client', None)
        episode = episodes_db.get_episode_for_conversation(uid, conversation_id, firestore_client=client)
        if episode and not policy.is_live(episode):
            if defer_late_compose(uid, episode, c or SimpleNamespace(firestore_client=None)):
                return
            if episode_compose_settle_enabled():
                c = c or SimpleNamespace(firestore_client=None, people_names=None)
                member = (
                    dict(row)
                    if row is not None
                    else conversations_db.get_conversation(uid, conversation_id, firestore_client=client)
                )
                baseline = episode.get('compose_pending_evidence') or episode.get('composed_evidence')
                # A legacy full hash cannot distinguish new speech from regenerated labels.
                # _compose backfills a matching hash for free; otherwise it settles one safe compose.
                if isinstance(baseline, Mapping):
                    evidence = dict(baseline)
                    if (
                        member
                        and not hidden_member(member)
                        and conversations_db.is_visible_conversation(member)
                        and conversation_id in _retained_ids(episode)
                    ):
                        evidence[conversation_id] = evidence_trigger({'transcript_segments': _named(uid, member, c)})
                    else:
                        evidence.pop(conversation_id, None)
                    evidence = {cid: stamp for cid, stamp in evidence.items() if cid in _retained_ids(episode)}
                    membership = (
                        episode.get('compose_pending_membership')
                        if episode.get('compose_pending_since')
                        else episode.get('composed_membership')
                    )
                    changed = evidence != baseline or membership != sorted(_retained_ids(episode))
                    if (
                        member
                        and episode_single_member_compose_enabled()
                        and _retained_ids(episode) == [conversation_id]
                    ):
                        named_member = {**member, 'id': conversation_id, 'transcript_segments': _named(uid, member, c)}
                        changed = changed or fingerprint([named_member]) != episode.get('composed_fingerprint')
                    if not changed and not needs_compose(episode):
                        metrics.record_compose_trigger_skipped('evidence_unchanged')
                        return
                    if changed:
                        _observe_evidence(uid, episode, c, evidence)
            schedule(uid, str(episode['id']), collaborators=collaborators, trigger='member_final')
    except Exception as error:
        logger.warning('event=episode_compose_schedule outcome=error exception_type=%s', type(error).__name__)


def owns_closed_notes(uid: str, episode: Mapping[str, Any], conversation_id: str, c: Any) -> bool:
    """Whether the composer will write this closed episode's notes, so a per-moment write may skip
    its model call. Every other retained member must already be done (else compose would wait,
    perhaps forever, and the skipped speech would never reach the notes) and the evidence must not
    be backed off after failures."""
    if not episode_composer_enabled() or policy.is_live(episode) or _backed_off(episode):
        return False
    try:
        for cid in _retained_ids(episode):
            if cid == conversation_id:
                continue
            row = conversations_db.get_conversation(uid, cid, firestore_client=getattr(c, 'firestore_client', None))
            if row and not hidden_member(row) and str(row.get('status') or '') not in _DONE:
                return False
    except Exception:
        return False
    return True


def recovery_notes_wait(episode: Optional[Mapping[str, Any]], updated_at: Optional[datetime], now: datetime) -> bool:
    """Recovered audio arrives batch by batch and the composer rewrites these notes at close, so draft
    notes refresh at most once per interval. Unconsumed speech stays in the conversation for the composer.
    Without a working composer these notes are the final ones and nothing waits."""
    if not episode or updated_at is None or not episode_composer_enabled() or _backed_off(episode):
        return False
    return (now - updated_at).total_seconds() < RECOVERY_NOTES_MIN_INTERVAL_SECONDS


def notes_free(*_args: Any, **_kwargs: Any) -> Any:
    """Stands in for the per-moment model call on a closed episode the composer owns: no call,
    no notes change; membership, cursors, receipts and member activity are still recorded."""
    from utils.episodes.incremental import ModelResult
    from utils.episodes.state import IncrementalUpdate

    return ModelResult(IncrementalUpdate(), 0, 0, 0.0, model_calls=0)


def no_changes(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {}
