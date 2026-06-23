import hashlib
import json
import os
import uuid

from google.cloud import firestore

if os.environ.get('SERVICE_ACCOUNT_JSON'):
    service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
    # create google-credentials.json
    with open('google-credentials.json', 'w') as f:
        json.dump(service_account_info, f)


def _firestore_client() -> firestore.Client:
    project = os.environ.get("FIREBASE_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    database = os.environ.get("FIRESTORE_DATABASE_ID")
    kwargs: dict[str, str] = {}
    if project:
        kwargs["project"] = project
    if database:
        kwargs["database"] = database
    return firestore.Client(**kwargs)


db = _firestore_client()


def get_users_uid():
    users_ref = db.collection('users')
    return [str(doc.id) for doc in users_ref.stream()]


def document_id_from_seed(seed: str) -> uuid.UUID:
    """Avoid repeating the same data"""
    seed_hash = hashlib.sha256(seed.encode('utf-8')).digest()
    generated_uuid = uuid.UUID(bytes=seed_hash[:16], version=4)
    return str(generated_uuid)
