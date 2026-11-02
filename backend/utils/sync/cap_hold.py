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
from utils.observability.held_content import record_capture
from utils.observability.stt_cap_dispatch import record_audio, record_allowance_decision, DispatchPath
from utils.stt_cap_dispatch import funded_allowance

from google.cloud import firestore
from google.api_core.exceptions import AlreadyExists, PreconditionFailed
from database import redis_db
from database.fsr_read_cache import forget_request_reads, memo
from config.stt_cap_dispatch import offline_admission_enabled as enabled
from utils.sync.files import get_timestamp_from_path
from utils.executors import db_executor, storage_executor, run_blocking
from database._client import get_data_plane_firestore_client as get_firestore_client
from database.legal_holds import external_write_fence
from utils.encryption import encrypt, decrypt, encrypt_audio_chunk, decrypt_audio_chunk
from utils.other.storage import get_private_cloud_sync_bucket, owner_storage_write_gate

logger = logging.getLogger(__name__)
COLLECTION = 'stt_cap_holds'
SUMMARY_COLLECTION = 'stt_cap_hold_summary'
AUDIO_CHUNK_BYTES = 1024 * 1024
RETAINED_NEXT_ATTEMPT_AT = 253402300799  # Terminal rows sort after actionable work, without a new query/index.


def holds(uid: str) -> Any:
    return get_firestore_client().collection('users').document(uid).collection(COLLECTION)


def summary_ref(uid: str) -> Any:
    """One running total of audio still in ``held``. Card and settings read this doc."""
    return get_firestore_client().collection('users').document(uid).collection(SUMMARY_COLLECTION).document('current')


def whole_seconds(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return max(0, int(round(value)))


def pending_holds(uid: str, *, limit: int = 10) -> list[Any]:
    return list(holds(uid).order_by('next_attempt_at').limit(limit).stream())


def capture_identity(path: str, metadata: dict[str, Any]) -> str:
    partition = {
        key: metadata.get(key) for key in ('timestamp', 'source', 'client_device_id', 'target_conversation_id')
    }
    if metadata.get('origin') == 'live':
        partition.update({key: metadata.get(key) for key in ('origin', 'recording_session_id', 'channel')})
    digest = hashlib.sha256(json.dumps(partition, sort_keys=True).encode())
    with open(path, 'rb') as source:
        while chunk := source.read(AUDIO_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def describe(path: str, metadata: dict[str, Any]) -> tuple[str, float, dict]:
    metadata = dict(metadata)
    metadata.setdefault('origin', 'sync')
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


def upload_held_audio(
    uid: str,
    path: str,
    identity: str,
    metadata: dict,
    *,
    immutable: bool = False,
    live_size_limit: int | None = None,
    rpc_timeout: float = 10.0,
) -> dict:
    codec = metadata.get('audio_codec')
    extension = 'opus' if codec == 'ogg_opus' else 'wav'
    blob_path = f'chunks/{uid}/cap-held/{identity}.{extension}.enc'
    bucket = get_private_cloud_sync_bucket()
    with external_write_fence(uid), owner_storage_write_gate(uid, bucket):
        blob = bucket.blob(blob_path)
        blob.chunk_size = 8 * AUDIO_CHUNK_BYTES
        with recovery_directory(uid) as directory, TemporaryFile(dir=directory) as encrypted:
            with open(path, 'rb') as source:
                while chunk := source.read(AUDIO_CHUNK_BYTES):
                    encrypted.write(encrypt_audio_chunk(chunk, uid))
            encrypted_size = encrypted.tell()
            encrypted.seek(0)
            capture = ''
            if live_size_limit is not None:
                if not immutable or codec != 'ogg_opus' or not 32 < encrypted_size <= live_size_limit + 32:
                    raise ValueError('invalid immutable live source')
                # Opaque provenance survives re-encoding and encryption randomness.
                capture = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()
                blob.metadata = {'omi_live_capture': capture, 'omi_live_bytes': str(encrypted_size - 32)}
            try:
                blob.upload_from_file(
                    encrypted,
                    content_type='application/octet-stream',
                    **({'if_generation_match': 0} if immutable else {}),
                    **({'timeout': rpc_timeout, 'retry': None, 'size': encrypted_size} if codec == 'ogg_opus' else {}),
                )
            except PreconditionFailed:
                if not immutable:
                    raise
                # The immutable capture identity names the same plaintext;
                # preserve the first authenticated object across upload retries.
                if codec == 'ogg_opus':
                    blob.reload(timeout=rpc_timeout, retry=None)  # Retry-only generation provenance.
                    if live_size_limit is not None:
                        stored_metadata = blob.metadata or {}
                        try:
                            stored_bytes = int(stored_metadata.get('omi_live_bytes', '0'))
                        except (TypeError, ValueError):
                            raise ValueError('invalid stored live source size') from None
                        if (
                            stored_metadata.get('omi_live_capture') != capture
                            or not 0 < stored_bytes <= live_size_limit
                            or blob.size != stored_bytes + 32
                            or not blob.generation
                        ):
                            raise ValueError('stored live source provenance mismatch')
                        encrypted_size = blob.size
        encoded_metadata = encrypt(json.dumps(metadata), uid)
        fields: dict[str, Any] = {'audio_path': blob_path, 'metadata': encoded_metadata}
        if codec == 'ogg_opus':
            fields.update(
                audio_codec=codec,
                sample_rate=metadata['sample_rate'],
                source_frames=metadata['source_frames'],
                audio_generation=blob.generation,
            )
        if live_size_limit is not None:
            if not blob.generation:
                raise ValueError('immutable live source generation unavailable')
            fields['audio_size'] = encrypted_size
        if len(encoded_metadata.encode()) > 512 * 1024:
            metadata_digest = hashlib.sha256(encoded_metadata.encode()).hexdigest()
            metadata_path = f'chunks/{uid}/cap-held/{identity}.{metadata_digest}.metadata.enc'
            bucket.blob(metadata_path).upload_from_string(encoded_metadata, content_type='application/octet-stream')
            fields.pop('metadata')
            fields['metadata_path'] = metadata_path
        return fields


def hold_started_at(metadata: dict) -> int | None:
    """Recording start from plaintext hold metadata, before it is encrypted."""
    value = metadata.get('timestamp')
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    return int(value)


def hold_manifest(fields: dict, seconds: float, now: float, started_at: int | None) -> dict:
    body = {
        **fields,
        'seconds': seconds,
        'state': 'held',
        'created_at': now,
        'next_attempt_at': 0,
        'lease_until': 0,
    }
    if started_at is not None:
        body['started_at'] = started_at
    # Newest-first listing. Recording start when we have it, otherwise the
    # manifest write. Every new hold carries the field the ordered query uses.
    body['listed_at'] = started_at if started_at is not None else now
    return body


def summary_after(current: dict | None, delta_seconds: float, delta_count: int) -> dict:
    data = current or {}
    count = max(0, int(data.get('count') or 0) + int(delta_count))
    seconds = max(0, float(data.get('seconds') or 0) + delta_seconds) if count else 0.0
    return {'version': 2, 'seconds': seconds, 'count': count}


def remaining_seconds(row: dict) -> float:
    """Pending source seconds, then pending frozen pieces once VAD is planned.

    Failed reconciliation remains waiting and retained. Successful/silent pieces
    cease contributing as soon as their transcribed receipt is fenced in.
    """
    if row.get('failed_reconciliation') or row.get('state') == 'held':
        plan = row.get('piece_plan')
        if plan is None:
            return max(0.0, float(row.get('seconds') or 0))
        receipts = row.get('piece_receipts') or {}
        processed = set(row.get('processed_paths') or [])
        return sum(
            max(0.0, float(piece.get('seconds') or 0))
            for name, piece in plan.items()
            if name not in processed and receipts.get(name, {}).get('state') != 'transcribed'
        )
    return 0.0


def read_held_audio_summary(uid: str) -> dict:
    """Held-audio summary document.

    Module-level so the Firestore read probe attributes the get to this
    function rather than a lambda or the request-memo wrapper.
    """
    snap = summary_ref(uid).get()
    if not snap.exists:
        return {}
    return snap.to_dict() or {}


def ensure_summary(uid: str) -> dict:
    """Resume a fenced, bounded migration before any hold mutation proceeds.

    Repeated reads in one request share the per-request memo. A version-2
    document is the fast path; an older document still migrates before the
    memo stores the finished total.
    """
    return memo(uid, 'stt_cap_hold_summary', lambda: _ensure_held_audio_summary(uid))


def _ensure_held_audio_summary(uid: str) -> dict:
    """Fenced migration. Creators and checkpoints wait for version 2.

    A short summary lease keeps concurrent initializers out of the 400-row
    transactions. Every page fences its owner and cursor together with listing
    backfill. An expired initializer can be replaced without rescanning
    completed pages.
    """
    current = read_held_audio_summary(uid)
    if current and current.get('version') == 2:
        return current
    client = get_firestore_client()
    ref = summary_ref(uid)
    owner = uuid4().hex
    wait_until = time.monotonic() + 30

    @firestore.transactional
    def claim_builder(tx: Any) -> dict:
        snapshot = ref.get(transaction=tx)
        data = (snapshot.to_dict() or {}) if snapshot.exists else {}
        if data.get('version') == 2:
            return data
        now = time.time()
        if data.get('build_owner') and float(data.get('build_lease_until') or 0) > now:
            return data
        building = data.get('version') == 1 and data.get('building') is True
        claimed = {
            'version': 1,
            'building': True,
            'cursor': data.get('cursor') if building else None,
            'partial_seconds': float(data.get('partial_seconds') or 0) if building else 0.0,
            'partial_count': int(data.get('partial_count') or 0) if building else 0,
            'build_owner': owner,
            'build_lease_until': now + 30,
        }
        tx.set(ref, claimed)
        return claimed

    @firestore.transactional
    def rebuild_page(tx: Any) -> dict:
        snap = ref.get(transaction=tx)
        current = (snap.to_dict() or {}) if snap.exists else {}
        if current.get('version') == 2:
            return current
        if current.get('build_owner') != owner or float(current.get('build_lease_until') or 0) <= time.time():
            return current
        building = current.get('version') == 1 and current.get('building') is True
        cursor = current.get('cursor') if building else None
        seconds = float(current.get('partial_seconds') or 0) if building else 0.0
        count = int(current.get('partial_count') or 0) if building else 0
        query = holds(uid).order_by('__name__').limit(400)
        if cursor:
            query = query.start_after({'__name__': holds(uid).document(cursor)})
        page = list(query.stream(transaction=tx))
        # Finish all reads before backfilling at most 400 rows plus one marker.
        for snap in page:
            row = snap.to_dict() or {}
            pending = remaining_seconds(row)
            seconds += pending
            count += int(pending > 0)
            if 'listed_at' not in row:
                tx.update(snap.reference, {'listed_at': row.get('started_at') or row.get('created_at') or 0})
        if len(page) < 400:
            result = {'version': 2, 'seconds': seconds, 'count': count}
        else:
            result = {
                'version': 1,
                'building': True,
                'cursor': page[-1].id,
                'partial_seconds': seconds,
                'partial_count': count,
                'build_owner': owner,
                'build_lease_until': time.time() + 30,
            }
        tx.set(ref, result)
        return result

    while True:
        if current and current.get('version') == 2:
            return current
        if (current or {}).get('build_owner') != owner:
            if float((current or {}).get('build_lease_until') or 0) > time.time():
                if time.monotonic() >= wait_until:
                    raise RuntimeError('held-audio summary initialization in progress')
                time.sleep(0.1)
                with external_write_fence(uid):
                    snapshot = ref.get()
                current = (snapshot.to_dict() or {}) if snapshot.exists else {}
                continue
        if (current or {}).get('build_owner') != owner or float(
            (current or {}).get('build_lease_until') or 0
        ) <= time.time():
            with external_write_fence(uid):
                current = claim_builder(client.transaction())
            if current.get('version') == 2:
                return current
            if current.get('build_owner') != owner:
                continue
        # Recheck deletion/destructive-operation authority between every page.
        with external_write_fence(uid):
            current = rebuild_page(client.transaction())


def _publish(uid: str, identity: str, seconds: float, fields: dict, started_at: int | None = None) -> bool:
    # Reacquire the account fence after upload: deletion may have started while
    # the async coordinator switched pools. Never acknowledge a refused manifest.
    manifest = hold_manifest(fields, seconds, time.time(), started_at)
    whole = seconds
    ensure_summary(uid)
    with external_write_fence(uid):
        client = get_firestore_client()
        batch = client.batch()
        try:
            # One commit: the hold and the running total appear together.
            # AlreadyExists fails the batch, so a retried create does not add twice.
            batch.create(holds(uid).document(identity), manifest)
            batch.set(
                summary_ref(uid),
                {'seconds': firestore.Increment(whole), 'count': firestore.Increment(1)},
                merge=True,
            )
            batch.commit()
        except AlreadyExists:
            return False  # Preserve the winner's immutable progress checkpoint.
    forget_request_reads(uid)
    return True


def _finish(identity: str, seconds: float, reason: str, receipt: dict | None, created: bool) -> float:
    if receipt is not None:
        receipt.update(id=identity, seconds=seconds, reason=reason)
    if created:
        record_audio('sync', 'held', 'unknown', seconds, reason == 'plan_allowance_exhausted')
        logger.info('event=stt_cap_dispatch path=sync outcome=held seconds=%.3f', seconds)
    return seconds


def hold_segment(uid: str, path: str, metadata: dict[str, Any], *, receipt: dict | None = None) -> float:
    identity, seconds, metadata = describe(path, metadata)
    created = False
    if not _exists(uid, identity):
        fields = upload_held_audio(uid, path, identity, metadata)
        created = _publish(uid, identity, seconds, fields, hold_started_at(metadata))
        if not created and not _exists(uid, identity):
            record_capture('ack_without_authority')
    return _finish(
        identity, seconds, funded_allowance(uid, lane=metadata.get('origin', 'sync')).reason, receipt, created
    )


async def _hold_capture(uid: str, path: str, metadata: dict, reason: str, receipt: dict) -> None:
    # Pool workers are leaves; no sync worker waits for another executor.
    identity, seconds, metadata = await run_blocking(storage_executor, describe, path, metadata)
    created = False
    if not await run_blocking(db_executor, _exists, uid, identity):
        fields = await run_blocking(storage_executor, upload_held_audio, uid, path, identity, metadata)
        created = await run_blocking(db_executor, _publish, uid, identity, seconds, fields, hold_started_at(metadata))
        if not created and not await run_blocking(db_executor, _exists, uid, identity):
            record_capture('ack_without_authority')
    _finish(identity, seconds, reason, receipt, created)


def claim(uid: str, ref: Any, now: float) -> dict[str, Any] | None:
    client = get_firestore_client()

    @firestore.transactional
    def commit(tx: Any):
        snapshot = ref.get(transaction=tx)
        row = snapshot.to_dict() if snapshot.exists else None
        if (
            not row
            or row.get('state') in {'completed', 'retained', 'purged', 'staging', 'sealing', 'superseded'}
            or row.get('lease_until', 0) > now
            or row.get('next_attempt_at', 0) > now
        ):
            return None
        token = uuid4().hex
        tx.update(ref, {'lease_until': now + 1800, 'lease_token': token})
        row['lease_token'] = token
        return row

    with external_write_fence(uid):
        return commit(client.transaction())


def _read_single_audio(uid: str, row: dict[str, Any], path: str) -> None:
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


def read_audio(uid: str, row: dict[str, Any], path: str) -> None:
    if row.get('source_slice'):
        return _read_source_slice(uid, row, path)
    if row.get('audio_codec') == 'ogg_opus':
        from utils.sync.live_cap_codec import decode

        with TemporaryDirectory(dir=Path(path).parent) as directory:
            compressed = str(Path(directory) / 'source.opus')
            _read_single_audio(uid, row, compressed)
            fragments = row.get('opus_fragments')
            if fragments:
                with open(compressed, 'rb') as source, wave.open(path, 'wb') as output:
                    output.setparams((1, 2, int(row['sample_rate']), 0, 'NONE', 'not compressed'))
                    for index, fragment in enumerate(fragments):
                        opus = str(Path(directory) / f'{index}.opus')
                        wav = str(Path(directory) / f'{index}.wav')
                        Path(opus).write_bytes(source.read(fragment['bytes']))
                        decode(opus, wav, int(row['sample_rate']), fragment['frames'])
                        with wave.open(wav, 'rb') as audio:
                            output.writeframesraw(audio.readframes(fragment['frames']))
                    if source.read(1):
                        raise ValueError('unexpected live fragment source tail')
            else:
                decode(compressed, path, int(row['sample_rate']), int(row['source_frames']))
        return
    parts = row.get('audio_parts')
    if not parts:
        return _read_single_audio(uid, row, path)
    # A live capture contains at most 60 one-second encrypted WAVs. Decode one
    # part at a time and stream PCM into one recovery WAV; never join headers.
    try:
        with TemporaryDirectory(dir=Path(path).parent) as directory, wave.open(path, 'wb') as output:
            params = None
            for index, source in enumerate(parts):
                piece = str(Path(directory) / f'{index}.wav')
                _read_single_audio(uid, {'audio_path': source}, piece)
                with wave.open(piece, 'rb') as audio:
                    current = (audio.getnchannels(), audio.getsampwidth(), audio.getframerate())
                    if params is None:
                        params = current
                        output.setparams((*current, 0, 'NONE', 'not compressed'))
                    elif current != params:
                        record_capture('frame_mismatch')
                        raise ValueError('live hold part codec mismatch')
                    while pcm := audio.readframes(AUDIO_CHUNK_BYTES // 2):
                        output.writeframesraw(pcm)
                Path(piece).unlink()
    except BaseException:
        Path(path).unlink(missing_ok=True)
        raise


def _read_source_slice(uid: str, row: dict[str, Any], path: str) -> None:
    from utils.sync.live_cap_codec import pcm_description

    cache_name = hashlib.sha256(row['audio_path'].encode()).hexdigest()
    source = str(Path(path).parent / f'.source-{cache_name}.wav')
    if not Path(source).exists():
        read_audio(uid, {key: value for key, value in row.items() if key != 'source_slice'}, source)
    selection = row['source_slice']
    with wave.open(source, 'rb') as audio, wave.open(path, 'wb') as output:
        first, frames = selection['start'], selection['frames']
        if first < 0 or frames <= 0 or first + frames > audio.getnframes():
            record_capture('frame_mismatch')
            raise ValueError('held source slice exceeds source')
        output.setparams(audio.getparams())
        audio.setpos(first)
        output.writeframes(audio.readframes(frames))
    if pcm_description(path)[2] != selection['sha256']:
        record_capture('byte_mismatch')
        Path(path).unlink(missing_ok=True)
        raise ValueError('held source decode changed since frozen plan')


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
                    'next_attempt_at': (
                        RETAINED_NEXT_ATTEMPT_AT
                        if row.get('state') == 'retained'
                        else max(row.get('next_attempt_at', 0), time.time())
                    ),
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
    dispatch_path: DispatchPath = DispatchPath.SYNC_V1,
    **context: Any,
) -> bool:
    # Shared by v1 intake and v2 execution, before VAD can discard silence.
    if not paths or not enabled(uid, 'sync'):
        return False
    allowance = await run_blocking(db_executor, funded_allowance, uid, lane='sync')
    if record_allowance_decision(dispatch_path, allowance):
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
                'origin': 'sync',
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
    hold_segment(
        uid,
        path,
        {'timestamp': get_timestamp_from_path(path), **metadata, 'file_name': Path(path).name},
        receipt=receipt,
    )
    with lock:
        response.setdefault('_cap_holds', {})[receipt['id']] = receipt


def checkpoint(uid: str, ref: Any, token: str, updates: dict) -> bool:
    ensure_summary(uid)
    client = get_firestore_client()

    @firestore.transactional
    def commit(tx: Any) -> bool:
        snapshot = ref.get(transaction=tx)
        row = snapshot.to_dict() if snapshot.exists else {}
        if row.get('lease_token') != token or row.get('lease_until', 0) <= time.time():
            return False
        updated = {**row, **updates}
        before, after = remaining_seconds(row), remaining_seconds(updated)
        delta = after - before
        count_delta = int(after > 0) - int(before > 0)
        summary_snapshot = summary_ref(uid).get(transaction=tx) if delta or count_delta else None
        tx.update(ref, updates)
        if summary_snapshot is not None:
            current = summary_snapshot.to_dict() if summary_snapshot.exists else None
            tx.set(summary_ref(uid), summary_after(current, delta, count_delta))
        return True

    with external_write_fence(uid):
        changed = commit(client.transaction())
    forget_request_reads(uid)
    return changed


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
