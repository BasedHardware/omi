"""Encrypted, compressed evidence under the owning conversation, without changing its revision."""

import base64
import json
import zlib
from typing import Any

from google.cloud import firestore

from database._client import run_transactional
from database.account_deletion_marker import account_deletion_document, account_deletion_firestore_client
from database.conversation_revisions import firestore_revision_datetime
from database.read_boundary import parse_payload_strict
from models.speaker_evidence import SpeakerEvidence
from utils.encryption import decrypt, encrypt
from utils.observability import speaker_evidence_erasure as metrics

MAX_ENCODED_BYTES = 750_000
MAX_DECODED_BYTES = 16_000_000


class _DeletionMarkerPresent(ValueError):
    """The write transaction observed an existing account deletion marker."""


def _ref(uid: str, conversation_id: str, client: Any):
    return client.collection('users').document(uid).collection('conversations').document(conversation_id)


def store_evidence(
    uid: str,
    conversation_id: str,
    evidence: SpeakerEvidence,
    *,
    expected_updated_at: Any = None,
    firestore_client: Any = None,
) -> None:
    raw = evidence.model_dump_json().encode()
    if len(raw) > MAX_DECODED_BYTES:
        raise ValueError('speaker evidence exceeds decoded size budget')
    payload = encrypt(base64.b64encode(zlib.compress(raw)).decode(), uid)
    if len(payload.encode()) > MAX_ENCODED_BYTES:
        raise ValueError('speaker evidence exceeds document size budget')
    client = account_deletion_firestore_client(firestore_client=firestore_client)
    parent = _ref(uid, conversation_id, client)
    marker = account_deletion_document(uid, firestore_client=client)

    @firestore.transactional
    def persist(transaction):
        marker_present = marker.get(transaction=transaction).exists
        if marker_present:
            raise _DeletionMarkerPresent('speaker evidence account unavailable')
        snapshot = parent.get(transaction=transaction)
        current = snapshot.to_dict()
        if (
            expected_updated_at is not None
            and firestore_revision_datetime(getattr(snapshot, 'update_time', None)) != expected_updated_at
        ):
            raise ValueError('speaker evidence source revision changed')
        if current is None or current.get('deleted') or current.get('discarded'):
            raise ValueError('speaker evidence parent unavailable')
        transaction.set(parent.collection('speaker_evidence').document('current'), {'version': 1, 'payload': payload})
        return marker_present

    # A child write preserves the parent update_time used by late identity CAS.
    # Parent deletion and the existing recursive deletion sweeps fence or purge it.
    try:
        marker_present = run_transactional(client, persist)
    except _DeletionMarkerPresent:
        metrics.REFUSED_MARKER_PRESENT.inc()
        raise
    except Exception:
        metrics.WRITER_FAILED.inc()
        raise
    # The SDK returns the callback result only after acknowledging the commit.
    if marker_present:
        metrics.COMMITTED_MARKER_PRESENT.inc()
    else:
        metrics.COMMITTED_MARKER_ABSENT.inc()


def get_evidence(uid: str, conversation_id: str, *, firestore_client: Any = None) -> SpeakerEvidence | None:
    client = account_deletion_firestore_client(firestore_client=firestore_client)
    parent = _ref(uid, conversation_id, client)
    raw = parent.get().to_dict()
    if raw is None or raw.get('deleted') or raw.get('discarded'):
        return None
    stored = parent.collection('speaker_evidence').document('current').get().to_dict() or {}
    if not stored:
        return None
    if stored.get('version') != 1:
        return None
    compressed = base64.b64decode(decrypt(stored['payload'], uid), validate=True)
    inflater = zlib.decompressobj()
    payload = inflater.decompress(compressed, MAX_DECODED_BYTES + 1)
    if len(payload) > MAX_DECODED_BYTES or not inflater.eof:
        raise ValueError('speaker evidence exceeds decoded size budget')
    return parse_payload_strict(
        SpeakerEvidence, json.loads(payload), document_path='users/*/conversations/*/speaker_evidence/current'
    )
