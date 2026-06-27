import json
import os

from google.cloud import firestore

from database.document_ids import document_id_from_seed

if os.environ.get('SERVICE_ACCOUNT_JSON'):
    service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
    # create google-credentials.json
    with open('google-credentials.json', 'w') as f:
        json.dump(service_account_info, f)

db = firestore.Client()


def get_users_uid():
    users_ref = db.collection('users')
    return [str(doc.id) for doc in users_ref.stream()]
