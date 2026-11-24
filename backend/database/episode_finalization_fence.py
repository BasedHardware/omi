"""Deletion authority for episode finalization transactions."""

from database.account_deletion_marker import account_deletion_document
from database.firestore_read_metrics import FirestoreReadOutcome, FirestoreReadSite, record_document_read


class EpisodeFinalizationDeleted(RuntimeError):
    """The account or the source conversation has a deletion marker."""


def require_not_deleted(transaction, client, uid: str, cid: str, site: FirestoreReadSite) -> None:
    # Keep both authority reads in the write transaction, including reads of
    # absent documents. Every retry must recheck before it can stage writes.
    tombstone = client.collection('users').document(uid).collection('deleted_conversations').document(cid)
    for ref in (account_deletion_document(uid, firestore_client=client), tombstone):
        snapshot = ref.get(transaction=transaction)
        record_document_read(site, FirestoreReadOutcome.HIT if snapshot.exists else FirestoreReadOutcome.MISS)
        if snapshot.exists:
            raise EpisodeFinalizationDeleted
