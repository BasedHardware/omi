import math
import os
from datetime import datetime
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
        memories = []
        for item in results['hits']:
            item['document']['created_at'] = datetime.utcfromtimestamp(item['document']['created_at']).isoformat()
            item['document']['started_at'] = datetime.utcfromtimestamp(item['document']['started_at']).isoformat()
            item['document']['finished_at'] = datetime.utcfromtimestamp(item['document']['finished_at']).isoformat()
            memories.append(item['document'])
        return {
            'items': memories,
            'total_pages': math.ceil(results['found'] / per_page),
            'current_page': page,
            'per_page': per_page
        }
    except Exception as e:
        raise Exception(f"Failed to search conversations: {str(e)}")
