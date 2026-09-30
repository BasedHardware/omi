"""Firestore CRUD for the `screen_frames` conversation subcollection.

This is a conversation subcollection exactly like `photos` in
database/conversations.py: same transactional-write-checks-parent-exists
shape, same batch-delete-before-parent-delete requirement (Firestore does
not cascade subcollection deletes), same @prepare_for_read / @prepare_for_write
/ @set_data_protection_level decorator stack. The difference is that a
screen frame's bytes live in GCS, not inline base64 here — the composite
functions that also touch GCS live in utils/screen_frames/store.py, not in
this module, matching how delete_conversation_audio_files (GCS) is called
alongside conversations_db.delete_conversation (Firestore-only) rather
than folded into it.

It lives in its own module, split out of database/conversations.py, purely
because that file is already over the repo's product-file line-count
ratchet (.github/scripts/check_product_file_line_count_ratchet.py,
THRESHOLD 1500) and may not grow further without a declared exception. This
block was one cohesive, self-contained addition — the natural thing to
extract rather than excuse.
"""

import copy
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from google.cloud import firestore

from utils import encryption
from ._client import db, get_firestore_client
from .conversations import conversations_collection
from .helpers import set_data_protection_level, prepare_for_write, prepare_for_read

screen_frames_subcollection = 'screen_frames'
_ENCRYPTED_TEXT_FIELDS = ('caption', 'screen_summary')


def _prepare_screen_frame_for_write(data: Dict[str, Any], uid: str, level: str) -> Dict[str, Any]:
    data = copy.deepcopy(data)
    data['data_protection_level'] = level
    if level == 'enhanced':
        # screen_summary and visible_participant_names are the notes evidence the
        # judge read off the pixels; they get the caption's protection.
        for field in _ENCRYPTED_TEXT_FIELDS:
            if isinstance(data.get(field), str):
                data[field] = encryption.encrypt(data[field], uid)
        if isinstance(data.get('visible_participant_names'), list):
            data['visible_participant_names'] = [
                encryption.encrypt(name, uid) if isinstance(name, str) else name
                for name in data['visible_participant_names']
            ]
    return data


def _decrypt_tolerant(value: Any, uid: str) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return encryption.decrypt(value, uid)
    except Exception:
        # Already decrypted, or never encrypted — same tolerance as _prepare_photo_for_read.
        return value


def _prepare_screen_frame_for_read(frame_data: Dict[str, Any], uid: str) -> Dict[str, Any]:
    # Typed to `prepare_for_read`'s actual contract — it maps over documents that already exist,
    # so it never hands this None. `_prepare_photo_for_read` declares Optional on both sides and
    # is not flagged only because the typecheck runs over changed files; copying that here would
    # be copying a latent mismatch. The falsy guard stays for an empty document, but it returns
    # the same shape it was given rather than None, which is what the caller is annotated for.
    if not frame_data:
        return frame_data
    data = copy.deepcopy(frame_data)
    level = data.get('data_protection_level')
    if level == 'enhanced':
        for field in _ENCRYPTED_TEXT_FIELDS:
            if field in data:
                data[field] = _decrypt_tolerant(data[field], uid)
        if isinstance(data.get('visible_participant_names'), list):
            data['visible_participant_names'] = [
                _decrypt_tolerant(name, uid) for name in data['visible_participant_names']
            ]
    return data


@prepare_for_read(decrypt_func=_prepare_screen_frame_for_read)
def get_conversation_screen_frames(uid: str, conversation_id: str) -> List[Dict[str, Any]]:
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    frames_ref = conversation_ref.collection(screen_frames_subcollection)
    return [doc.to_dict() for doc in frames_ref.stream()]


@set_data_protection_level(data_arg_name='frames')
@prepare_for_write(data_arg_name='frames', prepare_func=_prepare_screen_frame_for_write)
def store_conversation_screen_frames(
    uid: str,
    conversation_id: str,
    frames: List[Dict[str, Any]],
    *,
    firestore_client: Any = None,
) -> bool:
    """Upsert (merge) one or more screen_frame records.

    Used both for a brand-new write from the writer boundary and for an
    enforcement pass rewriting the role/rank of already-persisted survivors —
    merge=True means either use is a no-op on fields not present in the
    passed dict. Transactional and checks the parent conversation still
    exists, exactly like store_conversation_photos.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    user_ref = client.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    frames_ref = conversation_ref.collection(screen_frames_subcollection)
    transaction = client.transaction()

    @firestore.transactional
    def _store(transaction) -> bool:
        conversation_snapshot = conversation_ref.get(transaction=transaction)
        if not getattr(conversation_snapshot, 'exists', False):
            return False
        for frame in frames:
            frame_id = frame['id']
            frame_ref = frames_ref.document(frame_id)
            transaction.set(frame_ref, frame, merge=True)
        transaction.update(conversation_ref, {'has_content': True})
        return True

    return _store(transaction)


def delete_conversation_screen_frame_doc(uid: str, conversation_id: str, frame_id: str) -> bool:
    """Delete a single screen_frame Firestore document. GCS-agnostic — see
    utils.screen_frames.store.delete_screen_frame for the composite delete
    that also removes the GCS objects and cached signed URLs.
    """
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    frame_ref = conversation_ref.collection(screen_frames_subcollection).document(frame_id)
    snapshot = frame_ref.get()
    if not getattr(snapshot, 'exists', False):
        return False
    frame_ref.delete()
    return True


def delete_conversation_screen_frame_docs(uid: str, conversation_id: str) -> int:
    """Delete every screen_frame Firestore document for a conversation.

    IMPORTANT: Firestore does NOT cascade delete subcollections when you
    delete a parent document — this must run before the parent conversation
    doc is deleted, same contract as delete_conversation_photos.
    GCS-agnostic — see utils.screen_frames.store.delete_conversation_screen_frames.
    """
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    frames_ref = conversation_ref.collection(screen_frames_subcollection)

    frames = frames_ref.stream()
    deleted_count = 0
    batch = db.batch()
    batch_count = 0

    for frame_doc in frames:
        batch.delete(frame_doc.reference)
        batch_count += 1
        deleted_count += 1
        if batch_count >= 500:
            batch.commit()
            batch = db.batch()
            batch_count = 0

    if batch_count > 0:
        batch.commit()

    return deleted_count


# ---------------------------------------------------------------------------
# Per-environment frame state.
#
# Dev and prod backends share this Firestore but write screen-frame bytes to
# different buckets. Every frame doc records the bucket its bytes live in
# (`storage_bucket`), and the conversation-level markers (revision, the
# adjudication stamp, the selection fingerprint) are kept per bucket, so one
# environment's pass can never hide, sign, or skip the other's. Docs and
# markers written before this split carry no bucket; only dev ever had egress,
# so they belong to LEGACY_SCREEN_FRAMES_BUCKET and keep their original
# top-level fields as that bucket's state.
# ---------------------------------------------------------------------------

LEGACY_SCREEN_FRAMES_BUCKET = 'based-hardware-dev-screen-frames'
_ENV_STATE_FIELD = 'screen_frames_env_state'
_LEGACY_STATE_FIELDS = {
    'revision': 'screen_frames_revision',
    'adjudicated_at': 'screen_frames_adjudicated_at',
    'selection_fingerprint': 'screen_frames_selection_fingerprint',
}


def frame_storage_bucket(frame: Dict[str, Any]) -> str:
    """The bucket holding a frame doc's bytes; legacy docs belong to dev."""
    bucket = frame.get('storage_bucket')
    return bucket if isinstance(bucket, str) and bucket else LEGACY_SCREEN_FRAMES_BUCKET


def own_frames(frames: Iterable[Dict[str, Any]], bucket: Optional[str]) -> List[Dict[str, Any]]:
    """Frames whose recorded bucket is ``bucket``; none when no bucket is configured."""
    if not bucket:
        return []
    return [frame for frame in frames if frame_storage_bucket(frame) == bucket]


# Durable record of screen-frame bytes one environment could not delete from
# another environment's bucket (dev and prod lack access to each other's). The
# owning environment drains the records for its bucket.
_CLEANUP_COLLECTION = 'screen_frame_cleanup'


def record_screen_frame_cleanup(
    bucket: str, uid: str, conversation_id: str, frame_id: str, object_paths: List[str]
) -> None:
    doc_id = f'{_state_key(bucket)}__{frame_id}'
    get_firestore_client().collection(_CLEANUP_COLLECTION).document(doc_id).set(
        {
            'bucket': bucket,
            'uid': uid,
            'conversation_id': conversation_id,
            'frame_id': frame_id,
            'object_paths': list(object_paths),
            'created_at': datetime.now(timezone.utc),
        }
    )


def list_screen_frame_cleanups(bucket: str, limit: int) -> List[Dict[str, Any]]:
    query = get_firestore_client().collection(_CLEANUP_COLLECTION).where('bucket', '==', bucket).limit(limit)
    return [{**(doc.to_dict() or {}), 'id': doc.id} for doc in query.stream()]


def delete_screen_frame_cleanup(doc_id: str) -> None:
    get_firestore_client().collection(_CLEANUP_COLLECTION).document(doc_id).delete()


def _state_key(bucket: str) -> str:
    return re.sub(r'[^A-Za-z0-9_]', '_', bucket)


def _state_payload(bucket: str, field: str, value: Any) -> Dict[str, Any]:
    if bucket == LEGACY_SCREEN_FRAMES_BUCKET:
        return {_LEGACY_STATE_FIELDS[field]: value}
    return {_ENV_STATE_FIELD: {_state_key(bucket): {field: value}}}


def _rpc_bounds(rpc_timeout: Optional[float]) -> Dict[str, Any]:
    # A caller with a deadline gets one attempt within it: no library retry past the bound.
    return {'timeout': rpc_timeout, 'retry': None} if rpc_timeout is not None else {}


def _read_state(conversation_ref: Any, bucket: str, field: str, rpc_timeout: Optional[float] = None) -> Any:
    bounds = _rpc_bounds(rpc_timeout)
    if bucket == LEGACY_SCREEN_FRAMES_BUCKET:
        snapshot = conversation_ref.get(field_paths=[_LEGACY_STATE_FIELDS[field]], **bounds)
        return (snapshot.to_dict() or {}).get(_LEGACY_STATE_FIELDS[field])
    snapshot = conversation_ref.get(field_paths=[_ENV_STATE_FIELD], **bounds)
    state = (snapshot.to_dict() or {}).get(_ENV_STATE_FIELD)
    scoped = state.get(_state_key(bucket)) if isinstance(state, dict) else None
    return scoped.get(field) if isinstance(scoped, dict) else None


def _conversation_ref(uid: str, conversation_id: str) -> Any:
    return db.collection('users').document(uid).collection(conversations_collection).document(conversation_id)


def get_conversation_screen_frame_doc(uid: str, conversation_id: str, frame_id: str) -> Dict[str, Any] | None:
    """One frame doc's raw fields (no decryption) — enough to check its bucket."""
    snapshot = _conversation_ref(uid, conversation_id).collection(screen_frames_subcollection).document(frame_id).get()
    if not getattr(snapshot, 'exists', False):
        return None
    return snapshot.to_dict() or {}


def bump_conversation_screen_frames_revision(uid: str, conversation_id: str, *, bucket: str) -> int:
    """Atomically increment and return this bucket's ConversationScreenFrameSet
    revision counter. Called once per enforcement pass (contract §7) — never per read.
    """
    conversation_ref = _conversation_ref(uid, conversation_id)
    conversation_ref.set(_state_payload(bucket, 'revision', firestore.Increment(1)), merge=True)
    return int(_read_state(conversation_ref, bucket, 'revision') or 0)


def get_conversation_screen_frames_revision(uid: str, conversation_id: str, *, bucket: str) -> int:
    return int(_read_state(_conversation_ref(uid, conversation_id), bucket, 'revision') or 0)


def mark_conversation_screen_frames_adjudicated(
    uid: str, conversation_id: str, *, selection_fingerprint: str, bucket: str
) -> datetime:
    """Record that an adjudication pass ran for this conversation, whatever it decided.

    Distinct from the revision counter on purpose. `screen_frames_revision` only moves when a
    frame was actually approved and persisted, so it cannot tell "never attempted" apart from
    "attempted, and every candidate was rejected" — both read 0.

    That difference matters more than a counter usually would. The candidates rejected on such a
    pass are exactly the sensitive ones: the credentials, the DM window, the inbox. Without this
    marker the client re-selects and re-uploads those same frames every time the note is reopened,
    which turns the privacy gate into a repeating egress of the material it exists to refuse.

    Scoped to `bucket`: a dev pass must not make a prod client skip adjudication.
    """
    stamp = datetime.now(timezone.utc)
    payload = _state_payload(bucket, 'adjudicated_at', stamp)
    fingerprint_payload = _state_payload(bucket, 'selection_fingerprint', selection_fingerprint)
    if _ENV_STATE_FIELD in payload:
        payload[_ENV_STATE_FIELD][_state_key(bucket)].update(fingerprint_payload[_ENV_STATE_FIELD][_state_key(bucket)])
    else:
        payload.update(fingerprint_payload)
    _conversation_ref(uid, conversation_id).set(payload, merge=True)
    return stamp


def get_conversation_screen_frames_adjudicated_at(
    uid: str, conversation_id: str, *, bucket: str, rpc_timeout: Optional[float] = None
):
    return _read_state(_conversation_ref(uid, conversation_id), bucket, 'adjudicated_at', rpc_timeout)


def get_conversation_screen_frames_selection_fingerprint(uid: str, conversation_id: str, *, bucket: str):
    return _read_state(_conversation_ref(uid, conversation_id), bucket, 'selection_fingerprint')


def get_conversation_screenshot_sharing_enabled(conversation: Dict[str, Any]) -> bool:
    """Default true for a conversation that predates this field (David's
    ruling 2026-08-20)."""
    value = conversation.get('screenshot_sharing_enabled')
    return True if value is None else bool(value)


def set_conversation_screenshot_sharing_enabled(uid: str, conversation_id: str, enabled: bool) -> None:
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_ref.update({'screenshot_sharing_enabled': enabled})
