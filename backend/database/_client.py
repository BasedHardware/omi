import hashlib
import json
import os
import uuid

from google.cloud import firestore
from google.auth.exceptions import DefaultCredentialsError

class MockFirestore:
    def collection(self, name):
        return MockCollection()

class MockCollection:
    def stream(self):
        return []
    def document(self, doc_id):
        return MockDocument(doc_id)
    def add(self, data):
        return None
    def where(self, field, op, value):
        return self

class MockDocument:
    def __init__(self, doc_id):
        self.id = doc_id
    def set(self, data):
        return None
    def get(self):
        return MockSnapshot()
    def update(self, data):
        return None
    def delete(self):
        return None

class MockSnapshot:
    exists = False
    def to_dict(self):
        return {}

if os.environ.get('SERVICE_ACCOUNT_JSON'):
    service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
    # create google-credentials.json
    with open('google-credentials.json', 'w') as f:
        json.dump(service_account_info, f)

try:
    db = firestore.Client()
except (DefaultCredentialsError, ValueError) as e:
    print(f"⚠️ Warning: Firestore connection failed ({e}). Using MockFirestore for local dev.")
    db = MockFirestore()


def get_users_uid():
    users_ref = db.collection('users')
    return [str(doc.id) for doc in users_ref.stream()]


def document_id_from_seed(seed: str) -> uuid.UUID:
    """Avoid repeating the same data"""
    seed_hash = hashlib.sha256(seed.encode('utf-8')).digest()
    generated_uuid = uuid.UUID(bytes=seed_hash[:16], version=4)
    return str(generated_uuid)
