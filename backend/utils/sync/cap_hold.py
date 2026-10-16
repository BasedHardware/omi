"""Encrypted, owner-scoped pre-STT holds. Pending audio has no application TTL.

The manifest is written only after upload succeeds. A failed hold fails the
upload/job, so the client never receives success for audio we did not retain.
"""

import hashlib
import json
import logging
from pathlib import Path
import time
from tempfile import TemporaryDirectory
import wave
from uuid import uuid4
from typing import Any
from models.conversation_enums import ConversationSource
from utils.observability.stt_cap_dispatch import record_audio
from utils.stt_cap_dispatch import funded_allowance

from google.cloud import firestore
from google.api_core.exceptions import AlreadyExists
from database import redis_db
from config.stt_cap_dispatch import enabled
from utils.sync.files import get_timestamp_from_path
from utils.stt_cap_dispatch import sync_allowed
from database._client import get_firestore_client
from database.legal_holds import external_write_fence
from utils.encryption import encrypt, decrypt, encrypt_audio_chunk, decrypt_audio_file
from utils.other.storage import get_private_cloud_sync_bucket, owner_storage_write_gate

logger = logging.getLogger(__name__)
COLLECTION = 'stt_cap_holds'


def holds(uid: str) -> Any:
    return get_firestore_client().collection('users').document(uid).collection(COLLECTION)


def pending_holds(uid: str, *, limit: int = 10) -> list[Any]:
    return list(holds(uid).limit(limit).stream())


def hold_segment(uid: str, path: str, metadata: dict[str, Any]) -> float:
    audio = Path(path).read_bytes()
    partition = {
        key: metadata.get(key) for key in ('timestamp', 'source', 'client_device_id', 'target_conversation_id')
    }
    identity = hashlib.sha256(json.dumps(partition, sort_keys=True).encode() + audio).hexdigest()
    blob_path = f'chunks/{uid}/cap-held/{identity}.wav.enc'
    bucket = get_private_cloud_sync_bucket()
    with wave.open(path, 'rb') as wav:
        seconds = wav.getnframes() / wav.getframerate()
    with external_write_fence(uid), owner_storage_write_gate(uid, bucket):
        ref = holds(uid).document(identity)
        if ref.get().exists:
            return seconds
        blob = bucket.blob(blob_path)
        blob.upload_from_string(encrypt_audio_chunk(audio, uid), content_type='application/octet-stream')
        try:
            ref.create(
                {
                    'audio_path': blob_path,
                    'metadata': encrypt(json.dumps(metadata), uid),
                    'seconds': seconds,
                    'state': 'held',
                    'created_at': time.time(),
                    'lease_until': 0,
                }
            )
        except AlreadyExists:
            return seconds  # A concurrent upload owns the immutable recovery checkpoint.
    record_audio('sync', 'held', 'unknown', seconds, funded_allowance(uid).reason == 'plan_allowance_exhausted')
    logger.info('event=stt_cap_dispatch path=sync outcome=held seconds=%.3f', seconds)
    return seconds


def claim(uid: str, ref: Any, now: float) -> dict[str, Any] | None:
    client = get_firestore_client()

    @firestore.transactional
    def commit(tx: Any):
        snapshot = ref.get(transaction=tx)
        row = snapshot.to_dict() if snapshot.exists else None
        if not row or row.get('state') == 'completed' or row.get('lease_until', 0) > now:
            return None
        token = uuid4().hex
        tx.update(ref, {'lease_until': now + 1800, 'lease_token': token})
        row['lease_token'] = token
        return row

    with external_write_fence(uid):
        return commit(client.transaction())


def read_audio(uid: str, row: dict[str, Any], path: str) -> None:
    expected = f'chunks/{uid}/cap-held/'
    if not row['audio_path'].startswith(expected):
        raise ValueError('hold audio owner mismatch')
    raw = get_private_cloud_sync_bucket().blob(row['audio_path']).download_as_bytes()
    Path(path).write_bytes(decrypt_audio_file(raw, uid))


def metadata(uid: str, row: dict[str, Any]) -> dict[str, Any]:
    return json.loads(decrypt(row['metadata'], uid))


def release(uid: str, ref: Any, token: str) -> None:
    client = get_firestore_client()

    @firestore.transactional
    def commit(tx: Any):
        snapshot = ref.get(transaction=tx)
        row = snapshot.to_dict() if snapshot.exists else {}
        if row.get('lease_token') == token:
            tx.update(ref, {'lease_until': 0, 'lease_token': ''})

    return commit(client.transaction())


def hold_capture_if_exhausted(uid: str, paths: list[str], source: ConversationSource, **context: Any) -> bool:
    # Shared by v1 intake and v2 execution, before VAD can discard silence.
    if not enabled() or sync_allowed(uid):
        return False
    for path in paths:
        hold_segment(
            uid,
            path,
            {
                **context,
                'timestamp': get_timestamp_from_path(path),
                'source': getattr(source, 'value', source),
                'full_capture': True,
            },
        )
    return True


def recovery_cooldown(uid: str) -> bool:
    return bool(redis_db.r.set(f'users:{uid}:stt_cap_recovery:cooldown', '1', nx=True, ex=60))


def renew(uid: str, ref: Any, token: str, now: float) -> bool:
    client = get_firestore_client()

    @firestore.transactional
    def commit(tx: Any) -> bool:
        snapshot = ref.get(transaction=tx)
        row = snapshot.to_dict() if snapshot.exists else {}
        if row.get('lease_token') != token or row.get('lease_until', 0) <= now:
            return False
        tx.update(ref, {'lease_until': now + 1800})
        return True

    with external_write_fence(uid):
        return commit(client.transaction())


def recovery_directory(uid: str) -> TemporaryDirectory:
    parent = Path('syncing') / uid
    parent.mkdir(parents=True, exist_ok=True)
    return TemporaryDirectory(prefix='cap-recovery-', dir=parent)
