from datetime import datetime
from typing import List, Optional

import database.redis_db as redis_db
import database.conversations as conversations_db


def get_action_items_with_caching(
    uid: str,
    limit: int = 100,
    offset: int = 0,
    include_completed: bool = True,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> List[dict]:
    """
    Get action items with Redis caching.
    
    This function handles the caching logic and delegates to the database layer
    for actual data retrieval when cache misses occur.
    """
    # Try to get cached action items first
    cached_action_items = None
    if not start_date and not end_date:
        cached_action_items = redis_db.get_cached_user_action_items(uid)
    
    if cached_action_items is not None:
        # Parse datetime strings back to datetime objects for cached data
        for item in cached_action_items:
            if isinstance(item['conversation_created_at'], str):
                item['conversation_created_at'] = datetime.fromisoformat(
                    item['conversation_created_at'].replace('Z', '+00:00')
                )
        action_items = cached_action_items
    else:
        # Cache miss - fetch from database
        action_items = conversations_db.get_action_items(
            uid=uid,
            limit=5000,
            offset=0,
            include_completed=True,
            start_date=start_date,
            end_date=end_date,
        )
        
        # Cache the result if no date filters (cache full dataset)
        if not start_date and not end_date:
            redis_db.cache_user_action_items(uid, action_items)
    
    # Apply filtering (after caching to support all filter combinations)
    filtered_items = []
    for item in action_items:
        # Apply completion filter
        if not include_completed and item['completed']:
            continue
            
        # Apply date range filter (for cached data)
        if start_date and item['conversation_created_at'] < start_date:
            continue
        if end_date and item['conversation_created_at'] > end_date:
            continue
            
        filtered_items.append(item)
    
    # Apply pagination
    start_idx = offset
    end_idx = offset + limit
    
    return filtered_items[start_idx:end_idx]


def clear_action_items_cache(uid: str):
    """Clear cached action items for a user when they're modified."""
    redis_db.clear_user_action_items_cache(uid)


def should_clear_cache_for_conversation(conversation_data: dict) -> bool:
    """
    Check if a conversation update should trigger cache clearing.
    
    Returns True if the conversation has action items that would affect the cache.
    """
    structured = conversation_data.get('structured', {})
    return bool(structured.get('action_items'))