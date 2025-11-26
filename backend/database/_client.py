import hashlib
import json
import os
import uuid

from google.cloud import firestore

if os.environ.get('SERVICE_ACCOUNT_JSON'):
    json_str = os.environ["SERVICE_ACCOUNT_JSON"]
    try:
        service_account_info = json.loads(json_str)
    except json.JSONDecodeError:
        # Handle escaped JSON from Coolify (quotes are escaped as \")
        cleaned = json_str.replace('\\', '')
        service_account_info = json.loads(cleaned)
    # create google-credentials.json
    with open('google-credentials.json', 'w') as f:
        json.dump(service_account_info, f)

# Initialize Firestore client
# For authorized_user credentials, we need to explicitly set the project
project_id = os.environ.get('GOOGLE_CLOUD_PROJECT') or os.environ.get('GCP_PROJECT_ID')
if project_id:
    db = firestore.Client(project=project_id)
else:
    db = firestore.Client()


def get_users_uid():
    users_ref = db.collection('users')
    return [str(doc.id) for doc in users_ref.stream()]


def document_id_from_seed(seed: str) -> uuid.UUID:
    """Avoid repeating the same data"""
    seed_hash = hashlib.sha256(seed.encode('utf-8')).digest()
    generated_uuid = uuid.UUID(bytes=seed_hash[:16], version=4)
    return str(generated_uuid)
