"""Episode composer: one strong summary per closed episode.

The live incremental notes (``incremental.py``) are a cheap preview written by a small
model that only sees a few minutes at a time. Once an episode is closed and every retained
member conversation has finished processing, the composer reads the members' own summaries
plus the episode's full transcript in one ``episode_composer`` call and replaces the
episode's title, notes and moments with a whole-episode summary and a handful of chapters.

It runs again when the episode's evidence changes (a late member finishes, sync upgrades a
transcript, a member is discarded): the ``composed_fingerprint`` over retained members and
their transcripts decides. Kill switch: ``EPISODE_COMPOSER`` (on unless set off). Never
raises to callers.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Optional, Sequence, Union
from uuid import uuid4
from zoneinfo import ZoneInfo

from config.episodes import (
    COMPOSER_FEATURE,
    COMPOSER_LEASE_SECONDS,
    COMPOSER_MAX_FAILURES,
    COMPOSER_MAX_DETAILS,
    COMPOSER_MAX_PARAGRAPH_CHARS,
    COMPOSER_MAX_POINT_CHARS,
    COMPOSER_MAX_POINTS,
    COMPOSER_READ_THROTTLE_SECONDS,
    COMPOSER_RETRY_MINUTES,
    COMPOSER_MAX_CHAPTERS,
    COMPOSER_MAX_TRANSCRIPT_CHARS,
    COMPOSER_TIMEOUT_SECONDS,
    COMPOSER_VERSION,
    episode_composer_enabled,
)
from database import conversations as conversations_db
from database import episodes as episodes_db
from utils.conversations.recorded_time import conversation_span
from utils.episodes import policy
from utils.episodes.visibility import hidden_member
from utils.llm.clients import get_llm
from utils.llm.usage_tracker import track_usage

logger = logging.getLogger(__name__)

_DONE = {'completed'}
_PLACEHOLDER = re.compile(r'^\s*(new|unknown)\b.*\bmoment\b', re.I)
_WINDOW_SECONDS = 600
_CLOCK_SLACK_MINUTES = 2

SYSTEM_PROMPT = """You write the page people read for an "episode": one continuous stretch of {owner}'s day captured by a wearable. It can span several recordings. {owner} is the wearer; call them {owner}, never "the user" or "someone".
You get each recording's existing summary and action items, and the full transcript (or its densest stretches when it is very long). The transcript is automatic and noisy: speaker labels can be wrong, and short fragments in other languages are usually mis-transcribed background noise. Use the summaries as a map and the transcript as the source of truth.
Write in {language}. Return JSON only:
{{"title": "<= 7 words, specific to what happened",
 "emoji": "one emoji",
 "lede": "one or two sentences: what this stretch of the day was and what came out of it",
 "chapters": [{{"start": "HH:MM:SS", "end": "HH:MM:SS", "title": "<= 6 words",
   "points": [{{"text": "one specific point", "details": ["a supporting specific"]}}]}}],
 "follow_ups": ["a concrete next step someone committed to or clearly needs to take"],
 "people": ["names of people who mattered, only if named"]}}
chapters are the body of the page: 1 to {max_chapters} significant stretches in time order. start and end are the clock labels of the chapter's first and last transcript lines, copied exactly. Each chapter has 2 to 5 points; a point may carry 0 to 3 details. Points carry the substance the way good meeting notes do: names, numbers, product and feature names, the exact problem or idea, what was decided and why, open questions. Never repeat the lede inside a chapter. Attribute a statement, request or decision to a person only when the transcript makes the speaker clear; otherwise write it without a name.
Skip noise, background chatter, mumbling and filler entirely. Never write meta-commentary such as "no decision was recorded" or "nothing else was discussed": leave it out. Never write speaker labels or quote filler. Never title anything "New moment" or similar. follow_ups is empty when there are none."""


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
            )
            for s in _segments(row)
        ]
        evidence = json.dumps(
            [structured.get('title'), structured.get('overview'), items, speech], default=str, ensure_ascii=False
        )
        parts.append([str(row.get('id')), hashlib.sha256(evidence.encode()).hexdigest()[:24]])
    raw = json.dumps([COMPOSER_VERSION, parts], separators=(',', ':'))
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


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
    label = str(segment.get('speaker') or 'Speaker').replace('SPEAKER_', 'Speaker ')
    return label


def _origin(row: Mapping[str, Any]) -> Optional[datetime]:
    """The instant a member's segment offsets count from."""
    return _utc(row.get('started_at')) or _span(row)[0]


def transcript_lines(row: Mapping[str, Any], owner: str, tz: ZoneInfo) -> list[tuple[datetime, str]]:
    origin = _origin(row)
    out = []
    for segment in _segments(row):
        at = (origin or datetime.now(timezone.utc)) + timedelta(seconds=float(segment.get('start') or 0))
        local = at.astimezone(tz)
        out.append((at, f"[{local:%H:%M:%S}] {_speaker(segment, owner)}: {str(segment.get('text')).strip()}"))
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
    return re.sub(r'\s+', ' ', str(value or '')).strip().strip('•-* ').strip()[:limit].rstrip()


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
        times = {str(row.get('id')): [at for at, _ in transcript_lines(row, '', tz)] for row in members}
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
            if not heading or _PLACEHOLDER.match(heading) or start is None:
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
        if end is None or end <= start:
            # The last line the chapter owns: before the next chapter, on its own recording.
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


def invoke_model(uid: str, messages: list[tuple[str, str]]) -> Any:
    with track_usage(uid, COMPOSER_FEATURE):
        llm = get_llm('episode_composer', uid=uid, request_timeout=COMPOSER_TIMEOUT_SECONDS, max_retries=1)
        return llm.invoke(messages)


def _usage(reply: Any) -> tuple[int, int]:
    meta = getattr(reply, 'usage_metadata', None) or {}
    return int(meta.get('input_tokens') or 0), int(meta.get('output_tokens') or 0)


def compose(uid: str, episode_id: str, *, collaborators: Any = None, force: bool = False) -> str:
    """Compose a closed episode once its members are done. Returns an outcome label; never raises."""
    if not episode_composer_enabled():
        return 'disabled'
    from utils.episodes import metrics
    from utils.episodes import service

    c = collaborators or service.Collaborators()
    started = time.monotonic()
    try:
        outcome = _compose(uid, episode_id, c, force=force, service=service)
    except Exception as error:  # Never break finalization or reads.
        logger.warning('event=episode_compose outcome=error exception_type=%s', type(error).__name__)
        outcome = 'error'
    metrics.record_compose(outcome, time.monotonic() - started)
    return outcome


def _named(uid: str, row: Mapping[str, Any], c: Any) -> list[dict[str, Any]]:
    """Segments with stored person names, so a rename changes the evidence fingerprint too."""
    from utils.episodes import service

    owner: Any = service  # the same seam the live notes use (people lookup, owner gate)
    return owner._named_segments(uid, _segments(row), c)


def _members(uid: str, episode: Mapping[str, Any], c: Any) -> tuple[str, list[dict[str, Any]]]:
    """('ok' | 'waiting', retained visible members sorted by start)."""
    members = []
    for cid in _retained_ids(episode):
        row = conversations_db.get_conversation(uid, cid, firestore_client=c.firestore_client)
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
) -> str:
    """CAS write with bounded retries. ``guard(current)`` returns an outcome to stop, or None."""
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
            )
            return 'written'
        except episodes_db.EpisodeConflict:
            continue
    return 'conflict'


def _record_failure(uid: str, episode_id: str, c: Any, print_: str) -> None:
    """Back off after a failed paid attempt. The count is per evidence: new evidence starts at one."""
    try:
        _write(
            uid,
            episode_id,
            c,
            lambda current: {
                'compose_failures': (
                    int(current.get('compose_failures') or 0) + 1
                    if current.get('compose_failed_fingerprint') == print_
                    else 1
                ),
                'compose_failed_fingerprint': print_,
                'compose_failed_at': datetime.now(timezone.utc),
                **_release(current, print_),
            },
        )
    except Exception:
        pass


def _release(current: Mapping[str, Any], print_: str) -> dict[str, Any]:
    """Clear the lease only if it is still ours; a newer compose's lease stays."""
    lease = current.get('compose_lease')
    return {'compose_lease': None} if isinstance(lease, Mapping) and lease.get('fingerprint') == print_ else {}


def _backed_off(episode: Mapping[str, Any], print_: Optional[str] = None) -> bool:
    """Failed paid attempts on the same evidence back off 10/20/40 min, then stop until it changes."""
    failures = int(episode.get('compose_failures') or 0)
    if not failures:
        return False
    if print_ is not None and episode.get('compose_failed_fingerprint') != print_:
        return False
    if failures >= COMPOSER_MAX_FAILURES:
        return True
    failed_at = _utc(episode.get('compose_failed_at'))
    backoff = timedelta(minutes=COMPOSER_RETRY_MINUTES * (2 ** (failures - 1)))
    return bool(failed_at and datetime.now(timezone.utc) - failed_at < backoff)


def _compose(uid: str, episode_id: str, c: Any, *, force: bool, service: Any) -> str:
    episode = episodes_db.get_episode(uid, episode_id, firestore_client=c.firestore_client)
    if not episode:
        return 'no_episode'
    if policy.is_live(episode):
        return 'live'
    state, members = _members(uid, episode, c)
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
            'composed_notes': notes_hash(cleared),
            'composer_version': COMPOSER_VERSION,
            'summary_needs_regeneration': False,
        }
        _write(uid, episode_id, c, stamp)
        return 'empty'
    print_ = fingerprint(members)
    if (
        not force
        and episode.get('composed_fingerprint') == print_
        and episode.get('composed_notes') == notes_hash(episode)
        and not episode.get('summary_needs_regeneration')
    ):
        return 'unchanged'
    if not force and _backed_off(episode, print_):
        return 'backoff'
    invoke = (c.extras or {}).get('compose_invoke')
    if invoke is None and getattr(c, 'invoke', None) is not None:
        # Collaborators that fake the incremental model never reach the real composer model.
        return 'disabled'
    invoke = invoke or invoke_model

    # One paid call per evidence across replicas: claim a short lease for this fingerprint.
    now = datetime.now(timezone.utc)

    def lease_guard(current: Mapping[str, Any]) -> Optional[str]:
        lease = current.get('compose_lease') or {}
        until = _utc(lease.get('until')) if isinstance(lease, Mapping) else None
        if until and until > now and lease.get('fingerprint') == print_ and not force:
            return 'leased'
        if current.get('composed_fingerprint') == print_ and current.get('composed_notes') == notes_hash(current):
            return 'unchanged' if not force else None
        return None

    claimed = _write(
        uid,
        episode_id,
        c,
        {'compose_lease': {'fingerprint': print_, 'until': now + timedelta(seconds=COMPOSER_LEASE_SECONDS)}},
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
    messages = build_messages(named, owner=owner, tz=tz, language=language)
    try:
        reply = invoke(uid, messages)
        content = getattr(reply, 'content', reply)
        if isinstance(content, list):
            content = ''.join(part.get('text', '') if isinstance(part, Mapping) else str(part) for part in content)
        data = parse(str(content))
        times = {str(row['id']): [at for at, _ in transcript_lines(row, owner, tz)] for row in members}
        spans = [(cid, min(ts), max(ts)) if ts else (cid, None, None) for cid, ts in times.items()]
        composed = to_updates(data, members, tz, spans, times)
        if not any(m['points'] for m in composed['moments']):
            raise ComposeFailed('no_sections')  # Speech was there: a page with no sections is a failed compose.
    except Exception:
        _record_failure(uid, episode_id, c, print_)
        raise
    input_tokens, output_tokens = _usage(reply)

    # The model call took seconds: re-read the evidence. A discard, a transcript upgrade or a
    # membership change since then makes this result stale; its own trigger composes again.
    fresh_state, fresh = _members(
        uid, episodes_db.get_episode(uid, episode_id, firestore_client=c.firestore_client) or episode, c
    )
    if fresh_state != 'ok' or fingerprint(fresh) != print_:
        _write(uid, episode_id, c, lambda current: _release(current, print_))
        return 'superseded'

    def finish(current: Mapping[str, Any]) -> dict[str, Any]:
        usage = dict(current.get('usage') or {})
        usage['composer_calls'] = int(usage.get('composer_calls') or 0) + 1
        usage['composer_input_tokens'] = int(usage.get('composer_input_tokens') or 0) + input_tokens
        usage['composer_output_tokens'] = int(usage.get('composer_output_tokens') or 0) + output_tokens
        return {
            **composed,
            'usage': usage,
            'composed_fingerprint': print_,
            'composed_member_ids': member_ids,
            'composed_notes': notes_hash(composed),
            'composed_at': datetime.now(timezone.utc),
            'composer_version': COMPOSER_VERSION,
            'summary_needs_regeneration': False,
            'compose_failures': 0,
            **_release(current, print_),
        }

    def finish_guard(current: Mapping[str, Any]) -> Optional[str]:
        if sorted(_retained_ids(current)) != sorted(_retained_ids(episode)):
            return 'superseded'
        return None

    written = _write(uid, episode_id, c, finish, guard=finish_guard)
    if written != 'written':
        _write(uid, episode_id, c, lambda current: _release(current, print_))
        return written
    # A transcript change that landed between the evidence re-read and the write: compose again.
    after_state, after = _members(
        uid, episodes_db.get_episode(uid, episode_id, firestore_client=c.firestore_client) or episode, c
    )
    if after_state != 'ok' or fingerprint(after) != print_:
        return 'stale'
    return 'composed'


def needs_compose(episode: Optional[Mapping[str, Any]], *, visible_member_ids: Optional[Sequence[str]] = None) -> bool:
    """Cheap read-side check; the fingerprint decides for real inside ``compose``.

    ``visible_member_ids``, when the caller already read the members, catches a member
    discarded or deleted directly on its conversation after the compose. A visible change
    (members, notes drift, a regeneration request) always qualifies; the failure backoff
    only holds back retries of an episode that was never composed.
    """
    if not episode or policy.is_live(episode) or not episode_composer_enabled():
        return False
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


def schedule(uid: str, episode_id: str, *, collaborators: Any = None, throttle: bool = False) -> bool:
    """Compose in the background once per (uid, episode) at a time. Returns whether it was queued.

    ``throttle`` (read-side callers) skips an episode this process queued in the last few minutes,
    so an episode still waiting on a member is not re-read on every list request.
    """
    if not episode_composer_enabled() or not episode_id:
        return False
    key = (uid, str(episode_id))
    now = time.monotonic()
    with _inflight_lock:
        if key in _inflight:
            if not throttle:
                _rerun.add(key)  # Evidence may have changed under the running compose.
            return False
        if throttle and now - _recent.get(key, -1e9) < COMPOSER_READ_THROTTLE_SECONDS:
            return False
        if len(_recent) > 10_000:
            _recent.clear()
        _recent[key] = now
        _inflight.add(key)

    def run() -> None:
        try:
            for _attempt in range(3):
                outcome = compose(uid, str(episode_id), collaborators=collaborators)
                with _inflight_lock:
                    again = key in _rerun or outcome in {'stale', 'superseded'}
                    _rerun.discard(key)
                if not again:
                    break
        finally:
            with _inflight_lock:
                _inflight.discard(key)
                _rerun.discard(key)

    try:
        _executor.submit(run)
        return True
    except RuntimeError:
        with _inflight_lock:
            _inflight.discard(key)
        return False


def after_finalized(uid: str, conversation_id: str, outcome: str, collaborators: Any = None) -> str:
    """A member finished: once its episode is closed and every member is done, compose it."""
    schedule_for_conversation(uid, conversation_id, collaborators=collaborators)
    return outcome


def schedule_for_conversation(uid: str, conversation_id: str, *, collaborators: Any = None) -> None:
    if not episode_composer_enabled():
        return
    try:
        c = collaborators
        client = getattr(c, 'firestore_client', None)
        episode = episodes_db.get_episode_for_conversation(uid, conversation_id, firestore_client=client)
        if episode and not policy.is_live(episode):
            schedule(uid, str(episode['id']), collaborators=collaborators)
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


def notes_free(*_args: Any, **_kwargs: Any) -> Any:
    """Stands in for the per-moment model call on a closed episode the composer owns: no call,
    no notes change; membership, cursors, receipts and member activity are still recorded."""
    from utils.episodes.incremental import ModelResult
    from utils.episodes.state import IncrementalUpdate

    return ModelResult(IncrementalUpdate(), 0, 0, 0.0, model_calls=0)


def no_changes(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {}
