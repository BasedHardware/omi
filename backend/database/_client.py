from threading import Lock
from typing import Any

import os
from google.cloud import firestore

from database.document_ids import document_id_from_seed
from database.google_credentials import prepare_google_credentials

__all__ = ["db", "document_id_from_seed", "get_firestore_client", "get_firestore_client_dependency", "get_users_uid"]

_firestore_client = None
_firestore_client_lock = Lock()


def _build_firestore_client() -> Any:
    prepare_google_credentials()
    # Production safety: only override project/database when pointed at a local
    # Firestore emulator. Without FIRESTORE_EMULATOR_HOST set (i.e. real Firestore),
    # defer entirely to default resolution so env vars cannot repoint prod Firestore.
    if os.environ.get("FIRESTORE_EMULATOR_HOST"):
        project = os.environ.get("FIREBASE_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
        database = os.environ.get("FIRESTORE_DATABASE_ID")
        kwargs: dict[str, str] = {}
        if project:
            kwargs["project"] = project
        if database:
            kwargs["database"] = database
        return firestore.Client(**kwargs)
    return firestore.Client()


def get_firestore_client() -> Any:
    global _firestore_client

    if _firestore_client is None:
        with _firestore_client_lock:
            if _firestore_client is None:
                _firestore_client = _build_firestore_client()
    return _firestore_client


def get_firestore_client_dependency() -> Any:
    return get_firestore_client()


class _LazyFirestoreClient:
    # google-cloud-firestore ships no type stubs; attribute access proxies onto
    # the real client. Returning Any here is the SDK boundary; call sites narrow
    # the returned documents into typed dicts via the adapter pattern.
    def __getattr__(self, name: str) -> Any:
        return getattr(get_firestore_client(), name)


db = _LazyFirestoreClient()


def get_users_uid() -> list[str]:
    users_ref = get_firestore_client().collection('users')
    return [str(doc.id) for doc in users_ref.stream()]
