import math
import os
from datetime import datetime
from typing import Dict

import typesense

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
            doc['created_at'] = datetime.utcfromtimestamp(doc['created_at']).isoformat()
            doc['started_at'] = datetime.utcfromtimestamp(doc['started_at']).isoformat()
            doc['finished_at'] = datetime.utcfromtimestamp(doc['finished_at']).isoformat()
            memories.append(doc)
        # Cannot compute exact total from Typesense since is_locked is not a filter field.
        # Use page-level signal: if Typesense returned a full page, more may exist.
        has_more = len(results['hits']) >= per_page
        return {
            'items': memories,
            'total_pages': page + 1 if has_more else page,
            'current_page': page,
            'per_page': per_page,
        }
    except Exception as e:
        raise Exception(f"Failed to search conversations: {str(e)}")
