import math
import os
from datetime import datetime
from typing import Dict

import typesense

# Check if Typesense is configured
typesense_host = os.getenv('TYPESENSE_HOST')
typesense_port = os.getenv('TYPESENSE_HOST_PORT')
typesense_api_key = os.getenv('TYPESENSE_API_KEY')

if typesense_host and typesense_port and typesense_api_key:
    # Typesense is properly configured
    client = typesense.Client({
        'nodes': [{
            'host': typesense_host,
            'port': typesense_port,
            'protocol': 'https'
        }],
        'api_key': typesense_api_key,
        'connection_timeout_seconds': 2
    })
    print(f"Connected to Typesense at {typesense_host}:{typesense_port}")
else:
    # Typesense is not configured, create a mock client
    print("WARNING: Typesense is not configured. Using a mock client for development.")

    class MockTypesenseClient:
        def __init__(self):
            self.collections = {}

        def collections(self):
            return MockCollections(self.collections)

        def collection(self, name):
            if name not in self.collections:
                self.collections[name] = {}
            return MockCollection(self.collections, name)

    class MockCollections:
        def __init__(self, collections):
            self.collections = collections

        def create(self, schema):
            name = schema.get('name')
            if name not in self.collections:
                self.collections[name] = {}
            return {'name': name}

        def retrieve(self):
            return [{'name': name} for name in self.collections.keys()]

    class MockCollection:
        def __init__(self, collections, name):
            self.collections = collections
            self.name = name

        def documents(self):
            return MockDocuments(self.collections, self.name)

        def search(self, search_parameters):
            return {
                'found': 0,
                'hits': [],
                'page': 1,
                'request_params': search_parameters
            }

    class MockDocuments:
        def __init__(self, collections, collection_name):
            self.collections = collections
            self.collection_name = collection_name

        def create(self, document):
            return {'id': document.get('id')}

        def delete(self, document_id):
            return {'id': document_id}

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

        filter_by = f'userId:={uid} && deleted:=false'
        if not include_discarded:
            filter_by = filter_by + ' && discarded:=false'

        # Add date range filters if provided
        if start_date is not None:
            filter_by = filter_by + f' && created_at:>={start_date}'
        if end_date is not None:
            filter_by = filter_by + f' && created_at:<={end_date}'

        search_parameters = {
            'q': query,
            'query_by': 'structured, transcript_segments',
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
            'per_page': per_page
        }
    except Exception as e:
        raise Exception(f"Failed to search conversations: {str(e)}")
