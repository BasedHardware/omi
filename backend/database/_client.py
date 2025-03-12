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

# Read the project ID from google-credentials.json
project_id = None
try:
    with open('google-credentials.json', 'r') as f:
        credentials = json.load(f)
        # Try to get project_id, if not available use quota_project_id
        project_id = credentials.get('project_id') or credentials.get('quota_project_id')
except Exception as e:
    print(f"Error reading google-credentials.json: {e}")

if not project_id:
    raise EnvironmentError("Project ID could not be determined from google-credentials.json")

# Initialize Firestore with explicit project ID
db = firestore.Client(project=project_id)


def get_users_uid():
    users_ref = db.collection('users')
    return [str(doc.id) for doc in users_ref.stream()]




def document_id_from_seed(seed: str) -> uuid.UUID:
    """Avoid repeating the same data"""
    seed_hash = hashlib.sha256(seed.encode('utf-8')).digest()
    generated_uuid = uuid.UUID(bytes=seed_hash[:16], version=4)
    return str(generated_uuid)
