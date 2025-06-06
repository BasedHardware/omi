import hashlib
import json
import os
import uuid

from google.cloud import firestore

if os.environ.get('SERVICE_ACCOUNT_JSON'):
    service_account_json = os.environ["SERVICE_ACCOUNT_JSON"]
    if os.path.isfile(service_account_json):
    # If it's a file path, read the file
        with open(service_account_json, "r") as f:
            service_account_info = json.load(f)
    else:
        # If it's a JSON string, parse directly
        service_account_info = json.loads(service_account_json)

    # create google-credentials.json
    with open('google-credentials.json', 'w') as f:
        json.dump(service_account_info, f)

db = firestore.Client()


def get_users_uid():
    users_ref = db.collection('users')
    return [str(doc.id) for doc in users_ref.stream()]




def document_id_from_seed(seed: str) -> uuid.UUID:
    """Avoid repeating the same data"""
    seed_hash = hashlib.sha256(seed.encode('utf-8')).digest()
    generated_uuid = uuid.UUID(bytes=seed_hash[:16], version=4)
    return str(generated_uuid)
