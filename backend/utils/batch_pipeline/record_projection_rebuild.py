"""Socket-independent playback metadata discovery; no audio decoding or custody."""

from typing import Literal

from config import audio_archive
from database import conversations as conversations_db, conversation_tombstones, record_projection_rebuild as jobs
from database._client import get_firestore_client
from utils.other import storage, raw_audio_read


def projection_owner_gone(uid: str, conversation_id: str) -> bool:
    """Deletion intent and hard absence; the cold commit rechecks privacy atomically."""
    if conversation_tombstones.is_deleted(uid, conversation_id):
        return True
    doc = (
        get_firestore_client()
        .collection('users')
        .document(uid)
        .collection('conversations')
        .document(conversation_id)
        .get()
    )
    return not doc.exists


def projected_chunks(uid, cid, chunks):
    if not audio_archive.admitted(uid, 'READ'):
        return chunks
    packs = storage.list_packs(storage.get_private_cloud_sync_bucket(), uid, cid)
    return sorted([*chunks, *raw_audio_read.uncovered_raw_packs(packs, chunks)], key=lambda chunk: chunk['timestamp'])


def discover(uid, cid, *, strict_raw=False, fallback=None):
    """Snapshot before LIST; share the full rebuild with pusher's live cache."""
    owner = conversations_db.get_conversation_raw_snapshot(uid, cid, field_paths=['audio_files', 'deleted'])
    if owner is None or owner.get('deleted'):
        return None
    expected = owner.get('audio_files') or []
    chunks = storage.list_audio_chunks(uid, cid, source_identity=True, include_archive=False)
    raw_complete = True
    try:
        listed = projected_chunks(uid, cid, chunks)
    except Exception:
        if strict_raw:
            raise
        raw_complete, listed = False, chunks
        if fallback is not None:
            fallback(
                component='pusher',
                from_mode='raw_audio',
                to_mode='encoded_audio_projection',
                reason='other',
                outcome='degraded',
            )
    files = conversations_db.create_audio_files_from_chunks(uid, cid, listed_chunks=listed)
    return expected, chunks, files, raw_complete


def rebuild(uid: str, cid: str) -> bool | Literal['no_objects'] | None:
    """Full metadata rebuild with deletion/privacy and prior projection CAS.

    None retains debt for incomplete discovery. No PCM or audio object is read,
    created, rewritten or deleted; raw coverage uses the existing pack index.
    """
    if projection_owner_gone(uid, cid):
        return False
    for _ in range(2):
        discovery = discover(uid, cid, strict_raw=True)
        if discovery is None:
            return False
        expected, _, files, _ = discovery
        if not files:
            return 'no_objects'
        try:
            return jobs.apply_projection(
                uid, cid, {'audio_files': [af.model_dump() for af in files]}, expected_audio_files=expected
            )
        except conversations_db.AudioFilesChanged:
            continue
    raise RuntimeError('audio projection refresh exhausted')
