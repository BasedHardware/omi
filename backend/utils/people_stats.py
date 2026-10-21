"""Per-person conversation stats for the People list.

Computed on demand from the newest conversations rather than denormalized onto each conversation: the
scan is bounded (PEOPLE_STATS_SCAN_CAP), so counts for a very long history cover the most recent
conversations only.
"""

from datetime import datetime, timezone
from itertools import islice
from typing import Any, Dict, Iterable, List, Optional

from database import people_stats_cache
from utils.other.list_budget import ListReadBudget

PEOPLE_STATS_SCAN_CAP = 1000


def _as_utc(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def aggregate_people_stats(conversations: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """person_id -> {conversation_count, last_heard_at, talk_seconds, auto_conversation_count}.

    ``auto_conversation_count`` counts conversations where every label for that person was an
    automatic match (``speaker_match_source`` set): matches the user never reviewed.
    """
    stats: Dict[str, Dict[str, Any]] = {}
    for conversation in conversations:
        if conversation.get('is_locked'):
            continue
        if conversation.get('discarded'):
            # The scan reader filters discarded rows server-side by default, but
            # include_discarded callers can still deliver them; stats never count them.
            continue
        segments = conversation.get('transcript_segments') or []
        if not isinstance(segments, list):
            continue
        heard_at = _as_utc(conversation.get('started_at')) or _as_utc(conversation.get('created_at'))
        seen: set = set()
        reviewed: set = set()
        for segment in segments:
            if not isinstance(segment, dict):
                continue
            person_id = segment.get('person_id')
            if not person_id or not isinstance(person_id, str):
                continue
            entry = stats.setdefault(
                person_id,
                {'conversation_count': 0, 'last_heard_at': None, 'talk_seconds': 0.0, 'auto_conversation_count': 0},
            )
            if not segment.get('speaker_match_source'):
                reviewed.add(person_id)
            if person_id not in seen:
                seen.add(person_id)
                entry['conversation_count'] += 1
                if heard_at and (entry['last_heard_at'] is None or heard_at > entry['last_heard_at']):
                    entry['last_heard_at'] = heard_at
            start, end = segment.get('start'), segment.get('end')
            if isinstance(start, (int, float)) and isinstance(end, (int, float)) and end > start:
                entry['talk_seconds'] += float(end - start)
        for person_id in seen - reviewed:
            stats[person_id]['auto_conversation_count'] += 1
    return stats


def apply_people_stats(people: List[Any], stats: Dict[str, Dict[str, Any]]) -> None:
    """Attach stats to ``models.other.Person`` objects and refresh their confidence reasons."""
    for person in people:
        entry = stats.get(person.id) or {}
        person.conversation_count = entry.get('conversation_count', 0)
        person.last_heard_at = entry.get('last_heard_at')
        person.talk_seconds = entry.get('talk_seconds', 0.0)
        person.auto_conversation_count = entry.get('auto_conversation_count', 0)
        person.refresh_confidence()


def collect_people_stats(
    conversations: Iterable[Dict[str, Any]],
    scan_cap: int = PEOPLE_STATS_SCAN_CAP,
    *,
    uid: Optional[str] = None,
    budget: Optional[ListReadBudget] = None,
) -> Dict[str, Dict[str, Any]]:
    """Aggregate stats over up to ``scan_cap`` rows of one newest-first conversation iterator.

    The reader owns paging: ``database.conversation_scan.iter_conversations``
    issues bounded cursor pages (never ``offset``), advances past invisible
    rows so a tombstone inside the window cannot end the scan early (#19908),
    and stops at its ``ListReadBudget`` — in which case the prefix it already
    yielded is the honest partial result.

    With ``uid``, the aggregate map is served from and stored to the
    generation-namespaced ``database.people_stats_cache``: the generation and
    entry resolve before the iterator is consumed, so a hit performs no
    Firestore reads. A truncated scan is never stored.
    """
    iterator = iter(conversations)
    try:
        generation = people_stats_cache.current_generation(uid) if uid is not None else None
        if uid is not None and generation is not None:
            cached = people_stats_cache.read_people_stats_cache(uid, generation, scan_cap)
            if cached is not None:
                return cached
        stats = aggregate_people_stats(islice(iterator, scan_cap))
        if uid is not None and generation is not None and budget is not None and not budget.truncated:
            if people_stats_cache.current_generation(uid) == generation:
                people_stats_cache.write_people_stats_cache(uid, generation, scan_cap, stats)
        return stats
    finally:
        close = getattr(iterator, 'close', None)
        if callable(close):
            close()
