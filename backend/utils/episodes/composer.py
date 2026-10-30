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
from typing import Any, Mapping, Optional, Sequence
from uuid import uuid4
from zoneinfo import ZoneInfo

from config.episodes import (
    COMPOSER_FEATURE,
    COMPOSER_LEASE_SECONDS,
    COMPOSER_MAX_FAILURES,
    COMPOSER_MAX_PARAGRAPH_CHARS,
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

SYSTEM_PROMPT = """You write the summary people read for an "episode": one continuous stretch of {owner}'s day captured by a wearable. It can span several recordings. {owner} is the wearer.
You get each recording's existing summary and the full transcript (or its densest stretches when it is very long). The transcript is automatic and noisy: speaker labels can be wrong, and short fragments in other languages are usually mis-transcribed background noise. Use the summaries as a map and the transcript as the source of truth.
Write in {language}. Return JSON only:
{{"title": "<= 7 words, specific to what happened",
 "emoji": "one emoji",
 "overview": "2-4 short paragraphs a busy person would want to read later: what happened, what was decided, what matters. Concrete names, numbers and decisions. No filler. Never write speaker labels, transcript lines or quotes of filler.",
 "chapters": [{{"start": "HH:MM", "end": "HH:MM", "title": "<= 6 words", "summary": "one sentence"}}],
 "people": ["names of people who mattered, only if named"]}}
chapters: 1 to {max_chapters} significant stretches in time order, with clock times copied from the transcript. Skip noise, background chatter, mumbling and filler entirely. Never title anything "New moment" or similar."""


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
        speech = [(round(float(s.get('start') or 0), 1), str(s.get('text')).strip()) for s in _segments(row)]
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


def transcript_lines(row: Mapping[str, Any], owner: str, tz: ZoneInfo) -> list[tuple[datetime, str]]:
    start, _ = _span(row)
    origin = _utc(row.get('started_at')) or start
    out = []
    for segment in _segments(row):
        at = (origin or datetime.now(timezone.utc)) + timedelta(seconds=float(segment.get('start') or 0))
        local = at.astimezone(tz)
        out.append((at, f"[{local:%H:%M}] {_speaker(segment, owner)}: {str(segment.get('text')).strip()}"))
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
    if isinstance(data.get('overview'), list):
        data['overview'] = '\n\n'.join(str(part) for part in data['overview'] if str(part).strip())
    if not str(data.get('title') or '').strip() or not str(data.get('overview') or '').strip():
        raise ComposeFailed('parse_error')
    return data


def line_span(lines: Sequence[tuple[datetime, str]]) -> tuple[Optional[datetime], Optional[datetime]]:
    """The span the model saw: first and last transcript line clock, the same origin as the labels."""
    if not lines:
        return None, None
    return min(at for at, _ in lines), max(at for at, _ in lines)


def _clock(value: Any, lo: datetime, hi: datetime, tz: ZoneInfo) -> Optional[datetime]:
    """Resolve a local HH:MM to an instant inside the episode's transcript span (two-minute slack)."""
    match = re.match(r'^\s*(\d{1,2}):(\d{2})', str(value or ''))
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    slack = timedelta(minutes=_CLOCK_SLACK_MINUTES)
    floor = lo.replace(second=0, microsecond=0) - slack
    for day in sorted({lo.astimezone(tz).date() + timedelta(days=d) for d in (-1, 0, 1, 2)}):
        candidate = datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz).astimezone(timezone.utc)
        if floor <= candidate <= hi + slack:
            return candidate
    return None


def to_updates(
    data: Mapping[str, Any],
    members: Sequence[Mapping[str, Any]],
    tz: ZoneInfo,
    spans: Optional[Sequence[tuple[str, Optional[datetime], Optional[datetime]]]] = None,
) -> dict[str, Any]:
    """``spans`` are (member id, first line, last line) on the transcript clock the model saw."""
    if spans is None:
        spans = [(str(row.get('id')), *line_span(transcript_lines(row, '', tz))) for row in members]
    known = [(cid, a, b) for cid, a, b in spans if a and b]
    moments = []
    if known:
        lo, hi = min(a for _, a, _ in known), max(b for _, _, b in known)
        for chapter in (data.get('chapters') or [])[:COMPOSER_MAX_CHAPTERS]:
            if not isinstance(chapter, Mapping):
                continue
            heading = re.sub(r'\s+', ' ', str(chapter.get('title') or '')).strip()[:60]
            start = _clock(chapter.get('start'), lo, hi, tz)
            if not heading or _PLACEHOLDER.match(heading) or start is None:
                continue
            end = _clock(chapter.get('end'), lo, hi, tz) or start
            if end < start:
                end = start
            owner = next(
                (cid for cid, a, b in known if a - timedelta(minutes=1) <= start <= b + timedelta(minutes=1)), None
            )
            owner = (
                owner
                or min(
                    known, key=lambda s: min(abs((s[1] - start).total_seconds()), abs((s[2] - start).total_seconds()))
                )[0]
            )
            moments.append(
                {
                    'id': uuid4().hex[:12],
                    'conversation_id': owner,
                    'started_at': start,
                    'ended_at': end + timedelta(seconds=59) if end == start else end,
                    'heading': heading,
                    'summary': str(chapter.get('summary') or '').strip()[:280],
                    'composed': True,
                }
            )
    moments.sort(key=lambda m: m['started_at'])
    paragraphs = [
        p.strip()[:COMPOSER_MAX_PARAGRAPH_CHARS]
        for p in re.split(r'\n\s*\n|\n', str(data.get('overview') or ''))
        if p.strip()
    ][:4]
    people = [str(p).strip() for p in data.get('people') or [] if str(p).strip()][:12]
    activity = {str(row.get('id')): end for row in members if (end := _span(row)[1])}
    updates: dict[str, Any] = {
        'title': re.sub(r'\s+', ' ', str(data.get('title'))).strip()[:80],
        'bullets': paragraphs,
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


def _members(uid: str, episode: Mapping[str, Any], c: Any) -> tuple[str, list[dict[str, Any]]]:
    """('ok' | 'waiting', retained visible members sorted by start)."""
    members = []
    for cid in _retained_ids(episode):
        row = conversations_db.get_conversation(uid, cid, firestore_client=c.firestore_client)
        if not row or hidden_member(row):
            continue
        if str(row.get('status') or '') not in _DONE:
            return 'waiting', []
        members.append({**row, 'id': cid})
    members.sort(key=lambda row: _span(row)[0] or datetime.max.replace(tzinfo=timezone.utc))
    return 'ok', members


def _write(uid: str, episode_id: str, c: Any, updates: Mapping[str, Any], *, guard=None) -> str:
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


def _record_failure(uid: str, episode_id: str, c: Any) -> None:
    """Back off the read-side safety net after a failed paid attempt."""
    try:
        _write(
            uid,
            episode_id,
            c,
            lambda current: {
                'compose_failures': int(current.get('compose_failures') or 0) + 1,
                'compose_failed_at': datetime.now(timezone.utc),
                'compose_lease': None,
            },
        )
    except Exception:
        pass


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
        # Nothing to say: stamp it so neither reads nor finalizers keep retrying.
        stamp = {
            'composed_fingerprint': fingerprint(members),
            'composed_member_ids': member_ids,
            'composed_notes': notes_hash(episode),
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
    named = [{**row, 'transcript_segments': service._named_segments(uid, _segments(row), c)} for row in members]
    language = str(episode.get('output_language') or 'English')
    language = {'en': 'English'}.get(language, language)
    messages = build_messages(named, owner=owner, tz=tz, language=language)
    try:
        reply = invoke(uid, messages)
        content = getattr(reply, 'content', reply)
        if isinstance(content, list):
            content = ''.join(part.get('text', '') if isinstance(part, Mapping) else str(part) for part in content)
        data = parse(str(content))
    except Exception:
        _record_failure(uid, episode_id, c)
        raise
    spans = [(str(row['id']), *line_span(transcript_lines(row, owner, tz))) for row in members]
    composed = to_updates(data, members, tz, spans)
    input_tokens, output_tokens = _usage(reply)

    # The model call took seconds: re-read the evidence. A discard, a transcript upgrade or a
    # membership change since then makes this result stale; its own trigger composes again.
    fresh_state, fresh = _members(
        uid, episodes_db.get_episode(uid, episode_id, firestore_client=c.firestore_client) or episode, c
    )
    if fresh_state != 'ok' or fingerprint(fresh) != print_:
        _write(uid, episode_id, c, {'compose_lease': None})
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
            'compose_lease': None,
            'compose_failures': 0,
        }

    def finish_guard(current: Mapping[str, Any]) -> Optional[str]:
        if sorted(_retained_ids(current)) != sorted(_retained_ids(episode)):
            return 'superseded'
        return None

    written = _write(uid, episode_id, c, finish, guard=finish_guard)
    if written != 'written':
        _write(uid, episode_id, c, {'compose_lease': None})
        return written
    return 'composed'


def needs_compose(episode: Optional[Mapping[str, Any]], *, visible_member_ids: Optional[Sequence[str]] = None) -> bool:
    """Cheap read-side check; the fingerprint decides for real inside ``compose``.

    ``visible_member_ids``, when the caller already read the members, catches a member
    discarded or deleted directly on its conversation after the compose.
    """
    if not episode or policy.is_live(episode) or not episode_composer_enabled():
        return False
    failures = int(episode.get('compose_failures') or 0)
    failed_at = _utc(episode.get('compose_failed_at'))
    if failures >= COMPOSER_MAX_FAILURES and not episode.get('summary_needs_regeneration'):
        return False
    if failures and failed_at:
        backoff = timedelta(minutes=COMPOSER_RETRY_MINUTES * (2 ** (failures - 1)))
        if datetime.now(timezone.utc) - failed_at < backoff:
            return False
    if not episode.get('composed_fingerprint') or episode.get('summary_needs_regeneration'):
        return True
    if episode.get('composed_notes') != notes_hash(episode):
        return True
    composed = episode.get('composed_member_ids')
    return visible_member_ids is not None and composed is not None and sorted(composed) != sorted(visible_member_ids)


_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='episode-compose')
_inflight: set[tuple[str, str]] = set()
_recent: dict[tuple[str, str], float] = {}
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
            return False
        if throttle and now - _recent.get(key, -1e9) < COMPOSER_READ_THROTTLE_SECONDS:
            return False
        if len(_recent) > 10_000:
            _recent.clear()
        _recent[key] = now
        _inflight.add(key)

    def run() -> None:
        try:
            compose(uid, str(episode_id), collaborators=collaborators)
        finally:
            with _inflight_lock:
                _inflight.discard(key)

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
