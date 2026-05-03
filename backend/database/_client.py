import base64
import hashlib
import json
import os
import uuid

from google.cloud import firestore
from google.oauth2 import service_account


def _load_service_account_info() -> dict | None:
    """Resolve the service-account credential dict from one of two env vars.

    Coolify (and other deploy targets) sometimes ship credentials as raw JSON
    in ``SERVICE_ACCOUNT_JSON`` and sometimes base64-encoded in
    ``SERVICE_ACCOUNT_JSON_BASE64`` (the base64 variant avoids quote-escaping
    issues with multi-line dashboards). Try the plain variant first, fall
    back to base64. Returns ``None`` when neither is set, leaving Application
    Default Credentials (ADC) to handle local dev / GCP-native deploys.
    """
    raw = os.environ.get('SERVICE_ACCOUNT_JSON')
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Handle escaped JSON from Coolify (quotes are escaped as \")
            return json.loads(raw.replace('\\', ''))
    encoded = os.environ.get('SERVICE_ACCOUNT_JSON_BASE64')
    if encoded:
        decoded = base64.b64decode(encoded).decode('utf-8')
        return json.loads(decoded)
    return None


service_account_info = _load_service_account_info()
if service_account_info is not None:
    # create google-credentials.json — relative path resolves to the
    # container's WORKDIR (/app for both backend and pusher Dockerfiles),
    # which is exactly where GOOGLE_APPLICATION_CREDENTIALS points.
    with open('google-credentials.json', 'w') as f:
        json.dump(service_account_info, f)

# Initialize Firestore client
# For authorized_user credentials, we need to explicitly set the project
project_id = os.environ.get('GOOGLE_CLOUD_PROJECT') or os.environ.get('GCP_PROJECT_ID')

# Fall back to the project_id baked into the service account credentials.
# Using the already-decoded service_account_info means this works whether the
# credential came from SERVICE_ACCOUNT_JSON or SERVICE_ACCOUNT_JSON_BASE64.
if not project_id and service_account_info is not None:
    project_id = service_account_info.get('project_id') or service_account_info.get('quota_project_id')

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
