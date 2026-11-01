"""Encrypted, compressed evidence under the owning conversation, without changing its revision."""

import base64
import json
import zlib
from typing import Any

from google.cloud import firestore

from database._client import get_firestore_client, run_transactional
from database.conversation_revisions import firestore_revision_datetime
from database.read_boundary import parse_payload_strict
from models.speaker_evidence import SpeakerEvidence
from utils.encryption import decrypt, encrypt

MAX_ENCODED_BYTES = 750_000
MAX_DECODED_BYTES = 16_000_000


def _ref(uid: str, conversation_id: str, firestore_client: Any):
    client = firestore_client if firestore_client is not None else get_firestore_client()
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
    client = firestore_client if firestore_client is not None else get_firestore_client()
    parent = _ref(uid, conversation_id, client)

    @firestore.transactional
    def persist(transaction):
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

    # A child write preserves the parent update_time used by late identity CAS.
    # Parent deletion and the existing recursive deletion sweeps fence or purge it.
    run_transactional(client, persist)


def get_evidence(uid: str, conversation_id: str, *, firestore_client: Any = None) -> SpeakerEvidence | None:
    parent = _ref(uid, conversation_id, firestore_client)
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
