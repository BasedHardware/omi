import math
import os
from datetime import datetime
from typing import Dict

import typesense

import database.conversations as conversations_db

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
    include_trashed: bool = False,
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
        visible_ids = conversations_db.filter_visible_conversation_ids(
            uid,
            [item['document']['id'] for item in results['hits']],
            include_discarded=include_discarded,
            include_trashed=include_trashed,
        )
        visible_id_set = set(visible_ids)
        for item in results['hits']:
            doc = item['document']
            if doc['id'] not in visible_id_set:
                continue
            # Exclude locked conversations entirely to prevent inference leaks
            if doc.get('is_locked', False):
                continue
            doc['created_at'] = datetime.utcfromtimestamp(doc['created_at']).isoformat()
            doc['started_at'] = datetime.utcfromtimestamp(doc['started_at']).isoformat()
            doc['finished_at'] = datetime.utcfromtimestamp(doc['finished_at']).isoformat()
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
