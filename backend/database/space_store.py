"""Firestore per-space UoW. Bodies must be pure and restartable, with all reads first.

No buffering or commit hooks: SDK read-before-write ordering applies to the whole
body. Standalone repositories retain domain-specific transaction retry policies.
"""

from typing import Any, Callable, TypeVar

from google.cloud import firestore

from database._client import get_firestore_client, run_transactional
from database.firestore_transaction_retry import run_with_transaction_contention_retry
from database.folders import FirestoreFolders
from database.people import FirestorePeople
from database.ports.base import SpaceTx

T = TypeVar('T')


class FirestoreSpaceTx:
    def __init__(self, space_id: str, client: Any, transaction: Any):
        self.space_id = space_id
        self.folders = FirestoreFolders(space_id, firestore_client=client, transaction=transaction)
        self.people = FirestorePeople(space_id, firestore_client=client, transaction=transaction)


class FirestoreSpaceStore:
    def __init__(self, space_id: str, *, firestore_client: Any = None):
        self.space_id = space_id
        self.client = firestore_client if firestore_client is not None else get_firestore_client()
        self.folders = FirestoreFolders(space_id, firestore_client=self.client)
        self.people = FirestorePeople(space_id, firestore_client=self.client)

    def run(self, body: Callable[[SpaceTx], T]) -> T:
        @firestore.transactional
        def apply(transaction):
            return body(FirestoreSpaceTx(self.space_id, self.client, transaction))

        return run_transactional(self.client, apply, attempts=3)

    def run_with_contention_retry(self, body: Callable[[SpaceTx], T], *, operation_name: str) -> T:
        @firestore.transactional
        def apply(transaction):
            return body(FirestoreSpaceTx(self.space_id, self.client, transaction))

        return run_with_transaction_contention_retry(self.client.transaction, apply, operation_name=operation_name)
