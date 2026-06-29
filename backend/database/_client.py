import json
import os
from threading import Lock

from google.cloud import firestore

from database.document_ids import document_id_from_seed

_firestore_client = None
_firestore_client_lock = Lock()
_credentials_file_lock = Lock()
_credentials_file_prepared = False


def _prepare_service_account_credentials():
    global _credentials_file_prepared

    if _credentials_file_prepared:
        return

    with _credentials_file_lock:
        if _credentials_file_prepared:
            return

        service_account_json = os.environ.get('SERVICE_ACCOUNT_JSON')
        if service_account_json:
            service_account_info = json.loads(service_account_json)
            with open('google-credentials.json', 'w') as f:
                json.dump(service_account_info, f)

        _credentials_file_prepared = True


def _build_firestore_client():
    _prepare_service_account_credentials()
    return firestore.Client()


def get_firestore_client():
    global _firestore_client

    if _firestore_client is None:
        with _firestore_client_lock:
            if _firestore_client is None:
                _firestore_client = _build_firestore_client()
    return _firestore_client


def get_firestore_client_dependency():
    return get_firestore_client()


class _LazyFirestoreClient:
    def __getattr__(self, name):
        return getattr(get_firestore_client(), name)


db = _LazyFirestoreClient()


def get_users_uid():
    users_ref = get_firestore_client().collection('users')
    return [str(doc.id) for doc in users_ref.stream()]
