import hashlib
import json
import os
import uuid
import pathlib

from google.cloud import firestore

if os.environ.get('SERVICE_ACCOUNT_JSON'):
    service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
    # create google-credentials.json
    with open('google-credentials.json', 'w') as f:
        json.dump(service_account_info, f)

# Check if GOOGLE_APPLICATION_CREDENTIALS is set and expand the path if needed
credentials_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
if credentials_path and '~' in credentials_path:
    # Expand the tilde to the user's home directory
    credentials_path = os.path.expanduser(credentials_path)
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
    print(f"Expanded credentials path to: {credentials_path}")

# Read the project ID from credentials file
project_id = None
try:
    # First try to read from google-credentials.json if it exists
    if os.path.exists('google-credentials.json'):
        with open('google-credentials.json', 'r') as f:
            credentials = json.load(f)
            project_id = credentials.get('project_id') or credentials.get('quota_project_id')

    # If not found, try to read from the application default credentials
    if not project_id and credentials_path and os.path.exists(credentials_path):
        with open(credentials_path, 'r') as f:
            credentials = json.load(f)
            project_id = credentials.get('project_id') or credentials.get('quota_project_id')

    if project_id:
        print(f"Using project ID: {project_id}")
    else:
        print("Project ID not found in credentials files")
except Exception as e:
    print(f"Error reading credentials file: {e}")

if not project_id:
    raise EnvironmentError("Project ID could not be determined from credentials files. Please ensure your Google Cloud credentials are properly set up.")

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
