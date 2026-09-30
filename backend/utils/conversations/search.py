from typing import List, Optional, Tuple
from backend.database.conversations import ConversationsDB
from backend.models.conversation import Conversation


def browse_conversations_by_speaker(
    conversations_db: ConversationsDB,
    speaker_id: int,
    limit: int = 100,
    offset: int = 0,
    include_discarded: bool = False
) -> Tuple[List[Conversation], int]:
    """
    Browse conversations by speaker, handling tombstone rows correctly.
    Uses include_discarded=True server-side and filters client-side to avoid early termination.
    """
    scan_cap = offset + limit
    batch = 1000
    rows = []
    raw_offset = 0

    while len(rows) < scan_cap:
        request_size = min(batch, scan_cap - len(rows))
        page = conversations_db.get_conversations_by_speaker(
            speaker_id,
            request_size,
            raw_offset,
            include_discarded=True
        )
        rows.extend(page)
        if len(page) < request_size:
            break
        raw_offset += request_size

    # Filter out discarded/tombstone rows for the final result
    visible_rows = [row for row in rows if not getattr(row, 'discarded', False)]
    total = len(visible_rows)

    # Apply client-side offset and limit
    start = offset
    end = start + limit
    result = visible_rows[start:end]

    return result, total
