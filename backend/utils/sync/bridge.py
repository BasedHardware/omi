"""Replayable external bridge effects, always outside assignment transactions.

Ancestry is persisted with the transcript. Failure propagates to the sync job's
existing retry path; original audio and redirect tombstones are never removed.
"""

from database import conversations as conversations_db
from utils.conversations.merge_conversations import _copy_audio_chunks_for_merge, _delete_conversation_and_related_data


def finish_sync_bridges(uid: str, conversation_id: str) -> str:
    visited = set()
    while True:
        if conversation_id in visited:
            raise ValueError('sync redirect cycle')
        visited.add(conversation_id)
        row = conversations_db.get_conversation(uid, conversation_id)
        if not row or (row.get('deleted') and not row.get('sync_merged_into')):
            raise ValueError('sync conversation deleted during bridge')
        if row.get('sync_merged_into'):
            conversation_id = row['sync_merged_into']
            continue
        ancestors = row.get('sync_merged_from', [])
        for source_id in ancestors:
            _delete_conversation_and_related_data(uid, source_id, retain_capture=True)
        if ancestors and row.get('private_cloud_sync_enabled'):
            # Copies are idempotent. Keep the originals, including late uploads;
            # every finishing job traverses the current redirect and copies again.
            _copy_audio_chunks_for_merge(uid, [{'id': cid} for cid in ancestors], conversation_id, strict=True)
        current = conversations_db.get_conversation(uid, conversation_id)
        if current and current.get('sync_merged_into'):
            conversation_id = current['sync_merged_into']
            continue
        if not current or current.get('deleted'):
            raise ValueError('sync conversation deleted during bridge')
        return conversation_id
