import os
from typing import Dict

import typesense

client = typesense.Client({
    'nodes': [{
        'host': os.getenv('TYPESENSE_HOST'),
        'port': os.getenv('TYPESENSE_HOST_PORT'),
        'protocol': 'https'
    }],
    'api_key': os.getenv('TYPESENSE_API_KEY'),
    'connection_timeout_seconds': 2
})


def search_memories(
        uid: str,
        query: str,
        page: int = 1,
        per_page: int = 10,
) -> Dict:
    try:
        search_parameters = {
            'q': query,
            'query_by': 'structured, transcript_segments',
            'filter_by': 'userId := ' + uid,
            'sort_by': 'created_at:desc',
            'per_page': per_page,
            'page': page,
        }

        results = client.collections['memories'].documents.search(search_parameters)
        return {
            'items': results['hits'],
            'total': results['found'],
            'page': page,
            'per_page': per_page
        }
    except Exception as e:
        raise Exception(f"Failed to search conversations: {str(e)}")
