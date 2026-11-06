"""Create-only, envelope-encrypted space content. No product callers in C1.

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
from google.api_core.exceptions import NotFound, PreconditionFailed

from config import object_lake as config
from utils.other import space_keys
from utils.other.local_storage import create_storage_client

DATA_CLASSES = ('transcript',)
_HEADER = struct.Struct('>4sBI12s')
_bucket_lock = threading.Lock()
_bucket_instance = None
_bucket_name: str | None = None


class ObjectLakeError(Exception):
    """Base error for lake IO and envelope validation."""


class ObjectLakeNotConfigured(ObjectLakeError):
    """No bucket configured or write admission is closed."""


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
    digest = hashlib.sha256(plaintext).hexdigest()
    key = (
        f'{_segment(config.release())}/spaces/{_segment(space_id)}/{_class(data_class)}/{_segment(entity_id)}/{digest}'
    )
    keys = space_keys.get_or_create_space_key(space_id)
    dek = space_keys.unwrap_space_dek(space_id, keys.active_version)
    nonce = os.urandom(12)
    try:
        payload = _HEADER.pack(b'OLK1', 1, keys.active_version, nonce) + AESGCM(dek).encrypt(
            nonce, zlib.compress(plaintext, level=6), key.encode('utf-8')
        )
    finally:
        del dek
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
            return ref
    except ObjectLakeError:
        raise
    except Exception:
        raise LakeFetchError('Lake upload unavailable') from None
    return LakeObjectRef(config.bucket(), key, digest, len(payload), data_class, keys.active_version)


def get_space_object(ref: LakeObjectRef) -> bytes:
    _, sid, _, _, digest = _parse_ref(ref)
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
    magic, envelope_version, dek_version, nonce = _HEADER.unpack_from(payload)
    if magic != b'OLK1' or envelope_version != 1 or dek_version != ref.dek_version:
        raise LakeObjectCorrupt('Invalid lake envelope header')
    dek = space_keys.unwrap_space_dek(sid, dek_version)
    try:
        compressed = AESGCM(dek).decrypt(nonce, payload[_HEADER.size :], ref.key.encode('utf-8'))
        decoder = zlib.decompressobj()
        plaintext = decoder.decompress(compressed) + decoder.flush()
        if not decoder.eof or decoder.unused_data or hashlib.sha256(plaintext).hexdigest() != digest:
            raise LakeObjectCorrupt('Lake plaintext digest or compression mismatch')
        return plaintext
    except (InvalidTag, ValueError, zlib.error):
        raise LakeObjectCorrupt('Lake authentication or decompression failed') from None
    finally:
        del dek


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
