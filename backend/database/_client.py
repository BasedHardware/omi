import hashlib
import json
import os
import uuid

from google.cloud import firestore
from google.oauth2 import service_account

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

# Extract project from credentials if not in env
if not project_id and os.environ.get('SERVICE_ACCOUNT_JSON'):
    try:
        creds = json.loads(os.environ.get('SERVICE_ACCOUNT_JSON', '{}'))
        project_id = creds.get('project_id') or creds.get('quota_project_id')
    except:
        pass

print(f"Initializing Firestore with project_id: {project_id}")

if project_id:
    db = firestore.Client(project=project_id)
else:
    db = firestore.Client()


_prod_db = None


def get_prod_db():
    """Get a Firestore client connected to the production project.

    Uses PROD_SERVICE_ACCOUNT_JSON env var for credentials.
    Raises RuntimeError if not configured.
    """
    global _prod_db
    if _prod_db is not None:
        return _prod_db

    prod_sa_json = os.environ.get('PROD_SERVICE_ACCOUNT_JSON')
    if not prod_sa_json:
        raise RuntimeError('PROD_SERVICE_ACCOUNT_JSON environment variable is not set')

    try:
        prod_creds_info = json.loads(prod_sa_json)
    except json.JSONDecodeError:
        cleaned = prod_sa_json.replace('\\', '')
        prod_creds_info = json.loads(cleaned)

    credentials = service_account.Credentials.from_service_account_info(prod_creds_info)
    prod_project_id = prod_creds_info.get('project_id')
    _prod_db = firestore.Client(project=prod_project_id, credentials=credentials)
    return _prod_db


def get_users_uid():
    users_ref = db.collection('users')
    return [str(doc.id) for doc in users_ref.stream()]


def document_id_from_seed(seed: str) -> uuid.UUID:
    """Avoid repeating the same data"""
    seed_hash = hashlib.sha256(seed.encode('utf-8')).digest()
    generated_uuid = uuid.UUID(bytes=seed_hash[:16], version=4)
    return str(generated_uuid)
