import logging
import math
import os
from datetime import datetime
from typing import Dict, List

import typesense

logger = logging.getLogger(__name__)

client = typesense.Client(
    {
        'nodes': [{'host': os.getenv('TYPESENSE_HOST'), 'port': os.getenv('TYPESENSE_HOST_PORT'), 'protocol': 'https'}],
        'api_key': os.getenv('TYPESENSE_API_KEY'),
        'connection_timeout_seconds': 2,
    }
)


def search_conversations(
    uid: str,
    query: str,
    page: int = 1,
    per_page: int = 10,
    include_discarded: bool = True,
    start_date: int = None,
    end_date: int = None,
) -> Dict:
    try:

        filter_by = f'userId:={uid}'
        if not include_discarded:
            filter_by = filter_by + ' && discarded:=false'

        # Add date range filters if provided
        if start_date is not None:
            filter_by = filter_by + f' && created_at:>={start_date}'
        if end_date is not None:
            filter_by = filter_by + f' && created_at:<={end_date}'

        search_parameters = {
            'q': query,
            'query_by': 'structured.overview, structured.title',
            'filter_by': filter_by,
            'sort_by': 'created_at:desc',
            'per_page': per_page,
            'page': page,
        }

        results = client.collections['conversations'].documents.search(search_parameters)
        memories = []
        for item in results['hits']:
            doc = item['document']
            # Exclude locked conversations entirely to prevent inference leaks
            if doc.get('is_locked', False):
                continue
            try:
                # Convert all three into locals first, then assign, so a hit that fails partway is
                # never left half-converted.
                created_at = datetime.utcfromtimestamp(doc['created_at']).isoformat()
                started_at = datetime.utcfromtimestamp(doc['started_at']).isoformat()
                finished_at = datetime.utcfromtimestamp(doc['finished_at']).isoformat()
            except (KeyError, TypeError, ValueError, OverflowError, OSError) as e:
                # One malformed/legacy indexed doc (missing, null, or out-of-range timestamp) must not
                # 500 the whole search page; skip just this hit (mirrors the per-record tolerance in
                # routers/memories.py get_memories).
                logger.warning("search_conversations skipping malformed hit uid=%s id=%s: %s", uid, doc.get('id'), e)
                continue
            doc['created_at'] = created_at
            doc['started_at'] = started_at
            doc['finished_at'] = finished_at
            memories.append(doc)
        # Derive total_pages only from visible (unlocked) items to prevent inference leaks.
        # is_locked is not a Typesense filter field, so exact global count is unavailable.
        has_more = len(memories) >= per_page
        return {
            'items': memories,
            'total_pages': page + 1 if has_more else page,
            'current_page': page,
            'per_page': per_page,
        }
    except Exception as e:
        raise Exception(f"Failed to search conversations: {str(e)}")


def keyword_search_conversation_ids(
    uid: str,
    query: str,
    limit: int = 5,
    start_date: int = None,
    end_date: int = None,
) -> List[str]:
    """Typesense keyword search returning only conversation ids, for hybrid (keyword + vector) retrieval.

    Fail-open: any search error returns [] so callers can fall back to vector-only results.
    """
    try:
        results = search_conversations(
            uid=uid,
            query=query,
            per_page=limit,
            include_discarded=False,
            start_date=start_date,
            end_date=end_date,
        )
        return [item['id'] for item in results.get('items', []) if item.get('id')]
    except Exception as e:
        logger.warning("keyword_search_conversation_ids failed for uid=%s, falling back to vector-only: %s", uid, e)
        return []


def merge_conversation_search_ids(keyword_ids: List[str], vector_ids: List[str]) -> List[str]:
    """Merge keyword and vector search results, keyword hits first (exact text matches), deduplicated."""
    return list(keyword_ids) + [cid for cid in vector_ids if cid not in keyword_ids]
