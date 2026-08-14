"""Opaque composite cursor for universal mixed canonical+historical list reads.

Binds query authority (uid, include_archive, include_pending_processing, device
scope) into an HMAC-signed, versioned token so midstream clients cannot widen
access by tampering with the continuation token. Positions for each origin
advance independently so suppressed or filtered rows do not stall the merged
view.

Schema v3 stores exact microsecond keysets (never millisecond truncation) for:
- canonical emitted + raw scan positions
- historical updated_at-present raw scan
- historical created_at-only raw scan

Each historical document is partitioned into exactly one raw stream so dual
keyset continuation cannot omit rows under front inserts/deletes the way
offset paging did.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Optional, cast

_CURSOR_PREFIX = 'uml'
_CURSOR_SCHEMA_VERSION = 3
_DEFAULT_TTL_SECONDS = 86_400
_SOURCE = 'universal_mixed_list'
_READ_MODE = 'newest_first_mixed'


class UniversalListCursorError(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class StreamKeyset:
    """Exact Firestore order key: microsecond timestamp + document id (__name__)."""

    updated_at_us: int
    memory_id: str


@dataclass(frozen=True)
class UniversalListCursorState:
    uid: str
    include_archive: bool
    include_pending_processing: bool
    device_scope: str
    client_device_id: Optional[str]
    canonical: Optional[StreamKeyset]
    canonical_scan: Optional[StreamKeyset]
    historical: Optional[StreamKeyset]
    historical_updated_scan: Optional[StreamKeyset]
    historical_created_scan: Optional[StreamKeyset]
    canonical_exhausted: bool
    historical_updated_exhausted: bool
    historical_created_exhausted: bool


@dataclass(frozen=True)
class UniversalListCursorClaims:
    state: UniversalListCursorState
    expires_at_epoch_seconds: int


def cursor_secret() -> bytes:
    raw_secret = os.environ.get('MEMORY_V3_CURSOR_SECRET') or ''
    if not raw_secret:
        raise UniversalListCursorError('missing_cursor_secret')
    return raw_secret.encode('utf-8')


def cursor_ttl_seconds() -> int:
    raw_ttl = os.environ.get('MEMORY_V3_CURSOR_TTL_SECONDS') or ''
    if not raw_ttl:
        return _DEFAULT_TTL_SECONDS
    try:
        return max(1, int(raw_ttl))
    except ValueError:
        return _DEFAULT_TTL_SECONDS


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')


def _b64decode(value: str) -> bytes:
    padding = '=' * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode((value + padding).encode('ascii'))
    except (ValueError, TypeError) as exc:
        raise UniversalListCursorError('malformed_cursor') from exc


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')


def _signature(payload_segment: str, secret: bytes) -> str:
    return _b64encode(hmac.new(secret, payload_segment.encode('ascii'), hashlib.sha256).digest())


def _keyset_payload(keyset: Optional[StreamKeyset]) -> Optional[dict[str, Any]]:
    if keyset is None:
        return None
    return {'updated_at_us': keyset.updated_at_us, 'memory_id': keyset.memory_id}


def _parse_keyset(payload: Any) -> Optional[StreamKeyset]:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise UniversalListCursorError('malformed_cursor')
    data = cast(dict[str, Any], payload)
    updated_at_us = data.get('updated_at_us')
    memory_id = data.get('memory_id')
    if type(updated_at_us) is not int or updated_at_us < 0:
        raise UniversalListCursorError('malformed_cursor')
    if not isinstance(memory_id, str) or not memory_id.strip():
        raise UniversalListCursorError('malformed_cursor')
    return StreamKeyset(updated_at_us=updated_at_us, memory_id=memory_id)


def encode_universal_list_cursor(
    state: UniversalListCursorState,
    *,
    secret: bytes,
    now_epoch_seconds: Optional[int] = None,
    ttl_seconds: Optional[int] = None,
) -> str:
    now = int(now_epoch_seconds if now_epoch_seconds is not None else time.time())
    ttl = int(ttl_seconds if ttl_seconds is not None else cursor_ttl_seconds())
    payload: dict[str, Any] = {
        'schema_version': _CURSOR_SCHEMA_VERSION,
        'source': _SOURCE,
        'read_mode': _READ_MODE,
        'uid': state.uid,
        'include_archive': bool(state.include_archive),
        'include_pending_processing': bool(state.include_pending_processing),
        'device_scope': state.device_scope,
        'client_device_id': state.client_device_id,
        'canonical': _keyset_payload(state.canonical),
        'canonical_scan': _keyset_payload(state.canonical_scan),
        'historical': _keyset_payload(state.historical),
        'historical_updated_scan': _keyset_payload(state.historical_updated_scan),
        'historical_created_scan': _keyset_payload(state.historical_created_scan),
        'canonical_exhausted': bool(state.canonical_exhausted),
        'historical_updated_exhausted': bool(state.historical_updated_exhausted),
        'historical_created_exhausted': bool(state.historical_created_exhausted),
        'expires_at_epoch_seconds': now + max(1, ttl),
    }
    payload_segment = _b64encode(_canonical_json(payload))
    return f'{_CURSOR_PREFIX}.{payload_segment}.{_signature(payload_segment, secret)}'


def decode_universal_list_cursor(
    cursor: str,
    *,
    uid: str,
    include_archive: bool,
    include_pending_processing: bool,
    device_scope: str,
    client_device_id: Optional[str],
    secret: bytes,
    now_epoch_seconds: Optional[int] = None,
) -> UniversalListCursorClaims:
    parts = cursor.split('.') if cursor else []
    if len(parts) != 3 or parts[0] != _CURSOR_PREFIX:
        raise UniversalListCursorError('malformed_cursor')

    _, payload_segment, signature_segment = parts
    if not hmac.compare_digest(_signature(payload_segment, secret), signature_segment):
        raise UniversalListCursorError('invalid_signature')

    try:
        payload = cast(object, json.loads(_b64decode(payload_segment).decode('utf-8')))
        if not isinstance(payload, dict):
            raise UniversalListCursorError('malformed_cursor')
        data = cast(dict[str, Any], payload)
        if data.get('schema_version') != _CURSOR_SCHEMA_VERSION:
            raise UniversalListCursorError('malformed_cursor')
        if data.get('source') != _SOURCE or data.get('read_mode') != _READ_MODE:
            raise UniversalListCursorError('malformed_cursor')
        required_keys = (
            'canonical_scan',
            'historical_updated_scan',
            'historical_created_scan',
            'include_pending_processing',
            'historical_updated_exhausted',
            'historical_created_exhausted',
        )
        for key in required_keys:
            if key not in data:
                raise UniversalListCursorError('malformed_cursor')
        # Reject retired offset / millisecond cursor fields so old tokens fail closed.
        if 'historical_scan_offset' in data or 'historical_exhausted' in data:
            raise UniversalListCursorError('malformed_cursor')
        for keyset_name in (
            'canonical',
            'canonical_scan',
            'historical',
            'historical_updated_scan',
            'historical_created_scan',
        ):
            keyset_payload = data.get(keyset_name)
            if isinstance(keyset_payload, dict) and 'updated_at_ms' in keyset_payload:
                raise UniversalListCursorError('malformed_cursor')
        expires_at = data.get('expires_at_epoch_seconds')
        if type(expires_at) is not int:
            raise UniversalListCursorError('malformed_cursor')
        state = UniversalListCursorState(
            uid=data['uid'],
            include_archive=bool(data['include_archive']),
            include_pending_processing=bool(data['include_pending_processing']),
            device_scope=str(data['device_scope']),
            client_device_id=data.get('client_device_id'),
            canonical=_parse_keyset(data.get('canonical')),
            canonical_scan=_parse_keyset(data.get('canonical_scan')),
            historical=_parse_keyset(data.get('historical')),
            historical_updated_scan=_parse_keyset(data.get('historical_updated_scan')),
            historical_created_scan=_parse_keyset(data.get('historical_created_scan')),
            canonical_exhausted=bool(data.get('canonical_exhausted')),
            historical_updated_exhausted=bool(data.get('historical_updated_exhausted')),
            historical_created_exhausted=bool(data.get('historical_created_exhausted')),
        )
    except UniversalListCursorError:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise UniversalListCursorError('malformed_cursor') from exc

    now = int(now_epoch_seconds if now_epoch_seconds is not None else time.time())
    if now > expires_at:
        raise UniversalListCursorError('cursor_expired')
    if state.uid != uid:
        raise UniversalListCursorError('uid_mismatch')
    if state.include_archive != bool(include_archive):
        raise UniversalListCursorError('include_archive_mismatch')
    if state.include_pending_processing != bool(include_pending_processing):
        raise UniversalListCursorError('include_pending_processing_mismatch')
    if state.device_scope != device_scope:
        raise UniversalListCursorError('device_scope_mismatch')
    if (state.client_device_id or None) != (client_device_id or None):
        raise UniversalListCursorError('device_scope_mismatch')
    return UniversalListCursorClaims(state=state, expires_at_epoch_seconds=expires_at)


def scope_fingerprint(device_scope: str, client_device_id: Optional[str]) -> str:
    """Stable content-free fingerprint for logging only."""
    material = f'{device_scope}|{client_device_id or ""}'.encode('utf-8')
    return hashlib.sha256(material).hexdigest()[:12]
