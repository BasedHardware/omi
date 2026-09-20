"""Replayable external bridge effects, always outside assignment transactions.

Ancestry is persisted with the transcript. Failure propagates to the sync job's
existing retry path; original audio and redirect tombstones are never removed.
"""

from database import conversations as conversations_db
from database.sync_bridges import mark_sync_bridge_cleaned
from utils.conversations.merge_conversations import _copy_audio_chunks_for_merge, _delete_conversation_and_related_data


def finish_sync_bridges(uid: str, conversation_id: str, *, audio_source_id: str | None = None) -> str:
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
        for source_id in row.get('sync_merged_from', []):
            source = conversations_db.get_conversation(uid, source_id)
            if not source or not source.get('deleted') or not source.get('sync_merged_into'):
                raise ValueError('sync bridge source missing or not a tombstone')
            revision = source['sync_content_revision']
            needs_cleanup = source.get('sync_bridge_cleaned_revision') != revision
            audio_target = conversation_id if row.get('private_cloud_sync_enabled') else None
            needs_copy = audio_target and (
                needs_cleanup or source.get('sync_bridge_audio_target') != audio_target or source_id == audio_source_id
            )
            if needs_cleanup:
                _delete_conversation_and_related_data(uid, source_id, retain_capture=True)
            if needs_copy:
                _copy_audio_chunks_for_merge(uid, [{'id': source_id}], conversation_id, strict=True)
            if (needs_cleanup or needs_copy) and not mark_sync_bridge_cleaned(uid, source_id, revision, audio_target):
                raise RuntimeError('sync bridge completion revision changed')
        current = conversations_db.get_conversation(uid, conversation_id)
        if current and current.get('sync_merged_into'):
            conversation_id = current['sync_merged_into']
            continue
        if not current or current.get('deleted'):
            raise ValueError('sync conversation deleted during bridge')
        return conversation_id


def finish_sync_segment(uid, assigned, response, lock, language, *, audio_source_id=None):
    """One completion point, after audio persistence; follow a concurrent bridge."""
    if not assigned.get('sync_merged_from') and not assigned.get('private_cloud_sync_enabled'):
        return
    conversation_id = assigned['id']
    canonical_id = finish_sync_bridges(uid, conversation_id, audio_source_id=audio_source_id)
    if canonical_id != conversation_id:
        with lock:
            response['new_memories'].discard(conversation_id)
            response['updated_memories'].discard(conversation_id)
            response['updated_memories'].add(canonical_id)
            response.setdefault('_merged', {}).pop(conversation_id, None)
            if assigned['sync_relevance'] == 'keep':
                response['_merged'][canonical_id] = language
