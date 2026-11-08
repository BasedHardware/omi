"""Create-only, envelope-encrypted space content. Transcript codec storage.

All operations are synchronous; C2 owns executor dispatch, privacy fences and
pointer admission at the codec seam. Reads never return ciphertext on failure.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
import re
import struct
import threading
import zlib

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.keywrap import InvalidUnwrap, aes_key_unwrap, aes_key_wrap
from google.api_core.exceptions import AlreadyExists, NotFound, PreconditionFailed

from config import object_lake as config
from database.account_deletion_policy import account_deletion_marker_blocks_access
from utils.other import space_keys
from utils.other.local_storage import create_storage_client

# 32 MiB accommodates long transcripts while bounding authenticated zlib expansion.
# Every future class must choose its own reviewed limit before admission.
MAX_PLAINTEXT_BYTES = {'transcript': 32 * 1024 * 1024}
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
    if len(plaintext) > MAX_PLAINTEXT_BYTES[_class(data_class)]:
        raise LakeObjectCorrupt('Lake plaintext exceeds data-class limit')
    digest = hashlib.sha256(plaintext).hexdigest()
    key = (
        f'{_segment(config.release())}/spaces/{_segment(space_id)}/{_class(data_class)}/{_segment(entity_id)}/{digest}'
    )
    _assert_owner_write_allowed(space_id)
    keys, kek = space_keys.active_space_dek(space_id)
    # Two authority reads per put: get/create before encryption and a fresh
    # post-upload check. Share the first snapshot with unwrap, never cache authority.
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
        # Write-ahead intent survives a refused replay, an ambiguous upload
        # result or worker loss before the pointer commits. Never self-delete:
        # another writer may already reference this content-addressed name.
        _record_upload_candidate(config.bucket(), key)
        try:
            blob.upload_from_string(payload, content_type=content_type, if_generation_match=0)
        except PreconditionFailed:
            blob.reload()
            existing = blob.metadata or {}
            if any(existing.get(k) != stamp[k] for k in ('plaintext_sha256', 'space_id', 'data_class')):
                raise LakeObjectConflict('Existing lake object metadata conflicts')
            try:
                size = blob.size
                if size is None:
                    raise LakeObjectConflict('Existing lake object size is unavailable')
                ref = LakeObjectRef(config.bucket(), key, digest, size, data_class, int(existing['dek_version']))
                _parse_ref(ref)
            except (KeyError, TypeError, ValueError, LakeObjectCorrupt):
                raise LakeObjectConflict('Existing lake object metadata is invalid') from None
            _check_put_authority(space_id, blob)
            return ref
        _check_put_authority(space_id, blob)
    except (space_keys.SpaceKeyDestroyed, space_keys.SpaceKeyUnavailable):
        raise
    except ObjectLakeError:
        raise
    except Exception:
        raise LakeFetchError('Lake upload unavailable') from None
    return LakeObjectRef(config.bucket(), key, digest, len(payload), data_class, keys.active_version)


def _record_upload_candidate(bucket: str, key: str) -> None:
    """Durable discovery for C3's janitor, not authorization to delete an object.

    Entries deliberately survive successful commits too: the janitor must
    establish absence of live AND historical references under a writer fence
    before removing any object. No TTL may discard an unresolved candidate.
    """
    candidate_id = hashlib.sha256(f'{bucket}/{key}'.encode('utf-8')).hexdigest()
    candidate = space_keys.space_key_firestore_client().collection('lake_upload_candidates').document(candidate_id)
    snapshot = candidate.get()
    if not snapshot.exists:
        try:
            candidate.create({'bucket': bucket, 'key': key, 'created_at': datetime.now(timezone.utc)})
            return
        except AlreadyExists:
            # A concurrent writer must have made the SAME intent durable.
            snapshot = candidate.get()
    existing = snapshot.to_dict() or {}
    if (
        existing.get('bucket') != bucket
        or existing.get('key') != key
        or not isinstance(existing.get('created_at'), datetime)
        or existing['created_at'].tzinfo is None
    ):
        raise LakeObjectConflict('Existing lake upload candidate is invalid')


def _assert_owner_write_allowed(space_id):
    try:
        # Same customer plane as the key authority, never a cached negative.
        marker = space_keys.space_key_firestore_client().collection('account_deletions').document(space_id).get()
        if account_deletion_marker_blocks_access(
            marker_exists=marker.exists, raw_status=(marker.to_dict() or {}).get('wipe_status')
        ):
            raise LakeWriteFenced('Owner deletion fences lake writes')
    except LakeWriteFenced:
        raise
    except Exception:
        raise LakeFetchError('Lake owner write authority unavailable') from None


def _check_put_authority(space_id, blob):
    try:
        _assert_owner_write_allowed(space_id)
        if space_keys.get_space_keys(space_id) is None:
            raise space_keys.SpaceKeyDestroyed('Space key disappeared during upload')
    except (space_keys.SpaceKeyDestroyed, LakeWriteFenced):
        # An in-flight upload must not outlive a durable destroy fence.
        try:
            blob.delete()
        except NotFound:
            pass
        except Exception:
            raise LakeFetchError('Fenced lake upload cleanup unavailable') from None
        raise


def get_space_object(ref: LakeObjectRef) -> bytes:
    _, sid, data_class, _, digest = _parse_ref(ref)
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
    kek = space_keys.unwrap_space_dek(sid, dek_version)
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
            raise RuntimeError('Lake prefix deletion left objects behind')
        return count
    except (ObjectLakeError, RuntimeError):
        raise
    except Exception:
        raise LakeFetchError('Lake prefix deletion unavailable') from None


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
