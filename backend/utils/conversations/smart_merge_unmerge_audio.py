"""Exact undo audio ownership shared by administrative replay and source deletion."""

from typing import Any, Mapping

from database import conversations as conversations_db
from utils.cloud_tasks import is_audio_merge_dispatch_enabled
from utils.other.storage import (
    compute_audio_files_fingerprint,
    delete_cached_merged_audio,
    delete_copied_smart_merge_audio,
    enqueue_conversation_artifact_build,
    list_audio_chunks,
)


def copied_audio_filenames(uid: str, donor: Mapping[str, Any], survivor_id: str) -> list[str]:
    if donor.get('sync_bridge_audio_target') != survivor_id:
        return []
    return sorted({chunk['path'].rsplit('/', 1)[-1] for chunk in list_audio_chunks(uid, str(donor['id']))})


def rebuild_audio(uid: str, conversation_id: str) -> None:
    files = conversations_db.create_audio_files_from_chunks(uid, conversation_id)
    payload = [item.dict() for item in files]
    conversations_db.update_conversation(uid, conversation_id, {'audio_files': payload})
    delete_cached_merged_audio(uid, conversation_id)
    if payload and is_audio_merge_dispatch_enabled():
        enqueue_conversation_artifact_build(
            uid, conversation_id, compute_audio_files_fingerprint(payload), caller='smart_merge'
        )


def cleanup_restored_donor(uid: str, donor: Mapping[str, Any]) -> None:
    """Finish copied-audio removal before deleting a restored donor's originals.

    Do not checkpoint processing here: the undo worker still owns survivor refresh
    and terminal receipt convergence. Errors leave originals available for retry.
    """
    state = donor.get('smart_merge') or {}
    survivor_id = state.get('survivor_id')
    if state.get('role') != 'unmerged' or not survivor_id:
        return
    cid = str(donor['id'])
    filenames = state.get('unmerge_audio_filenames')
    if filenames is None:
        filenames = copied_audio_filenames(uid, donor, survivor_id)
    delete_copied_smart_merge_audio(uid, cid, survivor_id, filenames=filenames)
    survivor = conversations_db.get_conversation(uid, survivor_id)
    if survivor and not survivor.get('deleted'):
        rebuild_audio(uid, survivor_id)
