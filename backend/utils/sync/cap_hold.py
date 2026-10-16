"""Encrypted, owner-scoped pre-STT holds. Pending audio has no application TTL.

The manifest is written only after upload succeeds. A failed hold fails the
upload/job, so the client never receives success for audio we did not retain.
"""

import hashlib
import json
import logging
from pathlib import Path
import time
from tempfile import TemporaryDirectory, TemporaryFile
import struct
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
from utils.executors import db_executor, storage_executor, run_blocking
from database._client import get_firestore_client
from database.legal_holds import external_write_fence
from utils.encryption import encrypt, decrypt, encrypt_audio_chunk, decrypt_audio_chunk
from utils.other.storage import get_private_cloud_sync_bucket, owner_storage_write_gate

logger = logging.getLogger(__name__)
COLLECTION = 'stt_cap_holds'
AUDIO_CHUNK_BYTES = 1024 * 1024
RETAINED_NEXT_ATTEMPT_AT = 253402300799  # Terminal rows sort after actionable work, without a new query/index.


def holds(uid: str) -> Any:
    return get_firestore_client().collection('users').document(uid).collection(COLLECTION)


def pending_holds(uid: str, *, limit: int = 10) -> list[Any]:
    return list(holds(uid).order_by('next_attempt_at').limit(limit).stream())


def capture_identity(path: str, metadata: dict[str, Any]) -> str:
    partition = {
        key: metadata.get(key) for key in ('timestamp', 'source', 'client_device_id', 'target_conversation_id')
    }
    digest = hashlib.sha256(json.dumps(partition, sort_keys=True).encode())
    with open(path, 'rb') as source:
        while chunk := source.read(AUDIO_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _describe(path: str, metadata: dict[str, Any]) -> tuple[str, float, dict]:
    metadata = dict(metadata)
    geolocation = metadata.get('geolocation')
    if geolocation is not None and hasattr(geolocation, 'model_dump'):
        metadata['geolocation'] = geolocation.model_dump(mode='json')
    identity = capture_identity(path, metadata)
    with wave.open(path, 'rb') as wav:
        seconds = wav.getnframes() / wav.getframerate()
    return identity, seconds, metadata


def _exists(uid: str, identity: str) -> bool:
    with external_write_fence(uid):
        return bool(holds(uid).document(identity).get().exists)


def upload_held_audio(uid: str, path: str, identity: str, metadata: dict) -> dict:
    blob_path = f'chunks/{uid}/cap-held/{identity}.wav.enc'
    bucket = get_private_cloud_sync_bucket()
    with external_write_fence(uid), owner_storage_write_gate(uid, bucket):
        blob = bucket.blob(blob_path)
        blob.chunk_size = 8 * AUDIO_CHUNK_BYTES
        with recovery_directory(uid) as directory, TemporaryFile(dir=directory) as encrypted:
            with open(path, 'rb') as source:
                while chunk := source.read(AUDIO_CHUNK_BYTES):
                    encrypted.write(encrypt_audio_chunk(chunk, uid))
            encrypted.seek(0)
            blob.upload_from_file(encrypted, content_type='application/octet-stream')
        encoded_metadata = encrypt(json.dumps(metadata), uid)
        fields = {'audio_path': blob_path, 'metadata': encoded_metadata}
        if len(encoded_metadata.encode()) > 512 * 1024:
            metadata_digest = hashlib.sha256(encoded_metadata.encode()).hexdigest()
            metadata_path = f'chunks/{uid}/cap-held/{identity}.{metadata_digest}.metadata.enc'
            bucket.blob(metadata_path).upload_from_string(encoded_metadata, content_type='application/octet-stream')
            fields = {'audio_path': blob_path, 'metadata_path': metadata_path}
        return fields


def _publish(uid: str, identity: str, seconds: float, fields: dict) -> bool:
    # Reacquire the account fence after upload: deletion may have started while
    # the async coordinator switched pools. Never acknowledge a refused manifest.
    with external_write_fence(uid):
        try:
            holds(uid).document(identity).create(
                {
                    **fields,
                    'seconds': seconds,
                    'state': 'held',
                    'created_at': time.time(),
                    'next_attempt_at': 0,
                    'lease_until': 0,
                }
            )
        except AlreadyExists:
            return False  # Preserve the winner's immutable progress checkpoint.
    return True


def _finish(identity: str, seconds: float, reason: str, receipt: dict | None, created: bool) -> float:
    if receipt is not None:
        receipt.update(id=identity, seconds=seconds, reason=reason)
    if created:
        record_audio('sync', 'held', 'unknown', seconds, reason == 'plan_allowance_exhausted')
        logger.info('event=stt_cap_dispatch path=sync outcome=held seconds=%.3f', seconds)
    return seconds


def hold_segment(uid: str, path: str, metadata: dict[str, Any], *, receipt: dict | None = None) -> float:
    identity, seconds, metadata = _describe(path, metadata)
    created = False
    if not _exists(uid, identity):
        fields = upload_held_audio(uid, path, identity, metadata)
        created = _publish(uid, identity, seconds, fields)
    return _finish(identity, seconds, funded_allowance(uid).reason, receipt, created)


async def _hold_capture(uid: str, path: str, metadata: dict, reason: str, receipt: dict) -> None:
    # Pool workers are leaves; no sync worker waits for another executor.
    identity, seconds, metadata = await run_blocking(storage_executor, _describe, path, metadata)
    created = False
    if not await run_blocking(db_executor, _exists, uid, identity):
        fields = await run_blocking(storage_executor, upload_held_audio, uid, path, identity, metadata)
        created = await run_blocking(db_executor, _publish, uid, identity, seconds, fields)
    _finish(identity, seconds, reason, receipt, created)


def claim(uid: str, ref: Any, now: float) -> dict[str, Any] | None:
    client = get_firestore_client()

    @firestore.transactional
    def commit(tx: Any):
        snapshot = ref.get(transaction=tx)
        row = snapshot.to_dict() if snapshot.exists else None
        if not row or row.get('state') in {'completed', 'retained'} or row.get('lease_until', 0) > now:
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
    blob = get_private_cloud_sync_bucket().blob(row['audio_path'])
    blob.chunk_size = 8 * AUDIO_CHUNK_BYTES
    with TemporaryFile(dir=Path(path).parent) as encrypted:
        blob.download_to_file(encrypted)
        encrypted.seek(0)
        try:
            with open(path, 'wb') as output:
                while prefix := encrypted.read(4):
                    if len(prefix) != 4:
                        raise ValueError('truncated held-audio chunk')
                    size = struct.unpack('>I', prefix)[0]
                    if not 28 <= size <= AUDIO_CHUNK_BYTES + 28:
                        raise ValueError('invalid held-audio chunk size')
                    payload = encrypted.read(size)
                    if len(payload) != size:
                        raise ValueError('truncated held-audio payload')
                    audio, _ = decrypt_audio_chunk(prefix + payload, uid)
                    output.write(audio)
        except Exception:
            Path(path).unlink(missing_ok=True)
            raise


def metadata(uid: str, row: dict[str, Any]) -> dict[str, Any]:
    if row.get('metadata_path'):
        if not row['metadata_path'].startswith(f'chunks/{uid}/cap-held/'):
            raise ValueError('hold metadata owner mismatch')
        encoded = get_private_cloud_sync_bucket().blob(row['metadata_path']).download_as_text()
    else:
        encoded = row['metadata']
    return json.loads(decrypt(encoded, uid))


def release(uid: str, ref: Any, token: str) -> None:
    client = get_firestore_client()

    @firestore.transactional
    def commit(tx: Any):
        snapshot = ref.get(transaction=tx)
        row = snapshot.to_dict() if snapshot.exists else {}
        if row.get('lease_token') == token:
            tx.update(
                ref,
                {
                    'lease_until': 0,
                    'lease_token': '',
                    'next_attempt_at': RETAINED_NEXT_ATTEMPT_AT if row.get('state') == 'retained' else time.time(),
                },
            )

    return commit(client.transaction())


async def hold_capture_if_exhausted(
    uid: str,
    paths: list[str],
    source: ConversationSource,
    *,
    receipts: dict | None = None,
    source_frame_maps: dict | None = None,
    admission: dict | None = None,
    **context: Any,
) -> bool:
    # Shared by v1 intake and v2 execution, before VAD can discard silence.
    if not paths or not enabled():
        return False
    allowance = await run_blocking(db_executor, funded_allowance, uid)
    if allowance.managed:
        return False
    if admission is not None:
        admission['reason'] = allowance.reason
    for path in paths:
        receipt: dict = {}
        await _hold_capture(
            uid,
            path,
            {
                **context,
                'timestamp': get_timestamp_from_path(path),
                'source': getattr(source, 'value', source),
                'full_capture': True,
                'file_name': Path(path).name,
                'source_frame_map': (source_frame_maps or {}).get(path),
            },
            allowance.reason,
            receipt,
        )
        if receipts is not None:
            receipts[receipt['id']] = receipt
    return True


def defer_segment(uid: str, path: str, metadata: dict, response: dict, lock: Any) -> None:
    """Report a durable late hold to both coordinators, never as silence."""
    receipt: dict = {}
    hold_segment(uid, path, {**metadata, 'file_name': Path(path).name}, receipt=receipt)
    with lock:
        response.setdefault('_cap_holds', {})[receipt['id']] = receipt


def checkpoint(uid: str, ref: Any, token: str, updates: dict) -> bool:
    client = get_firestore_client()

    @firestore.transactional
    def commit(tx: Any) -> bool:
        row = ref.get(transaction=tx).to_dict() or {}
        if row.get('lease_token') != token or row.get('lease_until', 0) <= time.time():
            return False
        tx.update(ref, updates)
        return True

    with external_write_fence(uid):
        return commit(client.transaction())


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
