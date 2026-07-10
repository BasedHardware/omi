"""Canonical module for ``utils.memory.v3_cursor`` (WS-G8b).

Neutral ``v3_cursor`` is the source of truth. Legacy ``v3_cursor`` remains an importable alias.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, cast

_CURSOR_PREFIX = 'v3'
_CURSOR_SCHEMA_VERSION = 1
_KEYSET_ORDER = ('created_at_desc', 'memory_id_desc')
_DEFAULT_MAX_LIMIT = 500
_LEGACY_FIRST_PAGE_OVERRIDE_LIMIT = 5000


class V3CursorError(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class V3Keyset:
    created_at_ms: int
    memory_id: str


@dataclass(frozen=True)
class V3CursorContext:
    uid: str
    account_generation: int
    projection_generation: int
    filter_hash: str
    source: str
    read_mode: str
    now_epoch_seconds: int


@dataclass(frozen=True)
class V3CursorClaims:
    uid: str
    account_generation: int
    projection_generation: int
    filter_hash: str
    source: str
    read_mode: str
    keyset: V3Keyset
    expires_at_epoch_seconds: int
    keyset_order: tuple[str, str] = _KEYSET_ORDER


@dataclass(frozen=True)
class V3CursorPageRequest:
    limit: int
    cursor: str | None
    allows_offset: bool = False
    applies_first_page_5000_override: bool = False


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')


def _b64decode(value: str) -> bytes:
    padding = '=' * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode((value + padding).encode('ascii'))
    except (ValueError, TypeError):
        raise V3CursorError('malformed_cursor')


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')


def _signature(payload_segment: str, secret: bytes) -> str:
    return _b64encode(hmac.new(secret, payload_segment.encode('ascii'), hashlib.sha256).digest())


def create_v3_cursor(
    keyset: V3Keyset,
    context: V3CursorContext,
    secret: bytes,
    *,
    ttl_seconds: int,
) -> str:
    """Create an opaque, HMAC-signed memory `/v3` keyset cursor.

    Pure/local only: no route, Firestore, Pinecone, provider, network, or
    mutation work occurs here. Runtime `/v3` wiring remains a later blocked
    slice.
    """

    payload: dict[str, Any] = {
        'schema_version': _CURSOR_SCHEMA_VERSION,
        'uid': context.uid,
        'account_generation': context.account_generation,
        'projection_generation': context.projection_generation,
        'filter_hash': context.filter_hash,
        'source': context.source,
        'read_mode': context.read_mode,
        'keyset_order': list(_KEYSET_ORDER),
        'keyset': {
            'created_at_ms': keyset.created_at_ms,
            'memory_id': keyset.memory_id,
        },
        'expires_at_epoch_seconds': context.now_epoch_seconds + ttl_seconds,
    }
    payload_segment = _b64encode(_canonical_json(payload))
    return f'{_CURSOR_PREFIX}.{payload_segment}.{_signature(payload_segment, secret)}'


def parse_v3_cursor(cursor: str, context: V3CursorContext, secret: bytes) -> V3CursorClaims:
    parts = cursor.split('.') if cursor else []
    if len(parts) != 3 or parts[0] != _CURSOR_PREFIX:
        raise V3CursorError('malformed_cursor')

    _, payload_segment, signature_segment = parts
    if not hmac.compare_digest(_signature(payload_segment, secret), signature_segment):
        raise V3CursorError('invalid_signature')

    try:
        payload = cast(object, json.loads(_b64decode(payload_segment).decode('utf-8')))
        if not isinstance(payload, dict):
            raise V3CursorError('malformed_cursor')
        payload_data = cast(dict[str, Any], payload)
        keyset_payload = payload_data['keyset']
        if not isinstance(keyset_payload, dict):
            raise V3CursorError('malformed_cursor')
        keyset_data = cast(dict[str, Any], keyset_payload)
        claims = V3CursorClaims(
            uid=payload_data['uid'],
            account_generation=payload_data['account_generation'],
            projection_generation=payload_data['projection_generation'],
            filter_hash=payload_data['filter_hash'],
            source=payload_data['source'],
            read_mode=payload_data['read_mode'],
            keyset=V3Keyset(
                created_at_ms=keyset_data['created_at_ms'],
                memory_id=keyset_data['memory_id'],
            ),
            expires_at_epoch_seconds=payload_data['expires_at_epoch_seconds'],
            keyset_order=tuple(payload_data['keyset_order']),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise V3CursorError('malformed_cursor')

    if payload_data.get('schema_version') != _CURSOR_SCHEMA_VERSION or claims.keyset_order != _KEYSET_ORDER:
        raise V3CursorError('malformed_cursor')
    if context.now_epoch_seconds > claims.expires_at_epoch_seconds:
        raise V3CursorError('cursor_expired')
    if claims.uid != context.uid:
        raise V3CursorError('uid_mismatch')
    if claims.account_generation != context.account_generation:
        raise V3CursorError('account_generation_mismatch')
    if claims.projection_generation != context.projection_generation:
        raise V3CursorError('projection_generation_mismatch')
    if claims.filter_hash != context.filter_hash:
        raise V3CursorError('filter_hash_mismatch')
    if claims.source != context.source:
        raise V3CursorError('source_mismatch')
    if claims.read_mode != context.read_mode:
        raise V3CursorError('read_mode_mismatch')
    return claims


def validate_v3_cursor_request(*, limit: int, cursor: str | None, offset: int | None) -> V3CursorPageRequest:
    """Validate memory cursor-mode request semantics without legacy offset behavior."""

    if offset is not None:
        raise V3CursorError('offset_not_allowed_in_v3_cursor_mode')
    if limit == _LEGACY_FIRST_PAGE_OVERRIDE_LIMIT:
        raise V3CursorError('legacy_first_page_5000_not_allowed_in_v3_cursor_mode')
    if limit < 1 or limit > _DEFAULT_MAX_LIMIT:
        raise V3CursorError('limit_out_of_range')
    return V3CursorPageRequest(limit=limit, cursor=cursor)


# Neutral symbol aliases (memory names remain valid via shim)
V3CursorError = V3CursorError
V3Keyset = V3Keyset
V3CursorContext = V3CursorContext
V3CursorClaims = V3CursorClaims
V3CursorPageRequest = V3CursorPageRequest
