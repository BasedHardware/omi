"""Bounded foreground screen evidence for media; never infer it from transcript topics."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from models.boundary_evidence import BoundarySignal

MAX_SCREEN_ROWS = 80
MAX_OBSERVATION_SECONDS = 60
MIN_MEDIA_SHARE = 0.5
_MEDIA_APPS = frozenset(
    (
        'youtube',
        'netflix',
        'vlc',
        'iina',
        'quicktime player',
        'tv',
        'apple tv',
        'podcasts',
        'apple podcasts',
        'spotify',
        'overcast',
        'pocket casts',
        'coursera',
        'udemy',
    )
)
_MEDIA_SUFFIX = re.compile(r'\s*[-–—|]\s*(?:youtube|netflix|vimeo|coursera|udemy)\s*$', re.I)
_WATCH_URL = re.compile(
    r'https?://(?:www\.)?(?:youtube\.com/watch\?|youtu\.be/|netflix\.com/watch/|vimeo\.com/\d)', re.I
)
_GENERIC_TITLES = frozenset(('youtube', 'netflix', 'home', 'subscriptions', 'search', 'library', 'spotify'))


def screen_time(value: Any) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _title(row: Mapping[str, Any]) -> str | None:
    # Screen activity consists of foreground snapshots. Explicit background/paused
    # markers override that assumption. A mention in a transcript or OCR is insufficient.
    if row.get('isForeground') is False or row.get('is_foreground') is False or row.get('isPlaying') is False:
        return None
    app = str(row.get('appName') or '').strip().casefold()
    title = ' '.join(str(row.get('windowTitle') or '').split())[:160]
    url = str(row.get('url') or row.get('browserUrl') or '')
    if app not in _MEDIA_APPS and not _MEDIA_SUFFIX.search(title) and not _WATCH_URL.search(url):
        return None
    if title.casefold() in _GENERIC_TITLES:
        return None
    title = _MEDIA_SUFFIX.sub('', title).strip()
    return title[:120] or 'Media playback'


def media_playback_signals(
    rows: Sequence[Mapping[str, Any]], *, started_at: datetime, finished_at: datetime
) -> list[BoundarySignal]:
    """Require media across half the capture, with each snapshot valid for at most 60s.

    The next snapshot (including a non-media window) ends an observation. Never
    forward-fill an isolated video frame across hours of unrelated speech.
    """
    start, end = screen_time(started_at), screen_time(finished_at)
    if start is None or end is None or end <= start:
        return []
    ordered = sorted(
        ((at, row) for row in rows[:MAX_SCREEN_ROWS] if (at := screen_time(row.get('timestamp'))) is not None),
        key=lambda pair: pair[0],
    )
    spans: list[tuple[datetime, datetime, str]] = []
    for index, (at, row) in enumerate(ordered):
        title = _title(row)
        if title is None:
            continue
        next_at = ordered[index + 1][0] if index + 1 < len(ordered) else end
        left, right = max(start, at), min(end, next_at, at + timedelta(seconds=MAX_OBSERVATION_SECONDS))
        if right > left:
            spans.append((left, right, title))
    duration = (end - start).total_seconds()
    overlap = sum((right - left).total_seconds() for left, right, _ in spans)
    if overlap < max(min(15, duration), duration * MIN_MEDIA_SHARE):
        return []
    # The shared boundary ledger has a bounded recent-edge index. Adjacent
    # snapshots of one player are one observation interval, not new boundaries.
    intervals: list[tuple[datetime, datetime, str]] = []
    for left, right, title in spans:
        if intervals and intervals[-1][2] == title and left <= intervals[-1][1]:
            previous_left, previous_right, _ = intervals[-1]
            intervals[-1] = (previous_left, max(previous_right, right), title)
        else:
            intervals.append((left, right, title))
    signals = []
    for left, right, title in intervals:
        identity = hashlib.sha256(f'{left.isoformat()}:{right.isoformat()}:{title}'.encode()).hexdigest()
        signals.append(
            BoundarySignal(
                kind='media_playback',
                started_at=left,
                ended_at=right,
                title=title,
                confidence=0.8,
                external_id=f'media:{identity}',
            )
        )
    return signals
