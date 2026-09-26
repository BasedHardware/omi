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
from datetime import datetime, timezone
from typing import List, Dict, Any

from google.cloud import firestore

from utils import encryption
from ._client import db, get_firestore_client
from .conversations import conversations_collection
from .helpers import set_data_protection_level, prepare_for_write, prepare_for_read

screen_frames_subcollection = 'screen_frames'


def _prepare_screen_frame_for_write(data: Dict[str, Any], uid: str, level: str) -> Dict[str, Any]:
    data = copy.deepcopy(data)
    data['data_protection_level'] = level
    if level == 'enhanced' and 'caption' in data and isinstance(data['caption'], str):
        data['caption'] = encryption.encrypt(data['caption'], uid)
    return data


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
    if level == 'enhanced' and 'caption' in data and isinstance(data['caption'], str):
        try:
            data['caption'] = encryption.decrypt(data['caption'], uid)
        except Exception:
            # Already decrypted, or never encrypted — same tolerance as _prepare_photo_for_read.
            pass
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


def bump_conversation_screen_frames_revision(uid: str, conversation_id: str) -> int:
    """Atomically increment and return the ConversationScreenFrameSet revision
    counter. Called once per enforcement pass (contract §7) — never per read.
    """
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_ref.set({'screen_frames_revision': firestore.Increment(1)}, merge=True)
    snapshot = conversation_ref.get(field_paths=['screen_frames_revision'])
    data = snapshot.to_dict() or {}
    return int(data.get('screen_frames_revision', 0) or 0)


def get_conversation_screen_frames_revision(uid: str, conversation_id: str) -> int:
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    snapshot = conversation_ref.get(field_paths=['screen_frames_revision'])
    data = snapshot.to_dict() or {}
    return int(data.get('screen_frames_revision', 0) or 0)


def mark_conversation_screen_frames_adjudicated(uid: str, conversation_id: str) -> datetime:
    """Record that an adjudication pass ran for this conversation, whatever it decided.

    Distinct from the revision counter on purpose. `screen_frames_revision` only moves when a
    frame was actually approved and persisted, so it cannot tell "never attempted" apart from
    "attempted, and every candidate was rejected" — both read 0.

    That difference matters more than a counter usually would. The candidates rejected on such a
    pass are exactly the sensitive ones: the credentials, the DM window, the inbox. Without this
    marker the client re-selects and re-uploads those same frames every time the note is reopened,
    which turns the privacy gate into a repeating egress of the material it exists to refuse.
    """
    stamp = datetime.now(timezone.utc)
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_ref.set({'screen_frames_adjudicated_at': stamp}, merge=True)
    return stamp


def get_conversation_screen_frames_adjudicated_at(uid: str, conversation_id: str):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    snapshot = conversation_ref.get(field_paths=['screen_frames_adjudicated_at'])
    data = snapshot.to_dict() or {}
    return data.get('screen_frames_adjudicated_at')


def get_conversation_screenshot_sharing_enabled(conversation: Dict[str, Any]) -> bool:
    """Default true for a conversation that predates this field (David's
    ruling 2026-08-20)."""
    value = conversation.get('screenshot_sharing_enabled')
    return True if value is None else bool(value)


def set_conversation_screenshot_sharing_enabled(uid: str, conversation_id: str, enabled: bool) -> None:
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_ref.update({'screenshot_sharing_enabled': enabled})
