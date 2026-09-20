"""Replayable external bridge effects, always outside assignment transactions.

Ancestry is persisted with the transcript. Failure propagates to the sync job's
existing retry path; original audio and redirect tombstones are never removed.
"""

from _thread import LockType
from typing import NotRequired, TypedDict

from database import conversations as conversations_db
from database.sync_bridges import mark_sync_bridge_cleaned
from utils.sync.assignment_errors import SyncAssignmentSuperseded, SyncAssignmentConflict
from utils.conversations.merge_conversations import copy_sync_bridge_audio, retract_sync_bridge_source


class SyncBridgeAssignment(TypedDict):
    id: str
    sync_relevance: str
    sync_merged_from: NotRequired[list[str]]
    private_cloud_sync_enabled: NotRequired[bool]


class SyncSegmentResponse(TypedDict):
    new_memories: set[str]
    updated_memories: set[str]
    _merged: NotRequired[dict[str, str | None]]


def finish_sync_bridges(uid: str, conversation_id: str, *, audio_source_id: str | None = None) -> str:
    visited = set()
    while True:
        if conversation_id in visited:
            raise SyncAssignmentConflict('sync redirect cycle')
        visited.add(conversation_id)
        row = conversations_db.get_conversation(uid, conversation_id)
        if not row or (row.get('deleted') and not row.get('sync_merged_into')):
            raise SyncAssignmentSuperseded('sync conversation deleted during bridge')
        if row.get('sync_merged_into'):
            conversation_id = row['sync_merged_into']
            continue
        for source_id in row.get('sync_merged_from', []):
            source = conversations_db.get_conversation(uid, source_id)
            if not source or not source.get('deleted') or not source.get('sync_merged_into'):
                raise SyncAssignmentConflict('sync bridge source missing or not a tombstone')
            revision = source['sync_content_revision']
            needs_cleanup = source.get('sync_bridge_cleaned_revision') != revision
            audio_target = conversation_id if row.get('private_cloud_sync_enabled') else None
            needs_copy = audio_target and (
                needs_cleanup or source.get('sync_bridge_audio_target') != audio_target or source_id == audio_source_id
            )
            if needs_cleanup:
                retract_sync_bridge_source(uid, source_id)
            if needs_copy:
                # Invalidate an older copy receipt before late audio copying:
                # if copying fails, a retry without this worker's source hint
                # must still see pending audio work.
                if source_id == audio_source_id and source.get('sync_bridge_audio_target') == audio_target:
                    if not mark_sync_bridge_cleaned(uid, source_id, revision, None):
                        raise RuntimeError('sync bridge completion revision changed')
                copy_sync_bridge_audio(uid, source_id, conversation_id)
            if (needs_cleanup or needs_copy) and not mark_sync_bridge_cleaned(uid, source_id, revision, audio_target):
                raise RuntimeError('sync bridge completion revision changed')
        current = conversations_db.get_conversation(uid, conversation_id)
        if current and current.get('sync_merged_into'):
            conversation_id = current['sync_merged_into']
            continue
        if not current or current.get('deleted'):
            raise SyncAssignmentSuperseded('sync conversation deleted during bridge')
        return conversation_id


def finish_sync_segment(
    uid: str,
    assigned: SyncBridgeAssignment,
    response: SyncSegmentResponse,
    lock: LockType,
    language: str | None,
    *,
    audio_source_id: str | None = None,
) -> None:
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
            merged = response.setdefault('_merged', {})
            merged.pop(conversation_id, None)
            if assigned['sync_relevance'] == 'keep':
                merged[canonical_id] = language
