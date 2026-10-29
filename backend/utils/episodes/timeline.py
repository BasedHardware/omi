"""One ownership question for every device: which episode owns recorded time T?"""

from datetime import datetime
from typing import Any

from config.episodes import CLOSE_GAP_SECONDS, MAX_EPISODE_SECONDS
from database import episode_timeline, episodes
from utils.episodes.policy import utc


def choose_recorded_episode(rows: list[dict], started: datetime, finished: datetime) -> dict | None:
    """Arrival-independent interval/gap policy; deterministic across devices.

    Overlap wins before adjacency. Exactly thirty minutes of recorded quiet
    starts another occasion. An explicit close is a boundary after its recorded
    activity, but does not exclude speech inside that occasion's window.
    """
    candidates = []
    for row in rows:
        lo, hi = utc(row.get('started_at')), utc(episode_timeline.recorded_end(row))
        if lo is None or hi is None or hi < lo:
            continue
        gap = max(0.0, (started - hi).total_seconds(), (lo - finished).total_seconds())
        if gap >= CLOSE_GAP_SECONDS or (max(hi, finished) - min(lo, started)).total_seconds() > MAX_EPISODE_SECONDS:
            continue
        if (started - lo).total_seconds() >= MAX_EPISODE_SECONDS:
            continue
        if started >= hi and row.get('status') != 'live' and row.get('close_reason') not in {'gap', 'idle'}:
            continue
        overlap = max(0.0, (min(hi, finished) - max(lo, started)).total_seconds())
        candidates.append((gap, -overlap, lo, str(row['id']), row))
    return min(candidates, key=lambda item: item[:4])[-1] if candidates else None


def episode_owning_recorded_time(
    uid: str, at: datetime, *, ended_at: datetime | None = None, firestore_client: Any = None
) -> dict | None:
    """Read-only agent/service API. No episode is created, opened or closed.

    A bounded complete metadata window plus pure policy identifies the owner;
    only the selected episode's compact content is then read.
    """
    end = ended_at or at
    rows = episode_timeline.recorded_candidates(uid, at, end, firestore_client=firestore_client)
    owner = choose_recorded_episode(rows, at, end)
    return episodes.get_episode(uid, owner['id'], firestore_client=firestore_client) if owner else None


def ownership_end(row: dict) -> datetime | None:
    """Half-open recorded ownership window; scheduling/arrival is not an edge."""
    from datetime import timedelta

    lo, hi = utc(row.get('started_at')), utc(episode_timeline.recorded_end(row))
    if lo is None or hi is None:
        return None
    if row.get('status') == 'live' or row.get('close_reason') in {'gap', 'idle'}:
        hi += timedelta(seconds=CLOSE_GAP_SECONDS)
    return min(hi, lo + timedelta(seconds=MAX_EPISODE_SECONDS))


def episode_at(uid: str, at: datetime, *, firestore_client: Any = None) -> dict | None:
    """Which persisted episode owns recorded time T? Read-only, half-open windows."""
    point = utc(at)
    if point is None:
        raise ValueError('recorded time must be a datetime')
    at = point
    rows = episode_timeline.between(uid, at, at, firestore_client=firestore_client)
    owners = [
        r
        for r in rows
        if (lo := utc(r.get('started_at'))) is not None
        and lo <= at
        and (hi := ownership_end(r)) is not None
        and (at < hi or lo == hi == at)
    ]
    # Latest recorded start wins if legacy windows overlap. Never depend on query/arrival order.
    owner = max(owners, key=lambda r: (r['started_at'], str(r['id']))) if owners else None
    return episodes.get_episode(uid, owner['id'], firestore_client=firestore_client) if owner else None


def episodes_between(uid: str, start: datetime, end: datetime, *, firestore_client: Any = None) -> list[dict]:
    """Episodes whose ownership windows intersect [start, end), in recorded order."""
    first, last = utc(start), utc(end)
    if first is None or last is None or last < first:
        raise ValueError('episode window must contain ordered datetimes')
    start, end = first, last
    if end == start:
        owner = episode_at(uid, start, firestore_client=firestore_client)
        return [owner] if owner else []
    rows = episode_timeline.between(uid, start, end, firestore_client=firestore_client)
    selected = [
        r
        for r in rows
        if (lo := utc(r.get('started_at'))) is not None
        and lo < end
        and (hi := ownership_end(r)) is not None
        and hi > start
    ]
    return [
        episode
        for row in sorted(selected, key=lambda r: (r['started_at'], str(r['id'])))
        if (episode := episodes.get_episode(uid, row['id'], firestore_client=firestore_client))
    ]
