import math
import os
from datetime import datetime
from typing import Dict

import typesense

from typesense.exceptions import ConfigError

class MockTypesenseClient:
    def __init__(self):
        self.collections = MockCollections()

class MockCollections:
    def __getitem__(self, key):
        return MockDocuments()

class MockDocuments:
    @property
    def documents(self):
        return self

    def search(self, params):
        print(f"Mock search with params: {params}")
        return {'hits': [], 'found': 0}

try:
    if os.getenv('TYPESENSE_API_KEY'):
        client = typesense.Client(
            {
                'nodes': [{'host': os.getenv('TYPESENSE_HOST'), 'port': os.getenv('TYPESENSE_HOST_PORT'), 'protocol': 'https'}],
                'api_key': os.getenv('TYPESENSE_API_KEY'),
                'connection_timeout_seconds': 2,
            }
        )
    else:
        print("⚠️ Warning: TYPESENSE_API_KEY not set. Using MockTypesenseClient.")
        client = MockTypesenseClient()
except (ConfigError, ValueError, KeyError) as e:
    print(f"⚠️ Warning: Typesense init failed ({e}). Using MockTypesenseClient.")
    client = MockTypesenseClient()


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
            item['document']['created_at'] = datetime.utcfromtimestamp(item['document']['created_at']).isoformat()
            item['document']['started_at'] = datetime.utcfromtimestamp(item['document']['started_at']).isoformat()
            item['document']['finished_at'] = datetime.utcfromtimestamp(item['document']['finished_at']).isoformat()
            memories.append(item['document'])
        return {
            'items': memories,
            'total_pages': math.ceil(results['found'] / per_page),
            'current_page': page,
            'per_page': per_page,
        }
    except Exception as e:
        raise Exception(f"Failed to search conversations: {str(e)}")
