"""Reads that feed a projection.

Kept apart from `evidence.py` so packet assembly stays pure and testable without a database:
this module is the only place projections touch persistence, and it does no shaping beyond
passing documents through.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from database import action_items as action_items_db
from database import conversations as conversations_db
from database import goals as goals_db
from database import projections as projections_db
from utils.projections.evidence import WINDOW_DAYS, EvidencePacket, assemble_packet

# Read ceilings. Assembly caps the packet again; these bound the query itself so an unusually
# dense week cannot pull an unbounded page out of Firestore.
CONVERSATION_READ_LIMIT = 200
ACTION_ITEM_READ_LIMIT = 100


def read_evidence(uid: str, *, now: Optional[datetime] = None, window_days: int = WINDOW_DAYS) -> EvidencePacket:
    """Assemble the evidence packet for `uid` from the last `window_days`."""
    now = now or datetime.now(timezone.utc)
    start_date = now - timedelta(days=window_days)

    conversations = conversations_db.get_conversations(
        uid,
        limit=CONVERSATION_READ_LIMIT,
        start_date=start_date,
        end_date=now,
    )
    # Open action items are read without a date window: age is the signal, so an item that has
    # been open for a month is more interesting than one opened yesterday, not less.
    action_items = action_items_db.get_action_items(uid, completed=False, limit=ACTION_ITEM_READ_LIMIT)
    goal = goals_db.get_user_goal(uid)

    return assemble_packet(
        conversations=conversations,
        action_items=action_items,
        goal=goal,
        now=now,
        window_days=window_days,
    )


def read_previous_projections(uid: str, limit: int) -> List[Dict[str, Any]]:
    """The most recent projections, newest first, for continuity across a series."""
    if limit <= 0:
        return []
    return projections_db.get_projections(uid, limit=limit)
