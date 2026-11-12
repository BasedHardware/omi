"""Create-only, envelope-encrypted space content. Transcript codec storage.

All operations are synchronous; C2 owns executor dispatch, privacy fences and
pointer admission at the codec seam. Reads never return ciphertext on failure.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
import hashlib
import os
import re
import struct
import threading
import time
import uuid
import zlib

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.keywrap import InvalidUnwrap, aes_key_unwrap, aes_key_wrap
from google.api_core.exceptions import NotFound, PreconditionFailed
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from config import object_lake as config
from database.account_deletion_policy import account_deletion_marker_blocks_access
from utils.other import space_keys
from utils.other.local_storage import create_storage_client

# 32 MiB accommodates long transcripts while bounding authenticated zlib expansion.
# Every future class must choose its own reviewed limit before admission.
MAX_PLAINTEXT_BYTES = {'transcript': 32 * 1024 * 1024}
# One resumable session per attempt, finalized with one bounded payload PUT.
_MAX_SINGLE_REQUEST_BYTES = 8 * 1024 * 1024
DATA_CLASSES = tuple(MAX_PLAINTEXT_BYTES)
_HEADER = struct.Struct('>4sBI12s')
_HEADER_V2 = struct.Struct('>4sBI12s40s')
_PREFIX = struct.Struct('>4sB')
_bucket_lock = threading.Lock()
_bucket_instance = None
_bucket_name: str | None = None


class ObjectLakeError(Exception):
    """Base error for lake IO and envelope validation."""


class ObjectLakeNotConfigured(ObjectLakeError):
    """No bucket configured or write admission is closed."""


class LakeWriteFenced(ObjectLakeError):
    """Durable owner deletion forbids a new lake write."""


class LakeObjectAbsent(ObjectLakeError):
    """The blob no longer exists (deleted)."""


class LakeFetchError(ObjectLakeError):
    """Storage operation failed; the pointer must remain unresolved."""


class LakePurgeIncomplete(LakeFetchError):
    """Verified absence failed; retain documents and retry deletion."""


class LakeWriteDeadlineExceeded(LakeFetchError):
    """An expired put cannot publish a pointer; its intent remains discoverable."""


class LakeObjectCorrupt(ObjectLakeError):
    """Envelope, authentication or plaintext digest verification failed."""


class LakeObjectConflict(ObjectLakeError):
    """A create-only name already has incompatible metadata."""


@dataclass(frozen=True)
class ConsentStamp:
    consent: str
    policy_version: str
    consented_at: str

    def __post_init__(self):
        if self.consent not in ('opt_in', 'opt_out', 'unknown'):
            raise ValueError('Invalid consent state')


@dataclass(frozen=True)
class LakeObjectRef:
    bucket: str
    key: str
    sha256: str
    bytes: int
    data_class: str
    dek_version: int

    def to_pointer_dict(self) -> dict:
        return {
            'bucket': self.bucket,
            'key': self.key,
            'sha256': self.sha256,
            'bytes': self.bytes,
            'class': self.data_class,
            'dek_version': self.dek_version,
        }

    @classmethod
    def from_pointer_dict(cls, pointer: dict) -> LakeObjectRef:
        try:
            ref = cls(*(pointer[key] for key in ('bucket', 'key', 'sha256', 'bytes', 'class', 'dek_version')))
            _parse_ref(ref)
            return ref
        except (KeyError, TypeError, ValueError):
            raise LakeObjectCorrupt('Invalid lake pointer') from None


def _segment(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value in ('.', '..')
        or any(c in value for c in ('/', '\\'))
        or any(ord(c) < 32 for c in value)
    ):
        raise ValueError('Lake identifiers must be nonempty path segments')
    return value


def _class(data_class: str) -> str:
    if data_class not in DATA_CLASSES:
        raise ValueError('Unsupported lake data class')
    return data_class


def _parse_ref(ref: LakeObjectRef) -> tuple[str, str, str, str, str]:
    try:
        release, spaces, sid, data_class, entity_id, digest = ref.key.split('/')
        for segment in (release, sid, entity_id):
            _segment(segment)
        _class(data_class)
        _segment(ref.bucket)
        if (
            spaces != 'spaces'
            or re.fullmatch(r'[0-9a-f]{64}', digest) is None
            or ref.sha256 != digest
            or ref.data_class != data_class
            or type(ref.bytes) is not int
            or ref.bytes < _HEADER.size + 16
            or ref.bytes > MAX_PLAINTEXT_BYTES[data_class] + 65536
            or type(ref.dek_version) is not int
            or not 1 <= ref.dek_version <= 0xFFFFFFFF
            or not ref.bucket
        ):
            raise ValueError('Invalid pointer fields')
        return release, sid, data_class, entity_id, digest
    except (AttributeError, TypeError, ValueError):
        raise LakeObjectCorrupt('Invalid lake pointer') from None


def _lake_bucket():
    global _bucket_instance, _bucket_name
    name = config.bucket()
    if not name:
        raise ObjectLakeNotConfigured('BUCKET_OBJECT_LAKE is unset')
    with _bucket_lock:
        if _bucket_instance is None or _bucket_name != name:
            _bucket_instance = create_storage_client().bucket(name)
            _bucket_name = name
        return _bucket_instance


def _bucket_for(ref: LakeObjectRef):
    if not config.bucket():
        raise ObjectLakeNotConfigured('BUCKET_OBJECT_LAKE is unset')
    if ref.bucket != config.bucket():
        raise LakeObjectCorrupt('Lake pointer bucket does not match configured bucket')
    return _lake_bucket()


def put_space_object(
    space_id: str,
    data_class: str,
    entity_id: str,
    plaintext: bytes,
    *,
    consent: ConsentStamp | None = None,
    content_type: str = 'application/octet-stream',
) -> LakeObjectRef:
    if not config.bucket() or not config.write_admitted(space_id):
        raise ObjectLakeNotConfigured('Lake writes are not configured or admitted')
    deadline = time.monotonic() + config.put_deadline_seconds()
    if len(plaintext) > MAX_PLAINTEXT_BYTES[_class(data_class)]:
        raise LakeObjectCorrupt('Lake plaintext exceeds data-class limit')
    digest = hashlib.sha256(plaintext).hexdigest()
    key = (
        f'{_segment(config.release())}/spaces/{_segment(space_id)}/{_class(data_class)}/{_segment(entity_id)}/{digest}'
    )
    _assert_owner_write_allowed(space_id, entity_id)
    keys, kek = space_keys.active_space_dek(space_id)
    # Key authority is read before encryption and again after upload. The
    # candidate transaction also reads both deletion fences before its write.
    # Share the first key snapshot with unwrap; never cache authority.
    try:
        dek = os.urandom(32)
        try:
            nonce = os.urandom(12)
            wrapped = aes_key_wrap(kek, dek)
            payload = _HEADER_V2.pack(b'OLK1', 2, keys.active_version, nonce, wrapped) + AESGCM(dek).encrypt(
                nonce, zlib.compress(plaintext, level=6), key.encode('utf-8')
            )
        finally:
            del dek
    finally:
        del kek
    if len(payload) > _MAX_SINGLE_REQUEST_BYTES:
        raise LakeObjectCorrupt('Lake payload exceeds single-request upload limit')
    stamp = {
        'space_id': space_id,
        'data_class': data_class,
        'dek_version': str(keys.active_version),
        'plaintext_sha256': digest,
        'created_day': datetime.now(timezone.utc).date().isoformat(),
        'consent': consent.consent if consent else 'unknown',
        'consent_policy_version': str(consent.policy_version) if consent else '',
        'consented_at': str(consent.consented_at) if consent else '',
    }
    # Fixed metadata surface; reject oversized consent values before any upload.
    if sum(len(k.encode()) + len(v.encode()) for k, v in stamp.items()) > 8192:
        raise ValueError('Lake metadata exceeds 8 KiB')
    try:
        blob = _lake_bucket().blob(key)
        blob.metadata = stamp
        try:
            session = _UploadSession.create(blob, payload, content_type, deadline)
        except PreconditionFailed:
            # Initiation sent no bytes and issued no capability. Still record
            # settled discovery for the reused object under both owner fences.
            attempt = _record_upload_candidate(config.bucket(), key, None, 0)
            ref = _replay_object(blob, stamp, digest, data_class, deadline)
            _check_put_authority(space_id, entity_id, blob, created=False, deadline=deadline, attempt=attempt)
            if _settle_upload_candidate(config.bucket(), key, attempt, delete_if_fenced=True):
                raise LakeWriteFenced('Deletion fenced the upload')
            return ref
        # Discovery commits before any payload bytes; failure cancels the empty
        # session. An ambiguous finalize keeps the session discoverable.
        with _upload_candidate(config.bucket(), key, session, len(payload), blob.bucket.client) as attempt:
            try:
                _UploadSession.put_all(blob.bucket.client, session, payload, deadline, blob=blob)
            except PreconditionFailed:
                # Settlement drops the session URI, so first prove this session
                # terminal; a non-terminal status raises and keeps it discoverable.
                _fence_upload_attempt({'session': session, 'size': len(payload)}, blob.bucket.client)
                ref = _replay_object(blob, stamp, digest, data_class, deadline)
                _check_put_authority(space_id, entity_id, blob, created=False, deadline=deadline, attempt=attempt)
                return ref
            _check_put_authority(space_id, entity_id, blob, created=True, deadline=deadline, attempt=attempt)
    except (space_keys.SpaceKeyDestroyed, space_keys.SpaceKeyUnavailable):
        raise
    except ObjectLakeError:
        raise
    except Exception:
        raise LakeFetchError('Lake upload unavailable') from None
    return LakeObjectRef(config.bucket(), key, digest, len(payload), data_class, keys.active_version)


class _UploadSession:
    """Only transport seam for sensitive resumable capabilities; never expose errors/URLs."""

    @staticmethod
    def create(blob: Any, payload: bytes, content_type: str, deadline: float) -> str:
        try:
            remaining = _remaining_put_seconds(deadline)
            return blob.create_resumable_upload_session(
                content_type=content_type,
                size=len(payload),
                if_generation_match=0,
                timeout=(remaining / 2, remaining / 2),
                retry=None,
            )
        except PreconditionFailed:
            raise PreconditionFailed('Lake create-only object exists') from None
        except ObjectLakeError:
            raise
        except Exception:
            raise LakeFetchError('Lake session creation unavailable') from None

    @staticmethod
    def _request(
        client: Any,
        session: str,
        method: str,
        *,
        data=b'',
        headers=None,
        timeout: tuple[float, float] = (5, 5),
        blob: Any = None,
    ) -> int:
        try:
            response = client._http.request(
                method,
                session,
                data=data,
                headers=headers or {},
                timeout=timeout,
                allow_redirects=False,
            )
            try:
                if blob is not None and response.status_code in (200, 201):
                    # Match the SDK upload path: retain the generation returned
                    # by finalize for the post-put conditional deletion.
                    properties = response.json()
                    if not properties.get('generation'):
                        raise LakeFetchError('Lake upload generation unavailable')
                    blob._set_properties(properties)
                return response.status_code
            finally:
                response.close()
        except Exception:
            raise LakeFetchError('Lake session transport unavailable') from None

    @classmethod
    def put_all(cls, client: Any, session: str, payload: bytes, deadline: float, *, blob: Any = None) -> None:
        remaining = _remaining_put_seconds(deadline)
        status = cls._request(
            client,
            session,
            'PUT',
            data=payload,
            # One final chunk names its whole range (measured: GCS finalizes it).
            headers={
                'Content-Length': str(len(payload)),
                'Content-Range': f'bytes 0-{len(payload) - 1}/{len(payload)}',
            },
            timeout=(remaining / 2, remaining / 2),
            blob=blob,
        )
        if status == 412:
            raise PreconditionFailed('Lake create-only object exists')
        if status not in (200, 201):
            raise LakeFetchError('Lake session upload unavailable')

    @classmethod
    def cancel(cls, client: Any, session: str) -> None:
        cls._request(client, session, 'DELETE')

    @classmethod
    def status(cls, client: Any, session: str, size: int) -> int:
        # The documented status query names the session's declared total size.
        return cls._request(client, session, 'PUT', headers={'Content-Length': '0', 'Content-Range': f'bytes */{size}'})


def _replay_object(blob, stamp, digest, data_class, deadline):
    remaining = _remaining_put_seconds(deadline)
    gcs: Any = blob
    gcs.reload(timeout=(remaining / 2, remaining / 2), retry=None)
    existing = blob.metadata or {}
    if any(existing.get(k) != stamp[k] for k in ('plaintext_sha256', 'space_id', 'data_class')):
        raise LakeObjectConflict('Existing lake object metadata conflicts')
    try:
        if blob.size is None:
            raise ValueError('Missing size')
        ref = LakeObjectRef(config.bucket(), blob.name, digest, blob.size, data_class, int(existing['dek_version']))
        _parse_ref(ref)
        return ref
    except (KeyError, TypeError, ValueError, LakeObjectCorrupt):
        raise LakeObjectConflict('Existing lake object metadata is invalid') from None


@contextmanager
def _upload_candidate(bucket: str, key: str, session: str, size: int, client):
    try:
        attempt = _record_upload_candidate(bucket, key, session, size)
    except BaseException:
        try:
            _UploadSession.cancel(client, session)
        except Exception:
            pass
        raise
    yield attempt
    if _settle_upload_candidate(bucket, key, attempt, delete_if_fenced=True):
        raise LakeWriteFenced('Deletion fenced the upload')
    # Only a returned put settles. Lost/ambiguous requests retain the session
    # until deletion cancels it and proves terminal storage status.


def _record_upload_candidate(bucket: str, key: str, session: str | None, size: int) -> str:
    """Commit discovery before put, serialized against durable deletion fences.

    Intents survive successful commits and ambiguous uploads for C3's janitor.
    A fence read in this transaction prevents a crashed, delayed writer from
    recreating an owner-derived intent after account wipe's final scan.
    """
    _, _, space_id, _, entity_id, _ = key.split('/')
    attempt = uuid.uuid4().hex
    candidate_id = hashlib.sha256(f'{bucket}/{key}'.encode('utf-8')).hexdigest()
    client = space_keys.space_key_firestore_client()
    candidate = client.collection('lake_upload_candidates').document(candidate_id)

    @firestore.transactional
    def record(transaction):
        _assert_owner_write_allowed(space_id, entity_id, firestore_client=client, transaction=transaction)
        snapshot = candidate.get(transaction=transaction)
        existing = snapshot.to_dict() or {}
        if snapshot.exists and (
            existing.get('bucket') != bucket
            or existing.get('key') != key
            or not isinstance(existing.get('created_at'), datetime)
            or existing['created_at'].tzinfo is None
        ):
            raise LakeObjectConflict('Existing lake upload candidate is invalid')
        pending = dict(_candidate_pending(existing)) if snapshot.exists else {}
        if session is not None:
            pending[attempt] = {'admitted_at': firestore.SERVER_TIMESTAMP, 'session': session, 'size': size}
        state = {'admitted_at': firestore.SERVER_TIMESTAMP, 'in_flight': pending, 'settled': not pending}
        if snapshot.exists:
            transaction.update(candidate, state)
        else:
            transaction.create(
                candidate,
                {
                    'bucket': bucket,
                    'key': key,
                    'created_at': firestore.SERVER_TIMESTAMP,
                    **state,
                },
            )

    record(client.transaction())
    return attempt


def _settle_upload_candidate(bucket: str, key: str, attempt: str, *, delete_if_fenced: bool = False) -> bool:
    """Settle only this request; a concurrent upload of the same key stays live.

    Returns True when a deletion fence purged the object during settlement.
    """
    client = space_keys.space_key_firestore_client()
    candidate_id = hashlib.sha256(f'{bucket}/{key}'.encode('utf-8')).hexdigest()
    candidate = client.collection('lake_upload_candidates').document(candidate_id)
    _, _, space_id, _, entity_id, _ = key.split('/')
    tombstone = client.collection('users').document(space_id).collection('deleted_conversations').document(entity_id)

    # Storage IO stays outside the transaction, so the transaction re-reads
    # the tombstone. A fence that lands after the pre-read keeps this attempt
    # in flight until its object is purged, so deletion still owns
    # it and the caller never receives a reference to an erased object.
    purged = delete_if_fenced and tombstone.get().exists
    if purged:
        _delete_candidate_object({'bucket': bucket, 'key': key})

    marker = client.collection('account_deletions').document(space_id)

    @firestore.transactional
    def settle(transaction, purged):
        conversation_fenced = tombstone.get(transaction=transaction).exists
        marker_snapshot = marker.get(transaction=transaction)
        # Either durable fence that won after the put's authority check owns
        # the object: purge it before settling and refuse the reference.
        fenced = conversation_fenced or account_deletion_marker_blocks_access(
            marker_exists=marker_snapshot.exists, raw_status=(marker_snapshot.to_dict() or {}).get('wipe_status')
        )
        snapshot = candidate.get(transaction=transaction)
        if not snapshot.exists:
            # Never recreate discovery after the wipe's final erasure, and never
            # hand out a reference that erasure may already have removed.
            return delete_if_fenced and not purged
        if fenced and delete_if_fenced and not purged:
            return True
        pending = dict((snapshot.to_dict() or {}).get('in_flight', {}))
        pending.pop(attempt, None)
        if purged and not pending and conversation_fenced:
            transaction.delete(candidate)
        else:
            transaction.update(candidate, {'in_flight': pending, 'settled': not pending})
        return False

    if settle(client.transaction(), purged):
        _delete_candidate_object({'bucket': bucket, 'key': key})
        purged = True
        settle(client.transaction(), purged)
    return purged


def _space_candidate_key_range(space_id: str) -> tuple[str, str]:
    prefix = f'{_segment(config.release())}/spaces/{_segment(space_id)}/'
    return prefix, prefix[:-1] + '0'


def assert_space_uploads_quiescent(space_id: str, *, firestore_client=None) -> None:
    """Cancel every pending upload and prove terminal status before final purge."""
    try:
        client = firestore_client if firestore_client is not None else space_keys.space_key_firestore_client()
        lo, hi = _space_candidate_key_range(space_id)
        collection = client.collection('lake_upload_candidates')
        query = collection.where(filter=FieldFilter('key', '>=', lo)).where(filter=FieldFilter('key', '<', hi))
        for snapshot in query.stream():
            _fence_candidate_attempts(snapshot.to_dict() or {})
    except ObjectLakeError:
        raise
    except Exception:
        raise LakeFetchError('Lake upload fencing unavailable') from None


def _candidate_pending(row: dict) -> dict:
    pending = row.get('in_flight', {'legacy': row.get('created_at')})
    if (
        not isinstance(pending, dict)
        or row.get('settled') is True
        and pending
        or pending == {}
        and row.get('settled') is not True
    ):
        raise LakeFetchError('Lake upload candidate state invalid')
    for attempt, value in pending.items():
        if not isinstance(attempt, str) or not attempt:
            raise LakeFetchError('Lake upload candidate state invalid')
        if isinstance(value, datetime) and value.tzinfo is not None:
            continue  # Valid legacy state, but cannot be fenced.
        if (
            attempt == 'legacy'
            or not isinstance(value, dict)
            or set(value) != {'admitted_at', 'session', 'size'}
            or not isinstance(value['admitted_at'], datetime)
            or value['admitted_at'].tzinfo is None
            or not isinstance(value['session'], str)
            or not value['session'].strip()
            or type(value['size']) is not int
            or not 0 < value['size'] <= _MAX_SINGLE_REQUEST_BYTES
        ):
            raise LakeFetchError('Lake upload candidate state invalid')
    return pending


# Allowlist, measured against GCS (dev bucket, 2026-11-09): finalize -> 200 on
# status and on cancel; cancel -> 499 on every later status/cancel/upload; a
# generation-0 finalize refusal -> 412 on every later status/cancel/upload, and
# the session cannot create the object even after it is deleted. 404 and 410
# mean the service no longer knows the session, so it cannot finalize.
# Everything else (400 request errors, auth, throttling, 308 open, 5xx) is not
# proof and fails closed.
_FINALIZED_SESSION_STATUSES = frozenset({200, 201})
_TERMINAL_SESSION_STATUSES = _FINALIZED_SESSION_STATUSES | {404, 410, 412, 499}


def _fence_upload_attempt(attempt: dict, client: Any = None) -> None:
    client = client if client is not None else create_storage_client()
    _UploadSession.cancel(client, attempt['session'])
    status = _UploadSession.status(client, attempt['session'], attempt['size'])
    if status not in _TERMINAL_SESSION_STATUSES:
        raise LakeFetchError('Lake upload session is not terminal')


def _fence_candidate_attempts(row: dict) -> None:
    for name, attempt in _candidate_pending(row).items():
        if name == 'legacy' or isinstance(attempt, datetime):
            raise LakeFetchError('Legacy lake upload attempt cannot be fenced')
        _fence_upload_attempt(attempt)


def _delete_candidate_object(row: dict) -> None:
    """Purge the recorded binding even after bucket config changes or is removed."""
    bucket_name, key = row.get('bucket'), row.get('key')
    try:
        bucket_name = _segment(bucket_name)
        if not isinstance(key, str) or len(key.split('/')) != 6:
            raise ValueError('Invalid candidate key')
        for segment in key.split('/'):
            _segment(segment)
        bucket = _lake_bucket() if bucket_name == config.bucket() else create_storage_client().bucket(bucket_name)
        blob = bucket.blob(key)
        try:
            blob.delete()
        except NotFound:
            pass
        if blob.exists():
            raise LakePurgeIncomplete('Lake candidate object remains after deletion')
    except ObjectLakeError:
        raise
    except Exception:
        raise LakeFetchError('Lake candidate recorded-bucket purge unavailable') from None


def delete_entity_upload_candidates(space_id: str, entity_id: str, *, firestore_client=None) -> int:
    """Fence sessions, delete recorded objects, then compare-and-erase discovery."""
    try:
        client = firestore_client if firestore_client is not None else space_keys.space_key_firestore_client()
        tombstone = (
            client.collection('users').document(space_id).collection('deleted_conversations').document(entity_id)
        )
        base = f'{_segment(config.release())}/spaces/{_segment(space_id)}/'
        collection = client.collection('lake_upload_candidates')

        @firestore.transactional
        def erase(transaction, candidate, purged_row):
            if not tombstone.get(transaction=transaction).exists:
                raise LakeWriteFenced('Candidate purge requires conversation deletion fence')
            snapshot = candidate.get(transaction=transaction)
            row = snapshot.to_dict() or {}
            # Admission is fenced, but settlement can race storage IO. Retry any
            # changed state rather than erase discovery we have not checked.
            if snapshot.exists:
                if row != purged_row:
                    raise LakeFetchError('Lake upload candidate changed; retry deletion')
                transaction.delete(candidate)
                return 1
            return 0

        count = 0
        for data_class in DATA_CLASSES:
            lo = f'{base}{data_class}/{_segment(entity_id)}/'
            hi = lo[:-1] + '0'
            query = collection.where(filter=FieldFilter('key', '>=', lo)).where(filter=FieldFilter('key', '<', hi))
            for snapshot in query.stream():
                if not tombstone.get().exists:
                    raise LakeWriteFenced('Candidate purge requires conversation deletion fence')
                row = snapshot.to_dict() or {}
                _fence_candidate_attempts(row)
                _delete_candidate_object(row)
                count += erase(client.transaction(), collection.document(snapshot.id), row)
        return count
    except ObjectLakeError:
        raise
    except Exception:
        raise LakeFetchError('Lake conversation upload candidate purge unavailable') from None


def _assert_owner_write_allowed(space_id, entity_id, *, firestore_client=None, transaction=None):
    try:
        # Same customer plane as the key authority, never a cached negative.
        client = firestore_client if firestore_client is not None else space_keys.space_key_firestore_client()
        marker = client.collection('account_deletions').document(space_id).get(transaction=transaction)
        if account_deletion_marker_blocks_access(
            marker_exists=marker.exists, raw_status=(marker.to_dict() or {}).get('wipe_status')
        ):
            raise LakeWriteFenced('Owner deletion fences lake writes')
        tombstone = (
            client.collection('users').document(space_id).collection('deleted_conversations').document(entity_id)
        )
        if tombstone.get(transaction=transaction).exists:
            raise LakeWriteFenced('Conversation deletion fences lake writes')
    except LakeWriteFenced:
        raise
    except Exception:
        raise LakeFetchError('Lake owner write authority unavailable') from None


def _remaining_put_seconds(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise LakeWriteDeadlineExceeded('Lake put deadline exceeded')
    return remaining


def _check_put_authority(space_id, entity_id, blob, *, created, deadline, attempt):
    try:
        _assert_owner_write_allowed(space_id, entity_id)
        if space_keys.get_space_keys(space_id) is None:
            raise space_keys.SpaceKeyDestroyed('Space key disappeared during upload')
        # Expiry alone is not a deletion fence: another writer may already
        # reference this name. Retain the blob and discovery intent on expiry.
        _remaining_put_seconds(deadline)
    except (space_keys.SpaceKeyDestroyed, LakeWriteFenced):
        # Only this newly created candidate is ours to remove. A create-only
        # retry may have reused a referenced object; the purge owns that object.
        # The candidate cannot acquire a live reference after the durable
        # account/conversation fence, and its pointer has not been returned.
        if not created:
            # Preserve the referenced object and its discovery until the
            # deleting orchestrator purges it; a replay did not create it.
            _settle_upload_candidate(config.bucket(), blob.name, attempt)
            raise
        try:
            blob.delete(if_generation_match=blob.generation)
        except NotFound:
            pass
        except Exception:
            raise LakeFetchError('Fenced lake upload cleanup unavailable') from None
        # Remove discovery only after our late generation is absent and every
        # same-key attempt has settled under the conversation tombstone.
        _settle_upload_candidate(config.bucket(), blob.name, attempt, delete_if_fenced=True)
        raise


def get_space_object(ref: LakeObjectRef) -> bytes:
    _, sid, data_class, _, digest = _parse_ref(ref)
    # Destroyed authority wins over missing blobs for retained stale pointers.
    try:
        kek = space_keys.unwrap_space_dek(sid, ref.dek_version)
    except space_keys.SpaceKeyDestroyed:
        # A fabricated version in a live space is corrupt, while a destroyed
        # authority remains the explicit shredded state. get_space_keys raises
        # SpaceKeyDestroyed again for a tombstone; only live/missing rows return.
        keys = space_keys.get_space_keys(sid)
        if keys is not None and all(version.version != ref.dek_version for version in keys.versions):
            raise LakeObjectCorrupt('Invalid lake key version') from None
        raise
    try:
        try:
            payload = _bucket_for(ref).blob(ref.key).download_as_bytes()
        except ObjectLakeError:
            raise
        except NotFound:
            raise LakeObjectAbsent('Lake object is absent') from None
        except Exception:
            raise LakeFetchError('Lake download unavailable') from None
        if len(payload) != ref.bytes or len(payload) < _HEADER.size + 16:
            raise LakeObjectCorrupt('Lake envelope length mismatch')
        magic, envelope_version = _PREFIX.unpack_from(payload)
        if magic != b'OLK1' or envelope_version not in (1, 2):
            raise LakeObjectCorrupt('Invalid lake envelope header')
        header = _HEADER if envelope_version == 1 else _HEADER_V2
        if len(payload) < header.size + 16:
            raise LakeObjectCorrupt('Lake envelope length mismatch')
        _, _, dek_version, nonce, *wrapped = header.unpack_from(payload)
        if dek_version != ref.dek_version:
            raise LakeObjectCorrupt('Invalid lake envelope header')
        try:
            # v1 used the space key directly. v2 uses it only for nonce-less AES-KW;
            # each random object DEK performs exactly one GCM encryption.
            dek = kek if envelope_version == 1 else aes_key_unwrap(kek, wrapped[0])
            try:
                compressed = AESGCM(dek).decrypt(nonce, payload[header.size :], ref.key.encode('utf-8'))
            finally:
                del dek
            decoder = zlib.decompressobj()
            limit = MAX_PLAINTEXT_BYTES[data_class]
            plaintext = decoder.decompress(compressed, limit + 1)
            if len(plaintext) > limit or decoder.unconsumed_tail:
                raise LakeObjectCorrupt('Lake plaintext exceeds data-class limit')
            if not decoder.eof or decoder.unused_data or hashlib.sha256(plaintext).hexdigest() != digest:
                raise LakeObjectCorrupt('Lake plaintext digest or compression mismatch')
            return plaintext
        except (InvalidTag, InvalidUnwrap, ValueError, zlib.error):
            raise LakeObjectCorrupt('Lake authentication or decompression failed') from None
    finally:
        del kek


def delete_space_object(ref: LakeObjectRef) -> bool:
    _parse_ref(ref)
    try:
        _bucket_for(ref).blob(ref.key).delete()
        return True
    except ObjectLakeError:
        raise
    except NotFound:
        return False
    except Exception:
        raise LakeFetchError('Lake deletion unavailable') from None


def delete_space_prefix(space_id: str, *, data_class=None, entity_id=None) -> int:
    prefix = f'{_segment(config.release())}/spaces/{_segment(space_id)}/'
    if entity_id is not None and data_class is None:
        raise ValueError('entity_id requires data_class')
    if data_class is not None:
        prefix += _class(data_class) + '/'
    if entity_id is not None:
        prefix += _segment(entity_id) + '/'
    return _purge_prefix(prefix)


def delete_space_entity(space_id: str, entity_id: str) -> int:
    prefix = f'{_segment(config.release())}/spaces/{_segment(space_id)}/'
    entity_id = _segment(entity_id)
    return sum(_purge_prefix(f'{prefix}{data_class}/{entity_id}/') for data_class in DATA_CLASSES)


def _purge_prefix(prefix: str) -> int:
    try:
        bucket = _lake_bucket()
        count = 0
        for blob in bucket.list_blobs(prefix=prefix):
            try:
                blob.delete()
                count += 1
            except NotFound:
                pass
        if any(bucket.list_blobs(prefix=prefix)):
            raise LakePurgeIncomplete('Lake prefix deletion left objects behind')
        return count
    except (ObjectLakeError, RuntimeError):
        raise
    except Exception:
        raise LakeFetchError('Lake prefix deletion unavailable') from None


def delete_space_upload_candidates(space_id: str, *, firestore_client=None) -> int:
    """Erase user-derived intents after the fenced owner prefix is verified absent.

    Key-range discovery also covers abandoned intents with no object or pointer.
    No bucket filter: a config change must not strand the owner's old intents.
    The release pin matches delete_space_prefix; widen both on a release bump.
    """
    try:
        client = firestore_client if firestore_client is not None else space_keys.space_key_firestore_client()
        lo, hi = _space_candidate_key_range(space_id)
        collection = client.collection('lake_upload_candidates')
        query = collection.where(filter=FieldFilter('key', '>=', lo)).where(filter=FieldFilter('key', '<', hi))
        marker = client.collection('account_deletions').document(space_id)

        @firestore.transactional
        def erase(transaction, candidate, purged_row):
            status = (marker.get(transaction=transaction).to_dict() or {}).get('wipe_status')
            if status != 'running':
                raise LakeWriteFenced('Candidate purge requires running account wipe')
            snapshot = candidate.get(transaction=transaction)
            if snapshot.exists:
                if snapshot.to_dict() != purged_row:
                    raise LakeFetchError('Lake upload candidate changed; retry deletion')
                transaction.delete(candidate)
                return 1
            return 0

        count = 0
        for snapshot in query.stream():
            row = snapshot.to_dict() or {}
            _fence_candidate_attempts(row)
            _delete_candidate_object(row)
            count += erase(client.transaction(), collection.document(snapshot.id), row)
        if next(iter(query.limit(1).stream()), None) is not None:
            raise LakeFetchError('Lake upload candidates remain after purge')
        return count
    except ObjectLakeError:
        raise
    except Exception:
        raise LakeFetchError('Lake upload candidate purge unavailable') from None


def verify_space_object(ref: LakeObjectRef, *, deep: bool = False) -> bool:
    try:
        _parse_ref(ref)
        if deep:
            return hashlib.sha256(get_space_object(ref)).hexdigest() == ref.sha256
        blob = _bucket_for(ref).blob(ref.key)
        blob.reload()
        return blob.size == ref.bytes and (blob.metadata or {}).get('plaintext_sha256') == ref.sha256
    except ObjectLakeNotConfigured:
        raise
    except (ObjectLakeError, NotFound, space_keys.SpaceKeyDestroyed):
        return False
    except space_keys.SpaceKeyUnavailable:
        raise
    except Exception:
        raise LakeFetchError('Lake verification unavailable') from None
