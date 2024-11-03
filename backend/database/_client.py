import hashlib
import json
import os
import uuid
from google.cloud import firestore
from google.cloud.firestore_v1 import AsyncClient
from google.oauth2 import credentials
from google.auth import default

def get_google_cloud_project():
    """Get project ID from Google Cloud credentials"""
    try:
        # First check GOOGLE_APPLICATION_CREDENTIALS environment variable
        creds_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
        if creds_path and os.path.exists(creds_path):
            print(f"Firebase: Using credentials from GOOGLE_APPLICATION_CREDENTIALS: {creds_path}")
            with open(creds_path, 'r') as f:
                creds_data = json.load(f)
                return creds_data.get('quota_project_id')

        # Try to get credentials and project ID from the environment
        credentials, project_id = default()
        if project_id:
            print("Firebase: Using project ID from default credentials")
            return project_id

        # Last resort: Check for application default credentials file
        default_creds_path = os.path.expanduser('~/.config/gcloud/application_default_credentials.json')
        if os.path.exists(default_creds_path):
            print("Firebase: Using application default credentials")
            with open(default_creds_path, 'r') as f:
                creds_data = json.load(f)
                return creds_data.get('quota_project_id')
    except Exception as e:
        print(f"Firebase: Error reading credentials: {e}")
    return None

# Get project ID once to be used by all clients
project_id = None
if os.environ.get('SERVICE_ACCOUNT_JSON'):
    print("Firebase: Using SERVICE_ACCOUNT_JSON")
    service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
    project_id = service_account_info.get('project_id')
else:
    project_id = get_google_cloud_project()

if not project_id:
    raise EnvironmentError("Could not determine Google Cloud project ID. Please ensure either:\n"
                          "1. GOOGLE_APPLICATION_CREDENTIALS is set in .env\n"
                          "2. SERVICE_ACCOUNT_JSON is set in .env\n"
                          "3. You have run 'gcloud auth application-default login'")

print(f"Firebase: Initializing with project ID: {project_id}")

def get_firestore():
    """Get Firestore client"""
    return firestore.Client(project=project_id)

def get_async_firestore():
    """Get Async Firestore client"""
    return AsyncClient(project=project_id)

# Initialize default client
db = get_firestore()

def transaction(func):
    """Decorator to handle Firestore transactions"""
    def wrapper(*args, **kwargs):
        return db.transaction(lambda t: func(t, *args, **kwargs))
    return wrapper

def get_users_uid():
    users_ref = db.collection('users')
    return [str(doc.id) for doc in users_ref.stream()]

def document_id_from_seed(seed: str) -> str:
    """Avoid repeating the same data"""
    seed_hash = hashlib.sha256(seed.encode('utf-8')).digest()
    generated_uuid = uuid.UUID(bytes=seed_hash[:16], version=4)
    return str(generated_uuid)

# Export all needed functions
__all__ = [
    'db', 
    'get_firestore',
    'get_async_firestore',
    'transaction',
    'get_users_uid',
    'document_id_from_seed',
    'project_id'
]
