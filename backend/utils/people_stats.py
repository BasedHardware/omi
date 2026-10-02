"""Per-person conversation stats for the People list.

Computed on demand from the newest conversations rather than denormalized onto each conversation: the
scan is bounded (PEOPLE_STATS_SCAN_CAP), so counts for a very long history cover the most recent
conversations only.
"""

from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional

PEOPLE_STATS_SCAN_CAP = 1000
PEOPLE_STATS_BATCH = 100


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
    fetch_page: Callable[[int, int], List[Dict[str, Any]]],
    scan_cap: int = PEOPLE_STATS_SCAN_CAP,
    batch: int = PEOPLE_STATS_BATCH,
) -> Dict[str, Dict[str, Any]]:
    """Aggregate stats over up to ``scan_cap`` newest conversations; ``fetch_page(limit, offset)``."""
    rows: List[Dict[str, Any]] = []
    while len(rows) < scan_cap:
        request_size = min(batch, scan_cap - len(rows))
        page = fetch_page(request_size, len(rows))
        rows.extend(page)
        if len(page) < request_size:
            break
    return aggregate_people_stats(rows)
