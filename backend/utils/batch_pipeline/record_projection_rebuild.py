"""Socket-independent playback discovery and bounded original validation; no custody authority."""

from typing import Literal

from config import audio_archive
from database import conversations as conversations_db, conversation_tombstones, record_projection_rebuild as jobs
from database._client import get_firestore_client
from utils.other import storage, raw_audio_read
from utils.other.relay_archive_recovery import validated_uncovered_packs
from utils.other.relay_recovery_metrics import SAMPLES


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


def projected_chunks(uid, cid, chunks, *, validate_raw=False, diagnostics=None, reuse_manifest_bodies=False):
    if not audio_archive.admitted(uid, 'READ'):
        return chunks
    if validate_raw:
        raw = validated_uncovered_packs(storage.get_private_cloud_sync_bucket(), uid, cid, chunks)
        if diagnostics is not None:
            diagnostics['samples'] = sum(item['span']['samples'] for item in raw)
        return sorted([*chunks, *raw], key=lambda chunk: chunk['timestamp'])
    packs = storage.list_packs(
        storage.get_private_cloud_sync_bucket(), uid, cid, reuse_manifest_bodies=reuse_manifest_bodies
    )
    return sorted([*chunks, *raw_audio_read.uncovered_raw_packs(packs, chunks)], key=lambda chunk: chunk['timestamp'])


def discover(
    uid, cid, *, strict_raw=False, fallback=None, validate_raw=False, diagnostics=None, reuse_manifest_bodies=False
):
    """Snapshot before LIST; share the full rebuild with pusher's live cache."""
    owner = conversations_db.get_conversation_raw_snapshot(uid, cid, field_paths=['audio_files', 'deleted'])
    if owner is None or owner.get('deleted'):
        return None
    expected = owner.get('audio_files') or []
    chunks = storage.list_audio_chunks(uid, cid, source_identity=True, include_archive=False)
    raw_complete = True
    try:
        listed = (
            projected_chunks(uid, cid, chunks, validate_raw=True, diagnostics=diagnostics)
            if validate_raw
            else projected_chunks(uid, cid, chunks, reuse_manifest_bodies=reuse_manifest_bodies and not strict_raw)
        )
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

    None retains debt for incomplete discovery. Uncovered originals are decoded
    under fixed budgets; no audio object is created, rewritten or deleted.
    """
    if projection_owner_gone(uid, cid):
        return False
    if not jobs.preflight_projection(uid, cid):
        return None  # Privacy/consent holds forbid original reads and retain debt.
    for _ in range(2):
        diagnostics = {}
        discovery = discover(uid, cid, strict_raw=True, validate_raw=True, diagnostics=diagnostics)
        if discovery is None:
            return False
        expected, _, files, _ = discovery
        if not files:
            return 'no_objects'
        try:
            applied = jobs.apply_projection(
                uid, cid, {'audio_files': [af.model_dump() for af in files]}, expected_audio_files=expected
            )
            if applied is True:
                SAMPLES.labels(stage='recovered').inc(diagnostics.get('samples', 0))
            return applied
        except conversations_db.AudioFilesChanged:
            continue
    raise RuntimeError('audio projection refresh exhausted')
