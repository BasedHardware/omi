"""A completed attach/recovery memo. No episode queries or reads on a hit."""

from google.cloud import firestore

from config.episode_attach import content_gate_enabled
from database._client import get_firestore_client
from database import transcript_pointer
from database.transcript_pointer import run_preloaded_transactional
from database.conversations import decode_transcript_segments_verified
from utils.conversations.episode_attach_key import content_key, memo_eligible
from utils.conversations.fragment_visibility import is_relevance_discarded
from utils.observability.fallback import record_fallback


def current_key(uid, row):
    if not row or not memo_eligible(row) or is_relevance_discarded(row):
        return None
    try:
        decoded = dict(row)
        decoded['transcript_segments'] = decode_transcript_segments_verified(
            uid, row.get('transcript_segments'), bool(row.get('transcript_segments_compressed'))
        )
        return content_key(decoded)
    except (
        transcript_pointer.TranscriptSegmentsDecodeError,
        transcript_pointer.TranscriptBlobAbsent,
        transcript_pointer.TranscriptShredded,
    ):
        # Failed verification cannot manufacture a memo hit or a completed stamp.
        return None


def matches(uid, cid, row, *, firestore_client=None, finalized=False):
    key = content_key(row) if content_gate_enabled() and memo_eligible(row) else None
    if key is None:
        return False
    client = firestore_client if firestore_client is not None else get_firestore_client()
    root = client.collection('users').document(uid)

    @firestore.transactional
    def check(transaction):
        link = root.collection('episode_links').document(cid).get(transaction=transaction).to_dict() or {}
        if (
            not link.get('episode_id')
            or link.get('attach_owner_id') != link['episode_id']
            or link.get('attach_revision') != key
            or link.get('attach_completed') != key
        ):
            return False
        if finalized and link.get('attach_finalized') != key:
            return False
        current = root.collection('conversations').document(cid).get(transaction=transaction).to_dict() or {}
        return current.get('episode_id') == link['episode_id'] and current_key(uid, current) == key

    try:
        return run_preloaded_transactional(client, check, transient=True)
    except transcript_pointer.TranscriptPointerError:
        raise
    except Exception:
        record_fallback(
            component='episodes',
            from_mode='attach_memo',
            to_mode='full_attach',
            reason='gate_unavailable',
            outcome='recovered',
        )
        return False


def stamp(transaction, client, uid, cid, key, owner_id):
    """Existing attach transaction, after all reads. Completion is separate.

    The caller verified its semantic inputs against the transaction's row. The
    stamp is deliberately not skippable until notes recovery has succeeded.
    """
    if key and content_gate_enabled():
        transaction.update(
            client.collection('users').document(uid).collection('episode_links').document(cid),
            {'attach_revision': key, 'attach_completed': None, 'attach_finalized': None, 'attach_owner_id': owner_id},
        )


def complete(uid, cid, row, owner, *, firestore_client=None, finalized=False):
    key = content_key(row) if content_gate_enabled() and memo_eligible(row) else None
    if key is None:
        return
    client = firestore_client if firestore_client is not None else get_firestore_client()
    root = client.collection('users').document(uid)

    @firestore.transactional
    def finish(transaction):
        ref = root.collection('episode_links').document(cid)
        link = ref.get(transaction=transaction).to_dict() or {}
        current = root.collection('conversations').document(cid).get(transaction=transaction).to_dict() or {}
        owner_id = owner['id'] if owner is not None else link.get('episode_id')
        marker = 'attach_finalized' if finalized else 'attach_completed'
        if (
            owner_id
            and link.get('episode_id') == owner_id == current.get('episode_id')
            and link.get('attach_owner_id') == owner_id
            and link.get('attach_revision') == key
            and current_key(uid, current) == key
            and (not finalized or link.get('attach_completed') == key)
            and link.get(marker) != key
        ):
            transaction.update(ref, {marker: key})

    try:
        run_preloaded_transactional(client, finish, transient=True)
    except transcript_pointer.TranscriptPointerError:
        raise
    except Exception:
        # The recovery already committed. An absent completion stamp keeps
        # future calls on the full path without changing this call's outcome.
        record_fallback(
            component='episodes',
            from_mode='attach_memo',
            to_mode='full_attach',
            reason='completion_unavailable',
            outcome='recovered',
        )
