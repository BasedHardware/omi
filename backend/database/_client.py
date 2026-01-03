import hashlib
import json
import os
import uuid
from typing import Dict, Any

from google.cloud import firestore
from google.auth.exceptions import DefaultCredentialsError

# Constants for local persistence
DATA_DIR = '/app/data'
DB_FILE = os.path.join(DATA_DIR, 'firestore_mock.json')

class PersistentMockFirestore:
    _instance = None
    _data: Dict[str, Dict[str, Any]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PersistentMockFirestore, cls).__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        if os.path.exists(DB_FILE):
            try:
                with open(DB_FILE, 'r') as f:
                    self._data = json.load(f)
                print(f"✅ Loaded persistent mock data from {DB_FILE}")
            except Exception as e:
                print(f"⚠️ Failed to load mock data: {e}")
                self._data = {}
        else:
            self._data = {}

    def _save(self):
        if not os.path.exists(DATA_DIR):
            try:
                os.makedirs(DATA_DIR)
            except OSError:
                # Might fail if not permission, but inside Docker usually OK
                pass
        try:
            with open(DB_FILE, 'w') as f:
                json.dump(self._data, f, default=str, indent=2)
        except Exception as e:
            print(f"⚠️ Failed to save mock data: {e}")

    def collection(self, name):
        if name not in self._data:
            self._data[name] = {}
        return MockCollection(self, name)

    def batch(self):
        return MockBatch(self)

class MockBatch:
    def __init__(self, db):
        self.db = db
    
    def set(self, ref, data):
        ref.set(data)
    
    def update(self, ref, data):
        ref.update(data)
    
    def delete(self, ref):
        ref.delete()
    
    def commit(self):
        pass # Changes happen immediately in this simple mock

class MockCollection:
    def __init__(self, db, name, parent_doc=None):
        self.db = db
        self.name = name
        self.parent_doc = parent_doc  # For subcollections

    def _get_data(self):
        # Handle subcollections: parent_doc.data[col_name]
        if self.parent_doc:
            if self.name not in self.parent_doc._get_data():
                 self.parent_doc._get_data()[self.name] = {}
            return self.parent_doc._get_data()[self.name]
        return self.db._data[self.name]

    def document(self, doc_id=None):
        if doc_id is None:
            doc_id = str(uuid.uuid4())
        return MockDocument(self.db, self, doc_id)

    def add(self, data, doc_id=None):
        if doc_id is None:
            doc_id = str(uuid.uuid4())
        doc = self.document(doc_id)
        doc.set(data)
        return None, doc

    def stream(self):
        # Return all docs in this collection
        data = self._get_data()
        return [MockDocument(self.db, self, doc_id) for doc_id in data.keys()]
    
    def where(self, *args, **kwargs):
        # Basic mock support for chaining, doesn't actually filter yet
        return self

    def limit(self, count):
        return self

    def order_by(self, field, direction=None):
        return self

class MockDocument:
    def __init__(self, db, collection, doc_id):
        self.db = db
        self.collection = collection
        self.id = doc_id

    def _get_data(self):
        col_data = self.collection._get_data()
        if self.id not in col_data:
             return None # Does not exist
        return col_data[self.id]

    def set(self, data):
        col_data = self.collection._get_data()
        col_data[self.id] = data
        self.db._save()

    def update(self, data):
        current = self._get_data()
        if current:
            current.update(data)
            self.db._save()

    def get(self):
        data = self._get_data()
        return MockSnapshot(self.id, data)

    def delete(self):
        col_data = self.collection._get_data()
        if self.id in col_data:
            del col_data[self.id]
            self.db._save()

    def collection(self, name):
        # Subcollections require nested storage structure
        # Simplified: storing subcollections in a special field '_collections' inside the doc data?
        # Or simpler: Just return a dummy collection for now to prevent crashes, 
        # as implementing deep nested persistence in one file is complex.
        # But wait, we want persistence. 
        # Let's try to store it in the doc data under `__collections__` key
        current = self._get_data()
        if current is None:
             # Create doc implicitly? No, usually errors. 
             # But for mock, let's allow it
             self.set({})
             current = self._get_data()
        
        if '__collections__' not in current:
            current['__collections__'] = {}
            
        return MockSubCollection(self.db, name, current['__collections__'])

class MockSubCollection(MockCollection):
    def __init__(self, db, name, storage):
        self.db = db
        self.name = name
        self.storage = storage # Reference to the dict holding this collection's data

    def _get_data(self):
        if self.name not in self.storage:
            self.storage[self.name] = {}
        return self.storage[self.name]

class MockSnapshot:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None
        self.reference = None # Placeholder

    def to_dict(self):
        if self._data and '__collections__' in self._data:
            # Hide internal storage
            d = self._data.copy()
            del d['__collections__']
            return d
        return self._data or {}

if os.environ.get('SERVICE_ACCOUNT_JSON'):
    service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
    # create google-credentials.json
    with open('google-credentials.json', 'w') as f:
        json.dump(service_account_info, f)

try:
    db = firestore.Client()
except (DefaultCredentialsError, ValueError) as e:
    print(f"⚠️ Warning: Firestore connection failed ({e}). Using PersistentMockFirestore for local dev.")
    db = PersistentMockFirestore()


def get_users_uid():
    users_ref = db.collection('users')
    return [str(doc.id) for doc in users_ref.stream()]


def document_id_from_seed(seed: str) -> uuid.UUID:
    """Avoid repeating the same data"""
    seed_hash = hashlib.sha256(seed.encode('utf-8')).digest()
    generated_uuid = uuid.UUID(bytes=seed_hash[:16], version=4)
    return str(generated_uuid)