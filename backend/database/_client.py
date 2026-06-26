import json
import os

from google.cloud import firestore

from database.document_ids import document_id_from_seed

if os.environ.get('SERVICE_ACCOUNT_JSON'):
    service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
    # create google-credentials.json
    with open('google-credentials.json', 'w') as f:
        json.dump(service_account_info, f)


def _firestore_client() -> firestore.Client:
    # Production safety: only override project/database when pointed at a local
    # Firestore emulator. Without FIRESTORE_EMULATOR_HOST set (i.e. real Firestore),
    # defer entirely to default resolution so behavior is byte-identical to the prior
    # `firestore.Client()` — env vars must never be able to repoint the prod client.
    if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        return firestore.Client()
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
