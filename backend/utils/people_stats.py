from typing import List, Dict, Any
from datetime import datetime
from backend.database.conversations import ConversationsDB


def aggregate_people_stats(
    conversations_db: ConversationsDB,
    uid: int,
    scan_cap: int = 10000,
    batch: int = 1000
) -> Dict[str, Any]:
    """
    Aggregates people stats for a given user by scanning their conversations.
    Uses include_discarded=True to ensure tombstone rows do not terminate pagination early.
    """
    rows = []
    offset = 0

    while len(rows) < scan_cap:
        request_size = min(batch, scan_cap - len(rows))
        page = conversations_db.get_conversations_without_photos(
            uid, request_size, offset, include_discarded=True
        )
        # Extend rows with raw page (including tombstones) to maintain offset alignment
        rows.extend(page)
        if len(page) < request_size:
            break
        offset += request_size

    # Filter out discarded/tombstone rows for stats aggregation
    visible_rows = [row for row in rows if not getattr(row, 'discarded', False)]

    people_stats: Dict[int, Dict[str, Any]] = {}

    for conv in visible_rows:
        speaker_id = conv.speaker_id
        if speaker_id not in people_stats:
            people_stats[speaker_id] = {
                "conversation_count": 0,
                "last_heard_at": None,
                "talk_seconds": 0
            }

        stats = people_stats[speaker_id]
        stats["conversation_count"] += 1

        if conv.created_at and (stats["last_heard_at"] is None or conv.created_at > stats["last_heard_at"]):
            stats["last_heard_at"] = conv.created_at

        if conv.duration:
            stats["talk_seconds"] += conv.duration

    return {
        "people": people_stats,
        "total_conversations": len(visible_rows)
    }


def collect_people_stats(
    conversations_db: ConversationsDB,
    uid: int,
    scan_cap: int = 10000,
    batch: int = 1000
) -> Dict[str, Any]:
    """
    Legacy wrapper for aggregate_people_stats. Maintained for backward compatibility.
    """
    return aggregate_people_stats(conversations_db, uid, scan_cap, batch)
