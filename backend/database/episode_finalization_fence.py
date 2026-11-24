"""Deletion authority for episode finalization transactions."""

from database.account_deletion_marker import account_deletion_document
from database.account_deletion_policy import account_deletion_marker_blocks_access
from database.firestore_read_metrics import FirestoreReadOutcome, FirestoreReadSite, record_document_read

# Each fence site splits into its account-marker read and its conversation-tombstone
# read, so account hit/miss is marked/unmarked at decision time. Counters only.
_SPLIT = {
    site: (FirestoreReadSite(f'{site.value}_account'), FirestoreReadSite(f'{site.value}_tombstone'))
    for site in (
        FirestoreReadSite.EPISODE_FINALIZATION_UPDATE_FENCE,
        FirestoreReadSite.EPISODE_FINALIZATION_MOMENT_FENCE,
        FirestoreReadSite.EPISODE_FINALIZATION_CLOSE_FENCE,
        FirestoreReadSite.EPISODE_FINALIZATION_MEMO_FENCE,
    )
}


class EpisodeFinalizationDeleted(RuntimeError):
    """The account or the source conversation has a deletion marker."""


def require_not_deleted(transaction, client, uid: str, cid: str, site: FirestoreReadSite) -> None:
    # Keep both authority reads in the write transaction, including reads of
    # absent documents. Every retry must recheck before it can stage writes.
    account_site, tombstone_site = _SPLIT.get(site, (site, site))
    account = account_deletion_document(uid, firestore_client=client).get(transaction=transaction)
    record_document_read(account_site, FirestoreReadOutcome.HIT if account.exists else FirestoreReadOutcome.MISS)
    if account_deletion_marker_blocks_access(
        marker_exists=account.exists, raw_status=(account.to_dict() or {}).get('wipe_status')
    ):
        raise EpisodeFinalizationDeleted

    tombstone = (
        client.collection('users')
        .document(uid)
        .collection('deleted_conversations')
        .document(cid)
        .get(transaction=transaction)
    )
    record_document_read(tombstone_site, FirestoreReadOutcome.HIT if tombstone.exists else FirestoreReadOutcome.MISS)
    if tombstone.exists:
        raise EpisodeFinalizationDeleted
