from threading import Lock

from google.cloud import firestore

from database.document_ids import document_id_from_seed
from database.google_credentials import prepare_google_credentials

_firestore_client = None
_firestore_client_lock = Lock()


def _build_firestore_client():
    prepare_google_credentials()
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
