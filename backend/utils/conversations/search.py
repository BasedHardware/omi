import math
import os
from datetime import datetime
from typing import Dict, List

# Check if Typesense is configured
typesense_host = os.getenv('TYPESENSE_HOST')
typesense_port = os.getenv('TYPESENSE_HOST_PORT')
typesense_api_key = os.getenv('TYPESENSE_API_KEY')

# Create a mock Typesense implementation for development or when Typesense is not configured
class MockTypesenseClient:
    def __init__(self):
        self.collections_data = {}
        print("Using MockTypesenseClient - search will return empty results")

    def collections(self):
        return MockCollections(self.collections_data)

    def collection(self, name):
        if name not in self.collections_data:
            self.collections_data[name] = {}
        return MockCollection(self.collections_data, name)

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
        # Add documents attribute directly to make it easier to use
        self.documents = MockDocuments(self.collections, self.name)

    def search(self, search_parameters):
        return {
            'found': 0,
            'hits': [],
            'page': search_parameters.get('page', 1),
            'request_params': search_parameters
        }

class MockDocuments:
    def __init__(self, collections, collection_name):
        self.collections = collections
        self.collection_name = collection_name

    def create(self, document):
        doc_id = document.get('id', 'mock_id')
        self.collections.setdefault(self.collection_name, {})
        self.collections[self.collection_name][doc_id] = document
        return {'id': doc_id}

    def delete(self, document_id):
        if self.collection_name in self.collections and document_id in self.collections[self.collection_name]:
            del self.collections[self.collection_name][document_id]
        return {'id': document_id}

    def search(self, search_parameters):
        return {
            'found': 0,
            'hits': [],
            'page': search_parameters.get('page', 1),
            'request_params': search_parameters
        }

# Only import typesense if credentials are available
if typesense_host and typesense_port and typesense_api_key:
    try:
        import typesense
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

        # Create default collections if needed
        try:
            collections = client.collections().retrieve()
            collection_names = [c['name'] for c in collections]
            if 'conversations' not in collection_names:
                # Create conversations collection with appropriate schema
                schema = {
                    'name': 'conversations',
                    'fields': [
                        {'name': 'userId', 'type': 'string', 'facet': True},
                        {'name': 'deleted', 'type': 'bool', 'facet': True},
                        {'name': 'discarded', 'type': 'bool', 'facet': True},
                        {'name': 'created_at', 'type': 'int64', 'facet': True},
                        {'name': 'transcript_segments', 'type': 'string[]'},
                        {'name': 'structured', 'type': 'string'}
                    ]
                }
                client.collections().create(schema)
                print("Created 'conversations' collection in Typesense")
        except Exception as e:
            print(f"WARNING: Could not create default collections in Typesense: {e}")
    except ImportError:
        print("WARNING: typesense module not installed. Using mock client.")
        client = MockTypesenseClient()
    except Exception as e:
        print(f"WARNING: Could not connect to Typesense: {e}. Using mock client.")
        client = MockTypesenseClient()
else:
    # Typesense is not configured
    print("INFO: Typesense is not configured. Search functionality will use mock implementation.")
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

        # Safely access the collection and handle potential errors
        try:
            collection = client.collection('conversations')
            results = collection.documents.search(search_parameters)
        except AttributeError:
            # If client is a mock or collections don't exist yet
            try:
                results = client.collections.create({
                    'name': 'conversations',
                    'fields': [
                        {'name': 'userId', 'type': 'string', 'facet': True},
                        {'name': 'deleted', 'type': 'bool', 'facet': True},
                        {'name': 'discarded', 'type': 'bool', 'facet': True},
                        {'name': 'created_at', 'type': 'int64', 'facet': True},
                        {'name': 'transcript_segments', 'type': 'string[]'},
                        {'name': 'structured', 'type': 'string'}
                    ]
                })
                results = {'hits': [], 'found': 0, 'page': page}
            except:
                results = {'hits': [], 'found': 0, 'page': page}

        memories = []
        for item in results.get('hits', []):
            doc = item.get('document', {})
            # Convert timestamps to ISO format
            for ts_field in ['created_at', 'started_at', 'finished_at']:
                if ts_field in doc and isinstance(doc[ts_field], (int, float)):
                    doc[ts_field] = datetime.utcfromtimestamp(doc[ts_field]).isoformat()
            memories.append(doc)

        return {
            'items': memories,
            'total_pages': math.ceil(results.get('found', 0) / per_page),
            'current_page': page,
            'per_page': per_page
        }
    except Exception as e:
        print(f"Error in search_conversations: {e}")
        # Return empty result set on error
        return {
            'items': [],
            'total_pages': 0,
            'current_page': page,
            'per_page': per_page
        }
