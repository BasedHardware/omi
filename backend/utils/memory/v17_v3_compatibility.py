from dataclasses import dataclass, field
from enum import Enum
from typing import Any

SUPPORTED_ENROLLED_CONTROL_STATES = {'valid'}
ENROLLED_FAIL_CLOSED_CONTROL_STATES = {
    'missing',
    'malformed',
    'uid_mismatch',
    'unsupported_schema',
    'control_timeout',
}


class V17V3CompatibilityReadPath(str, Enum):
    LEGACY_PRIMARY = 'LEGACY_PRIMARY'
    V17_COMPATIBILITY_PROJECTION = 'V17_COMPATIBILITY_PROJECTION'
    FAIL_CLOSED = 'FAIL_CLOSED'
    DENY = 'DENY'


@dataclass(frozen=True)
class V17V3CompatibilityContext:
    uid: str
    enrolled: bool
    control_state: str = 'missing'
    default_memory_grant: bool | None = None
    write_convergence_ready: bool = False
    projection_ready: bool = False
    projection_empty: bool = False
    requested_archive: bool = False


@dataclass(frozen=True)
class V17V3CursorMode:
    enabled_mode: str = 'additive_v17_cursor'
    opaque: bool = True
    signed: bool = True
    keyset_fields: tuple[str, str] = ('created_at_desc', 'memory_id_desc')
    generation_bound: bool = True
    projection_bound: bool = True
    allows_offset: bool = False
    applies_first_page_5000_override: bool = False


@dataclass(frozen=True)
class V17V3CompatibilityDecision:
    read_path: V17V3CompatibilityReadPath
    http_status: int
    reason: str
    headers: dict[str, str]
    body_contract: str = 'List[MemoryDB]'
    metadata_location: str = 'headers'
    body_additions: tuple[str, ...] = ()
    legacy_primary_allowed: bool = False
    legacy_fallback_allowed: bool = False
    product_overridable: bool = False
    archive_available: bool = False
    response_body_override: list[Any] | None = None


def _headers(*, source: str, reason: str) -> dict[str, str]:
    return {'X-Omi-Memory-Read-Source': source, 'X-Omi-Memory-Read-Decision': reason}


def _fail_closed(reason: str) -> V17V3CompatibilityDecision:
    return V17V3CompatibilityDecision(
        read_path=V17V3CompatibilityReadPath.FAIL_CLOSED,
        http_status=503,
        reason=reason,
        headers=_headers(source='none', reason=reason),
    )


def decide_v17_v3_compatibility(context: V17V3CompatibilityContext) -> V17V3CompatibilityDecision:
    """Pure Oracle-prescribed `/v3` V17 compatibility decision seam.

    This function is intentionally local and side-effect free. It performs no
    Firestore, Pinecone, provider, network, routing, or mutation work. Runtime
    `/v3` route wiring remains blocked until a later slice supplies the backing
    read/projection/write convergence services and product approval.
    """

    if not context.enrolled:
        reason = 'non_enrolled_legacy_primary'
        return V17V3CompatibilityDecision(
            read_path=V17V3CompatibilityReadPath.LEGACY_PRIMARY,
            http_status=200,
            reason=reason,
            headers=_headers(source='legacy_primary', reason=reason),
            legacy_primary_allowed=True,
        )

    if context.control_state in ENROLLED_FAIL_CLOSED_CONTROL_STATES:
        return _fail_closed(f'enrolled_{context.control_state}_fail_closed')

    if context.control_state not in SUPPORTED_ENROLLED_CONTROL_STATES:
        return _fail_closed('enrolled_unsupported_schema_fail_closed')

    if context.default_memory_grant is not True:
        reason = 'no_default_memory_grant_privacy_consent_deny'
        return V17V3CompatibilityDecision(
            read_path=V17V3CompatibilityReadPath.DENY,
            http_status=403,
            reason=reason,
            headers=_headers(source='none', reason=reason),
            product_overridable=True,
        )

    if context.requested_archive:
        reason = 'archive_default_unavailable'
        return V17V3CompatibilityDecision(
            read_path=V17V3CompatibilityReadPath.DENY,
            http_status=404,
            reason=reason,
            headers=_headers(source='none', reason=reason),
            archive_available=False,
        )

    if not context.write_convergence_ready:
        return _fail_closed('write_convergence_not_ready')

    if not context.projection_ready:
        return _fail_closed('v17_projection_not_ready')

    if context.projection_empty:
        reason = 'v17_projection_empty_no_legacy_fallback'
        return V17V3CompatibilityDecision(
            read_path=V17V3CompatibilityReadPath.V17_COMPATIBILITY_PROJECTION,
            http_status=200,
            reason=reason,
            headers=_headers(source='v17_compatibility_projection', reason=reason),
            response_body_override=[],
        )

    reason = 'v17_compatibility_projection_primary'
    return V17V3CompatibilityDecision(
        read_path=V17V3CompatibilityReadPath.V17_COMPATIBILITY_PROJECTION,
        http_status=200,
        reason=reason,
        headers=_headers(source='v17_compatibility_projection', reason=reason),
    )


def describe_v17_cursor_mode() -> V17V3CursorMode:
    """Return the allowed V17 `/v3` cursor contract without parsing live cursors."""

    return V17V3CursorMode()
