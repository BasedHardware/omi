"""Bounded related-task input for conversation notes and deduplication."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import database.action_items as action_items_db
from database.vector_db import find_similar_action_items

logger = logging.getLogger(__name__)


def _dedup_excluded_conversation_ids(conversation: Any) -> set:
    """The conversation's own id plus any merge-source ids. Items from these
    conversations must never be dedup candidates: on reprocess/merge they are
    this conversation's previous items — the LLM would suppress re-extracting
    them, and the save step then deletes them, silently losing the tasks."""
    excluded = {getattr(conversation, 'id', None)}
    external_data = getattr(conversation, 'external_data', None) or {}
    merge_metadata = external_data.get('merge_metadata') or {}
    excluded.update(merge_metadata.get('source_conversation_ids') or [])
    excluded.discard(None)
    return excluded


def fetch_dedup_candidates_for_query(uid: str, query: str, conversation: Any = None) -> List[Dict[str, Any]]:
    if not query.strip():
        return []

    excluded_conversation_ids = _dedup_excluded_conversation_ids(conversation) if conversation else set()

    try:
        similar = find_similar_action_items(uid, query, threshold=0.6, limit=10)
        if not similar:
            return []

        items = action_items_db.get_action_items_by_ids(uid, [s['action_item_id'] for s in similar])
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)

        eligible: List[Dict[str, Any]] = []
        for item in items:
            if item.get('completed', False):
                continue
            if item.get('conversation_id') in excluded_conversation_ids:
                continue
            last_active = item.get('updated_at') or item.get('created_at')
            if last_active is None or last_active < cutoff:
                continue
            eligible.append(item)

        logger.info(
            f'dedup_candidates uid={uid} similar={len(similar)} '
            f'eligible={len(eligible)} top_score={similar[0]["score"]}'
        )
        return eligible
    except Exception as e:
        logger.exception(f'_fetch_dedup_candidates failed uid={uid}: {e}')
        return []
