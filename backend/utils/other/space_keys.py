"""Per-space envelope keys. No clients, credentials or IO are initialized on import.

Wrapped keys live at space_keys/{space_id}, outside the user subtree. Account
wipe must destroy the wrapped keys LAST, retaining the deletion tombstone (C4). A fresh document read precedes cache
use so another worker's destroy cannot leave a cached key usable for a day.
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import logging
import os
import threading
from typing import Any

from cachetools import TTLCache
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from google.api_core.exceptions import AlreadyExists, FailedPrecondition

from config import object_lake as config

logger = logging.getLogger(__name__)


class SpaceKeyDestroyed(Exception):
    """The space or requested key version no longer exists or is disabled."""


class SpaceKeyUnavailable(Exception):
    """The key service is unavailable; retry without degrading encryption."""


@dataclass(frozen=True)
class SpaceKeyVersion:
    version: int
    wrapped_b64: str
    wrapped_at: str
    state: str


@dataclass(frozen=True)
class SpaceKey:
    space_id: str
    versions: tuple[SpaceKeyVersion, ...]
    active_version: int
    kms_key: str = ''


class FakeKMS:
    """Offline AES-GCM wrapper with an unmistakable, authenticated fake marker."""

    PREFIX = b'FAKEKMS1'

    def _key(self) -> bytes:
        secret = os.getenv('OBJECT_LAKE_KMS_FAKE_SECRET', 'omi-offline-fake-kms-v1')
        return hashlib.sha256(secret.encode()).digest()

    def encrypt(self, *, request):
        nonce = os.urandom(12)
        wrapped = self.PREFIX + nonce + AESGCM(self._key()).encrypt(nonce, request['plaintext'], self.PREFIX)
        return _KMSResult(ciphertext=wrapped)

    def decrypt(self, *, request):
        wrapped = request['ciphertext']
        if not wrapped.startswith(self.PREFIX):
            raise ValueError('Not a FakeKMS envelope')
        nonce = wrapped[len(self.PREFIX) : len(self.PREFIX) + 12]
        plaintext = AESGCM(self._key()).decrypt(nonce, wrapped[len(self.PREFIX) + 12 :], self.PREFIX)
        return _KMSResult(plaintext=plaintext)


@dataclass(frozen=True)
class _KMSResult:
    plaintext: bytes = b''
    ciphertext: bytes = b''


_cache: TTLCache | None = None
_cache_lock = threading.RLock()
_kms_lock = threading.Lock()
_kms_client: Any = None
_did_warn_fake = False


def _kms():
    global _kms_client, _did_warn_fake
    with _kms_lock:
        if not config.kms_key():
            if not _did_warn_fake:
                logger.warning('OBJECT_LAKE_KMS_KEY unset: using offline FakeKMS')
                _did_warn_fake = True
            return FakeKMS()
        if _kms_client is None:
            from google.cloud import kms_v1

            _kms_client = kms_v1.KeyManagementServiceClient()
        return _kms_client


def space_key_firestore_client(firestore_client=None):
    if firestore_client is not None:
        return firestore_client
    from database._client import get_data_plane_firestore_client

    return get_data_plane_firestore_client()


def _space_id(space_id: str) -> str:
    if not space_id or '/' in space_id or space_id in ('.', '..'):
        raise ValueError('space_id must be one nonempty path segment')
    return space_id


@contextmanager
def _key_errors():
    try:
        yield
    except (SpaceKeyDestroyed, SpaceKeyUnavailable):
        raise
    except FailedPrecondition as error:
        if any(word in str(error).lower() for word in ('destroyed', 'disabled')):
            raise SpaceKeyDestroyed('Space key version is destroyed or disabled') from None
        raise SpaceKeyUnavailable('Space key operation unavailable') from None
    except Exception:
        # Do not propagate provider exception bodies: they may contain key material.
        raise SpaceKeyUnavailable('Space key operation unavailable') from None


def _destroyed_tombstone(data: dict, space_id: str) -> bool:
    if data.get('state') != 'destroyed':
        return False
    if (
        set(data) != {'space_id', 'state', 'destroyed_at'}
        or data.get('space_id') != space_id
        or not isinstance(data.get('destroyed_at'), str)
        or not data.get('destroyed_at')
    ):
        raise ValueError('Malformed destroyed space-key authority')
    return True


def _decode(data: dict, space_id: str) -> SpaceKey:
    if _destroyed_tombstone(data, space_id):
        raise SpaceKeyDestroyed('Space key is durably destroyed')
    if data['space_id'] != space_id or data['algo'] != 'AES-256-GCM':
        raise ValueError('Invalid space key document')
    versions = tuple(SpaceKeyVersion(v['version'], v['wrapped'], v['wrapped_at'], v['state']) for v in data['versions'])
    if (
        type(data['active_version']) is not int
        or not isinstance(data['kms_key'], str)
        or not versions
        or len({v.version for v in versions}) != len(versions)
        or any(
            type(v.version) is not int
            or not 1 <= v.version <= 0xFFFFFFFF
            or v.state not in ('active', 'retired')
            or type(v.wrapped_at) is not str
            or not v.wrapped_at
            or type(v.wrapped_b64) is not str
            or not base64.b64decode(v.wrapped_b64, validate=True)
            for v in versions
        )
        or [v.version for v in versions if v.state == 'active'] != [data['active_version']]
    ):
        raise ValueError('Invalid space key versions')
    return SpaceKey(space_id, versions, data['active_version'], data['kms_key'])


def get_space_keys(space_id: str, *, firestore_client=None) -> SpaceKey | None:
    _space_id(space_id)
    with _key_errors():
        snapshot = space_key_firestore_client(firestore_client).collection('space_keys').document(space_id).get()
        return _decode(snapshot.to_dict(), space_id) if snapshot.exists else None


def _wrapped_version(version: int) -> dict:
    raw = os.urandom(32)
    try:
        wrapped = _kms().encrypt(request={'name': config.kms_key(), 'plaintext': raw}).ciphertext
        return {
            'version': version,
            'wrapped': base64.b64encode(wrapped).decode('ascii'),
            'wrapped_at': datetime.now(timezone.utc).isoformat(),
            'state': 'active',
        }
    finally:
        del raw


def get_or_create_space_key(space_id: str, *, firestore_client=None) -> SpaceKey:
    _space_id(space_id)
    with _key_errors():
        client = space_key_firestore_client(firestore_client)
        existing = get_space_keys(space_id, firestore_client=client)
        if existing is not None:
            return existing
        version = _wrapped_version(1)
        now = version['wrapped_at']
        data = {
            'space_id': space_id,
            'algo': 'AES-256-GCM',
            'kms_key': config.kms_key(),
            'active_version': 1,
            'versions': [version],
            'created_at': now,
            'updated_at': now,
        }
        try:
            client.collection('space_keys').document(space_id).create(data)
        except AlreadyExists:
            winner = get_space_keys(space_id, firestore_client=client)
            if winner is None:
                raise SpaceKeyDestroyed('Space key disappeared during creation')
            return winner
        return _decode(data, space_id)


def rotate_space_key(space_id: str, *, firestore_client=None) -> SpaceKey:
    _space_id(space_id)
    with _key_errors():
        from google.cloud.firestore_v1 import transactional

        client = space_key_firestore_client(firestore_client)
        ref = client.collection('space_keys').document(space_id)
        # KMS is outside the transaction (including retries).
        candidate = _wrapped_version(1)

        @transactional
        def rotate(transaction):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists:
                raise SpaceKeyDestroyed('Space key no longer exists')
            data = snapshot.to_dict()
            current = _decode(data, space_id)
            if current.kms_key != config.kms_key():
                raise SpaceKeyUnavailable('KMS resource changes require explicit rewrapping')
            new_version = {**candidate, 'version': max(v.version for v in current.versions) + 1}
            versions = [{**v, 'state': 'retired'} for v in data['versions']] + [new_version]
            patch = {
                'versions': versions,
                'active_version': new_version['version'],
                'updated_at': candidate['wrapped_at'],
            }
            transaction.update(ref, patch)
            return _decode({**data, **patch}, space_id)

        return rotate(client.transaction())


def _key_cache() -> TTLCache:
    global _cache
    ttl = config.key_cache_ttl_seconds()
    if _cache is None or _cache.ttl != ttl:
        _cache = TTLCache(maxsize=10_000, ttl=ttl)
    return _cache


def unwrap_space_dek(space_id: str, version: int, *, firestore_client=None) -> bytes:
    _space_id(space_id)
    with _key_errors():
        client = space_key_firestore_client(firestore_client)
        # Cache only KMS work, never the authority that the document still exists.
        keys = get_space_keys(space_id, firestore_client=client)
        if keys is None:
            raise SpaceKeyDestroyed('Space key no longer exists')
        return _unwrap_keys(client, keys, version)


def _unwrap_keys(client, keys: SpaceKey, version: int) -> bytes:
    with _key_errors():
        space_id = keys.space_id
        stored = next((v for v in keys.versions if v.version == version), None)
        if stored is None:
            raise SpaceKeyDestroyed('Space key version no longer exists')
        cache_key = (id(client), space_id, version, keys.kms_key, stored.wrapped_b64)
        with _cache_lock:
            cache = _key_cache()
            if cache_key in cache:
                return cache[cache_key]
        # KMS calls for unrelated spaces must not serialize on the cache lock.
        raw = (
            _kms()
            .decrypt(request={'name': keys.kms_key, 'ciphertext': base64.b64decode(stored.wrapped_b64, validate=True)})
            .plaintext
        )
        if len(raw) != 32:
            raise SpaceKeyUnavailable('Invalid space key length')
        with _cache_lock:
            _key_cache()[cache_key] = raw
        return raw


def active_space_dek(space_id: str) -> tuple[SpaceKey, bytes]:
    """One fresh key authority read for a put; the caller rechecks after upload."""
    client = space_key_firestore_client()
    keys = get_or_create_space_key(space_id, firestore_client=client)
    return keys, _unwrap_keys(client, keys, keys.active_version)


def _evict_space(space_id: str) -> None:
    with _cache_lock:
        if _cache is not None:
            for key in list(_cache):
                if key[1] == space_id:
                    del _cache[key]


def destroy_space_keys(space_id: str, *, firestore_client=None) -> int:
    _space_id(space_id)
    try:
        with _key_errors():
            from google.cloud.firestore_v1 import transactional

            client = space_key_firestore_client(firestore_client)
            ref = client.collection('space_keys').document(space_id)

            @transactional
            def destroy(transaction):
                snapshot = ref.get(transaction=transaction)
                data = snapshot.to_dict() or {}
                if _destroyed_tombstone(data, space_id):
                    return 0
                # Content-free tombstone survives even a never-created key.
                # Malformed live rows are retryable, never treated as shredded.
                count = len(_decode(data, space_id).versions) if snapshot.exists else 0
                transaction.set(
                    ref,
                    {
                        'space_id': space_id,
                        'state': 'destroyed',
                        'destroyed_at': datetime.now(timezone.utc).isoformat(),
                    },
                )
                return count

            count = destroy(client.transaction())
            verified = ref.get().to_dict() or {}
            if not _destroyed_tombstone(verified, space_id):
                raise SpaceKeyUnavailable('Space key deletion not verified')
            return count
    finally:
        _evict_space(space_id)


def clear_space_key_cache() -> None:
    with _cache_lock:
        if _cache is not None:
            _cache.clear()
