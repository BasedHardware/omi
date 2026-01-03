import hashlib
import json
import os
import uuid
from typing import Dict, Any, List

from google.cloud import firestore
from google.auth.exceptions import DefaultCredentialsError
from google.cloud.firestore_v1.base_query import FieldFilter, BaseCompositeFilter

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
        pass 

class MockCollection:
    def __init__(self, db, name, parent_doc=None):
        self.db = db
        self.name = name
        self.parent_doc = parent_doc
        self._filters = []
        self._limit = None
        self._offset = 0
        self._order_by = []

    def _get_data(self):
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

    def _apply_filters(self, docs):
        filtered_docs = []
        for doc in docs:
            data = doc._get_data()
            if not data: continue
            
            match = True
            for f in self._filters:
                field, op, value = f
                # Handle dot notation for nested fields
                val = data
                for part in field.split('.'):
                    if isinstance(val, dict):
                        val = val.get(part)
                    else:
                        val = None
                        break
                
                if op == '==' and val != value: match = False
                elif op == '!=' and val == value: match = False
                elif op == '>' and not (val > value if val is not None else False): match = False
                elif op == '>=' and not (val >= value if val is not None else False): match = False
                elif op == '<' and not (val < value if val is not None else False): match = False
                elif op == '<=' and not (val <= value if val is not None else False): match = False
                elif op == 'in' and val not in value: match = False
                elif op == 'array_contains' and (val is None or value not in val): match = False
                
                if not match: break
            
            if match: filtered_docs.append(doc)
        return filtered_docs

    def stream(self):
        data = self._get_data()
        docs = [MockDocument(self.db, self, doc_id) for doc_id in data.keys()]
        
        # Filter
        docs = self._apply_filters(docs)
        
        # Sort
        for field, direction in self._order_by:
            reverse = direction == 'DESCENDING'
            docs.sort(key=lambda x: x._get_data().get(field, ""), reverse=reverse)

        # Offset & Limit
        if self._offset:
            docs = docs[self._offset:]
        if self._limit:
            docs = docs[:self._limit]
            
        return docs
    
    def get(self):
        return [doc.get() for doc in self.stream()]

    def where(self, *args, **kwargs):
        # Support both .where("field", "==", "value") and .where(filter=FieldFilter(...))
        if 'filter' in kwargs:
            f = kwargs['filter']
            if isinstance(f, FieldFilter):
                self._filters.append((f.field.field_path, f.op, f.value))
            elif isinstance(f, BaseCompositeFilter):
                # Basic composite handling (AND only for now)
                for sub_filter in f.filters:
                    if isinstance(sub_filter, FieldFilter):
                        self._filters.append((sub_filter.field.field_path, sub_filter.op, sub_filter.value))
        elif len(args) == 3:
            self._filters.append(args)
        return self

    def limit(self, count):
        self._limit = count
        return self
    
    def offset(self, count):
        self._offset = count
        return self

    def order_by(self, field, direction='ASCENDING'):
        self._order_by.append((field, direction))
        return self
    
    def count(self):
        return MockCountQuery(self)

class MockCountQuery:
    def __init__(self, query):
        self.query = query
    
    def get(self):
        # Return a list containing a list containing an object with a value property
        # Firestore count query structure: [[Aggregation(value=count)]]
        count = len(self.query.stream())
        return [[MockAggregation(count)]]

class MockAggregation:
    def __init__(self, value):
        self.value = value

class MockDocument:
    def __init__(self, db, collection, doc_id):
        self.db = db
        self.collection = collection
        self.id = doc_id

    def _get_data(self):
        col_data = self.collection._get_data()
        if self.id not in col_data:
             return None
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

    @property
    def reference(self):
        return self

    def collection(self, name):
        current = self._get_data()
        if current is None:
             self.set({})
             current = self._get_data()
        
        if '__collections__' not in current:
            current['__collections__'] = {}
            
        return MockSubCollection(self.db, name, current['__collections__'])

class MockSubCollection(MockCollection):
    def __init__(self, db, name, storage):
        super().__init__(db, name) # Init base filtering/sorting
        self.storage = storage 

    def _get_data(self):
        if self.name not in self.storage:
            self.storage[self.name] = {}
        return self.storage[self.name]

class MockSnapshot:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None
        self.reference = None 

    def to_dict(self):
        if self._data and '__collections__' in self._data:
            d = self._data.copy()
            del d['__collections__']
            return d
        return self._data or {}

if os.environ.get('SERVICE_ACCOUNT_JSON'):
    service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
    with open('google-credentials.json', 'w') as f:
        json.dump(service_account_info, f)

try:
    db = firestore.Client()
except (DefaultCredentialsError, ValueError, ImportError) as e:
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
