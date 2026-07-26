from threading import Lock
from typing import Any

import os
from google.cloud import firestore

from database.document_ids import document_id_from_seed
from database.google_credentials import prepare_google_credentials

__all__ = [
    "db",
    "delete_collection_recursive",
    "document_id_from_seed",
    "get_firestore_client",
    "get_users_uid",
]

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


class _LazyFirestoreClient:
    # google-cloud-firestore ships no type stubs; attribute access proxies onto
    # the real client. Returning Any here is the SDK boundary; call sites narrow
    # the returned documents into typed dicts via the adapter pattern.
    def __getattr__(self, name: str) -> Any:
        return getattr(get_firestore_client(), name)


db = _LazyFirestoreClient()


def delete_collection_recursive(collection_ref: Any, *, client: Any, batch_size: int = 450) -> None:
    """Delete every document under a collection, descending into nested subcollections first.

    Firestore does not cascade: deleting a document leaves its subcollections in
    place as data no query can reach (the parent no longer exists, so it is not
    returned by a collection query either). Any caller that deletes a parent
    document must purge its children through this helper.
    """
    while True:
        docs = list(collection_ref.limit(batch_size).stream())
        if not docs:
            return

        for doc in docs:
            for sub in doc.reference.collections():
                delete_collection_recursive(sub, client=client, batch_size=batch_size)

        batch = client.batch()
        for doc in docs:
            batch.delete(doc.reference)
        batch.commit()

        if len(docs) < batch_size:
            return


def get_users_uid() -> list[str]:
    users_ref = get_firestore_client().collection('users')
    return [str(doc.id) for doc in users_ref.stream()]
