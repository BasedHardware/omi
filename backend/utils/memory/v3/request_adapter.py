"""Canonical module for ``utils.memory.v3.request_adapter`` (WS-G8b).

This module adapts HTTP parameters for the V3 read path.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, cast

from utils.memory.v3.cursor import validate_v3_cursor_request
from utils.memory.v3.memory_read_service import V3_READ_MODE, V3_READ_SOURCE

LEGACY_V3_READ_SOURCE = 'legacy_users_uid_memories'
LEGACY_V3_READ_MODE = 'legacy_primary'
LEGACY_FIRST_PAGE_LIMIT_OVERRIDE = 5000
V3_DEFAULT_LIMIT = 100
V3_MAX_LIMIT = 500
LEGACY_V3_MAX_LIMIT = 5000
_SUPPORTED_FILTER_KEYS = {'category', 'visibility', 'reviewed'}
_SUPPORTED_QUERY_KEYS = {'limit', 'offset', 'cursor', 'include_archive'} | _SUPPORTED_FILTER_KEYS
_ALLOWED_VISIBILITY_FILTERS = {'visible'}
_TRUE_VALUES = {'true', '1', 'yes'}
_FALSE_VALUES = {'false', '0', 'no'}


class V3RequestAdapterError(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class V3AdaptedRequest:
    valid: bool
    limit: int
    offset: int | None
    cursor: str | None
    read_mode: str
    source: str
    legacy_primary: bool
    v3_cursor_mode: bool
    filter_hash: str
    filters: dict[str, Any] = field(default_factory=dict[str, Any])
    cursor_binding: dict[str, str] = field(default_factory=dict[str, str])
    category: str | None = None
    include_archive: bool = False
    archive_authorized: bool = False
    archive_default_available: bool = False
    applies_first_page_5000_override: bool = False
    fail_closed_reason: str | None = None
    should_fetch_legacy: bool = False
    should_fetch_memory_projection: bool = False
    stale_short_term_default_visible: bool = False


@dataclass(frozen=True)
class _Invalid:
    reason: str
    limit: int = V3_DEFAULT_LIMIT
    offset: int | None = None
    cursor: str | None = None
    include_archive: bool = False


def _first_value(value: object) -> object | None:
    if isinstance(value, list):
        values = cast(list[object], value)
        return values[0] if values else None
    if isinstance(value, tuple):
        values = cast(tuple[object, ...], value)
        return values[0] if values else None
    return value


def _parse_int(value: object, *, default: int, reason: str) -> int:
    value = _first_value(value)
    if value is None or value == '':
        return default
    if isinstance(value, bool):
        raise V3RequestAdapterError(reason)
    if not isinstance(value, (str, int, float, bytes, bytearray)):
        raise V3RequestAdapterError(reason)
    try:
        return int(value)
    except (TypeError, ValueError):
        raise V3RequestAdapterError(reason)


def _parse_bool(value: object, *, default: bool, reason: str) -> bool:
    value = _first_value(value)
    if value is None or value == '':
        return default
    normalized = str(value).strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise V3RequestAdapterError(reason)


def _normalize_cursor(value: object) -> str | None:
    value = _first_value(value)
    if value is None:
        return None
    cursor = str(value).strip()
    if not cursor:
        raise V3RequestAdapterError('malformed_cursor_parameter')
    return cursor


def _normalize_filters(query_params: Mapping[str, Any]) -> tuple[dict[str, Any], str | None]:
    unsupported = sorted(set(query_params) - _SUPPORTED_QUERY_KEYS)
    if unsupported:
        raise V3RequestAdapterError('unsupported_filter')

    filters: dict[str, Any] = {}
    category = _first_value(query_params.get('category'))
    if category is not None and str(category).strip():
        filters['category'] = str(category).strip().lower()

    visibility = _first_value(query_params.get('visibility'))
    if visibility is not None and str(visibility).strip():
        normalized_visibility = str(visibility).strip().lower()
        if normalized_visibility not in _ALLOWED_VISIBILITY_FILTERS:
            raise V3RequestAdapterError('unsupported_filter_value')
        filters['visibility'] = normalized_visibility

    reviewed = _first_value(query_params.get('reviewed'))
    if reviewed is not None and str(reviewed).strip():
        filters['reviewed'] = _parse_bool(reviewed, default=False, reason='unsupported_filter_value')

    return filters, filters.get('category')


def _filter_hash(filters: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(sorted(filters.items())), sort_keys=True, separators=(',', ':'))
    return 'v3fh_' + hashlib.sha256(payload.encode('utf-8')).hexdigest()[:32]


def _invalid_result(invalid: _Invalid, *, enrolled: bool, raise_on_invalid: bool) -> V3AdaptedRequest:
    if raise_on_invalid:
        raise V3RequestAdapterError(invalid.reason)
    source = V3_READ_SOURCE if enrolled else LEGACY_V3_READ_SOURCE
    read_mode = V3_READ_MODE if enrolled else LEGACY_V3_READ_MODE
    return V3AdaptedRequest(
        valid=False,
        limit=invalid.limit,
        offset=invalid.offset,
        cursor=invalid.cursor,
        read_mode=read_mode,
        source=source,
        legacy_primary=False,
        v3_cursor_mode=enrolled,
        filter_hash=_filter_hash({}),
        fail_closed_reason=invalid.reason,
        include_archive=invalid.include_archive,
    )


def adapt_v3_request_parameters(
    query_params: Mapping[str, Any] | None,
    *,
    enrolled: bool,
    raise_on_invalid: bool = False,
) -> V3AdaptedRequest:
    """Normalize `/v3` query parameters into a pure read-service request contract.

    Non-enrolled callers retain legacy-primary limit/offset semantics, including
    the historical first-page `limit=5000` override marker. Enrolled memory callers
    use the bounded cursor-mode contract and fail closed for offsets, unsupported
    filters, explicit Archive requests, and invalid bounds.
    """

    params = dict(query_params or {})
    limit = V3_DEFAULT_LIMIT
    offset: int | None = None
    cursor: str | None = None
    include_archive = False
    try:
        limit = _parse_int(params.get('limit'), default=V3_DEFAULT_LIMIT, reason='invalid_limit')
        offset_present = 'offset' in params
        offset = _parse_int(params.get('offset'), default=0, reason='invalid_offset') if offset_present else None
        cursor = _normalize_cursor(params.get('cursor'))
        include_archive = _parse_bool(params.get('include_archive'), default=False, reason='invalid_include_archive')
        filters, category = _normalize_filters(params)

        if offset is not None and offset < 0:
            raise V3RequestAdapterError('invalid_offset')

        if include_archive:
            raise V3RequestAdapterError('archive_not_launched_on_v3_default')

        if not enrolled:
            if limit < 1 or limit > LEGACY_V3_MAX_LIMIT:
                raise V3RequestAdapterError('limit_out_of_range')
            legacy_offset = 0 if offset is None else offset
            if legacy_offset < 0:
                raise V3RequestAdapterError('invalid_offset')
            applies_override = legacy_offset == 0 and cursor is None
            effective_limit = LEGACY_FIRST_PAGE_LIMIT_OVERRIDE if applies_override else limit
            filters_hash = _filter_hash(filters)
            return V3AdaptedRequest(
                valid=True,
                limit=effective_limit,
                offset=legacy_offset,
                cursor=cursor,
                read_mode=LEGACY_V3_READ_MODE,
                source=LEGACY_V3_READ_SOURCE,
                legacy_primary=True,
                v3_cursor_mode=False,
                filter_hash=filters_hash,
                filters=filters,
                cursor_binding={
                    'filter_hash': filters_hash,
                    'source': LEGACY_V3_READ_SOURCE,
                    'read_mode': LEGACY_V3_READ_MODE,
                },
                category=category,
                applies_first_page_5000_override=applies_override,
                should_fetch_legacy=True,
            )

        validate_v3_cursor_request(limit=limit, cursor=cursor, offset=offset)
        filters_hash = _filter_hash(filters)
        return V3AdaptedRequest(
            valid=True,
            limit=limit,
            offset=None,
            cursor=cursor,
            read_mode=V3_READ_MODE,
            source=V3_READ_SOURCE,
            legacy_primary=False,
            v3_cursor_mode=True,
            filter_hash=filters_hash,
            filters=filters,
            cursor_binding={
                'filter_hash': filters_hash,
                'source': V3_READ_SOURCE,
                'read_mode': V3_READ_MODE,
            },
            category=category,
            should_fetch_memory_projection=True,
        )
    except V3RequestAdapterError as exc:
        return _invalid_result(
            _Invalid(
                reason=exc.reason,
                limit=limit,
                offset=offset,
                cursor=cursor,
                include_archive=include_archive,
            ),
            enrolled=enrolled,
            raise_on_invalid=raise_on_invalid,
        )
    except Exception as exc:
        reason = getattr(exc, 'reason', 'invalid_request_parameters')
        return _invalid_result(
            _Invalid(
                reason=reason,
                limit=limit,
                offset=offset,
                cursor=cursor,
                include_archive=include_archive,
            ),
            enrolled=enrolled,
            raise_on_invalid=raise_on_invalid,
        )
