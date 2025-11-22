import hashlib
import json
import os
import uuid

from google.cloud import firestore

# Set up Google Cloud credentials
if os.environ.get('SERVICE_ACCOUNT_JSON'):
    service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
    # create google-credentials.json
    with open('google-credentials.json', 'w') as f:
        json.dump(service_account_info, f)

# Ensure GOOGLE_APPLICATION_CREDENTIALS is set
if not os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'):
    # Try to find google-credentials.json in current directory or backend directory
    possible_paths = [
        'google-credentials.json',
        os.path.join(os.path.dirname(__file__), '..', 'google-credentials.json'),
        os.path.join(os.getcwd(), 'google-credentials.json')
    ]
    for path in possible_paths:
        if os.path.exists(path):
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = os.path.abspath(path)
            break

db = firestore.Client()


def get_users_uid():
    users_ref = db.collection('users')
    return [str(doc.id) for doc in users_ref.stream()]


def document_id_from_seed(seed: str) -> uuid.UUID:
    """Avoid repeating the same data"""
    seed_hash = hashlib.sha256(seed.encode('utf-8')).digest()
    generated_uuid = uuid.UUID(bytes=seed_hash[:16], version=4)
    return str(generated_uuid)
