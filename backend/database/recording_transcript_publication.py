"""Owner-scoped, revision-bound product reads of a published recording."""

from google.cloud import firestore

from database._client import run_transactional
from database.account_deletion_policy import account_deletion_marker_blocks_access
from database.conversation_revisions import firestore_revision_datetime

FIELD = 'published_recording_transcript'
RESOLVED_RECORDING_ID = '_published_recording_id'


def belongs_to(row, uid, cid):
    return bool(row and row.get('id', cid) == cid and row.get('owner_uid', uid) == uid)


def read_snapshot(client, uid, recording_id, *, field_paths=None):
    """Read the mapping, erasure authority and exact transcript revision together."""
    owner = client.collection('users').document(uid)
    conversations = owner.collection('conversations')
    tombstones = owner.collection('deleted_conversations')

    @firestore.transactional
    def read(transaction):
        source = (
            conversations.document(recording_id)
            .get(
                transaction=transaction,
                field_paths=[FIELD, 'id', 'owner_uid', 'recording', 'deleted', 'sync_merged_into', 'is_locked'],
            )
            .to_dict()
        )
        if not belongs_to(source, uid, recording_id) or not source.get('recording') or source.get('is_locked'):
            return None
        binding = source.get(FIELD)
        if not isinstance(binding, dict):
            return None
        destination = binding.get('conversation_id')
        revision = binding.get('sync_content_revision')
        if (
            not isinstance(destination, str)
            or not destination
            or '/' in destination
            or len(destination.encode()) > 256
            or destination in {'.', '..'}
            or (destination.startswith('__') and destination.endswith('__'))
            or type(revision) is not int
            or revision <= 0
            or (source.get('deleted') and source.get('sync_merged_into') != destination)
        ):
            return None
        account = client.collection('account_deletions').document(uid).get(transaction=transaction)
        if account_deletion_marker_blocks_access(
            marker_exists=account.exists, raw_status=(account.to_dict() or {}).get('wipe_status')
        ):
            return None
        for cid in dict.fromkeys((recording_id, destination)):
            if tombstones.document(cid).get(transaction=transaction).exists:
                return None
        fields = (
            None if field_paths is None else list(dict.fromkeys([*field_paths, 'owner_uid', 'sync_content_revision']))
        )
        snapshot = conversations.document(destination).get(transaction=transaction, field_paths=fields)
        row = snapshot.to_dict()
        if (
            not belongs_to(row, uid, destination)
            or row.get('deleted')
            or row.get('is_locked')
            or type(row.get('sync_content_revision')) is not int
            or row['sync_content_revision'] != revision
            or not row.get('transcript_segments')
        ):
            return None
        row['id'] = destination
        row[RESOLVED_RECORDING_ID] = recording_id
        updated_at = firestore_revision_datetime(snapshot.update_time)
        if updated_at is not None:
            row['updated_at'] = updated_at
        return row

    return run_transactional(client, read, initial_transaction=client.transaction(read_only=True))
