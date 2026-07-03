"""Canonical module for ``utils.memory.v3_composed_get_service`` (WS-G8b).

Neutral ``v3_composed_get_service`` is the source of truth. Legacy ``v3_composed_get_service`` remains an importable alias.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, cast

from utils.memory.v3_archive_visibility_readiness import decide_default_visibility

DependencyStatus = Literal['enrolled_ready', 'legacy', 'fail']
SnapshotStatus = Literal['ready', 'fail']

_DEFAULT_LIMIT = 100
_MAX_LIMIT = 500
_DEFAULT_DEADLINE_MS = 1_000
_MIN_STAGE_BUDGET_MS = 1
_DEFAULT_SCAN_BUDGET = 1_000
_DEFAULT_MAX_PROJECTION_READS = 5
_DEFAULT_RESPONSE_BYTE_CAP = 1_000_000

_PUBLIC_ERROR_BY_REASON = {
    'bad_request': 'request_invalid',
    'cursor_invalid': 'cursor_invalid',
    'offset_invalid': 'offset_invalid',
    'grant_denied': 'grant_denied',
    'infrastructure_failure': 'infrastructure_failure',
    'adapter_contract': 'infrastructure_failure',
    'adapter_exception': 'infrastructure_failure',
    'projection_attestation_mismatch': 'generation_invalidated',
    'row_fence_mismatch': 'generation_invalidated',
    'deadline_exhausted': 'deadline_exhausted',
    'partial_projection': 'infrastructure_failure',
    'response_too_large': 'response_too_large',
}


def _public_error(reason: str) -> str:
    return _PUBLIC_ERROR_BY_REASON.get(reason, 'infrastructure_failure')


MemoryDbItem = dict[str, Any]


def _empty_headers() -> dict[str, str]:
    return {}


@dataclass(frozen=True)
class V3ComposedRequestParams:
    limit: int | None = None
    offset: int | None = None
    cursor: str | None = None
    include_archive: bool = False
    include_historical: bool = False
    scan_budget: int = _DEFAULT_SCAN_BUDGET
    max_projection_reads: int = _DEFAULT_MAX_PROJECTION_READS
    response_byte_cap: int = _DEFAULT_RESPONSE_BYTE_CAP
    deadline_ms: int | None = None


@dataclass(frozen=True)
class V3ComposedRequest:
    limit: int
    offset: int | None = None
    cursor: str | None = None
    include_archive: bool = False
    include_historical: bool = False


@dataclass(frozen=True)
class V3ComposedCursor:
    created_at_ms: int
    memory_id: str


@dataclass(frozen=True)
class V3ComposedGrant:
    revoked: bool
    epoch: str


@dataclass(frozen=True)
class V3ComposedExecutionContext:
    subject_uid: str
    grant_epoch: str
    config_epoch: str
    account_generation: int
    projection_generation: int
    projection_commit: str
    cursor_policy_version: str
    cursor_secret_version: str
    read_timestamp_ms: int
    deadline_ms: int
    filter_hash: str
    archive_requested: bool
    source: str
    read_mode: str


@dataclass(frozen=True)
class V3ComposedDependencyDecision:
    status: DependencyStatus
    subject_uid: str | None = None
    reason: str = 'ok'
    http_status: int = 200
    should_read_legacy: bool = False
    should_read_projection: bool = False

    @staticmethod
    def enrolled_ready(subject_uid: str) -> 'V3ComposedDependencyDecision':
        return V3ComposedDependencyDecision(
            status='enrolled_ready', subject_uid=subject_uid, should_read_projection=True
        )

    @staticmethod
    def legacy(subject_uid: str) -> 'V3ComposedDependencyDecision':
        return V3ComposedDependencyDecision(status='legacy', subject_uid=subject_uid, should_read_legacy=True)

    @staticmethod
    def fail(reason: str, http_status: int) -> 'V3ComposedDependencyDecision':
        return V3ComposedDependencyDecision(status='fail', reason=reason, http_status=http_status)


@dataclass(frozen=True)
class V3ComposedSnapshotDecision:
    status: SnapshotStatus
    context: V3ComposedExecutionContext | None = None
    reason: str = 'ok'
    http_status: int = 200
    grant: V3ComposedGrant | None = None

    @staticmethod
    def ready(context: V3ComposedExecutionContext) -> 'V3ComposedSnapshotDecision':
        return V3ComposedSnapshotDecision(status='ready', context=context)

    @staticmethod
    def fail(reason: str, http_status: int, *, grant: object = None) -> 'V3ComposedSnapshotDecision':
        typed_grant = grant if isinstance(grant, V3ComposedGrant) else None
        return V3ComposedSnapshotDecision(status='fail', reason=reason, http_status=http_status, grant=typed_grant)


@dataclass(frozen=True)
class V3ComposedRow:
    memory_id: str
    created_at_ms: int
    subject_uid: str
    account_generation: int
    projection_generation: int
    projection_commit: str
    item_revision: int
    source_version: str
    source_commit: str
    deleted: bool
    tombstoned: bool
    visibility: str
    lifecycle_status: str
    source_freshness: str
    source_backed_projection: bool
    memorydb_item: MemoryDbItem
    estimated_response_bytes: int = 0


@dataclass(frozen=True)
class V3ComposedProjectionPage:
    rows: tuple[V3ComposedRow, ...]
    next_cursor: V3ComposedCursor | None
    subject_uid: str
    grant_epoch: str
    config_epoch: str
    account_generation: int
    projection_generation: int
    projection_commit: str
    cursor_policy_version: str
    cursor_secret_version: str
    read_timestamp_ms: int
    scanned_count: int
    partial: bool = False
    estimated_response_bytes: int = 0


@dataclass(frozen=True)
class V3ComposedResponse:
    http_status: int
    body: list[MemoryDbItem] | None
    public_error: str | None = None
    next_cursor: str | None = None
    source: str = 'memory_compatibility_projection'
    decision: str = 'ok'
    read_count: int = 0
    scanned_count: int = 0
    verified_empty: bool = False
    headers: dict[str, str] = field(default_factory=_empty_headers)

    @staticmethod
    def success(
        *,
        body: list[MemoryDbItem],
        next_cursor: str | None,
        source: str,
        read_count: int = 0,
        scanned_count: int = 0,
        verified_empty: bool = False,
    ) -> 'V3ComposedResponse':
        headers: dict[str, str] = {'X-Omi-Memory-Read-Source': source, 'X-Omi-Memory-Read-Decision': 'ok'}
        if next_cursor:
            headers['X-Omi-Memory-Next-Cursor'] = next_cursor
            headers['Link'] = f'<{next_cursor}>; rel="next"'
        return V3ComposedResponse(
            http_status=200,
            body=body,
            next_cursor=next_cursor,
            source=source,
            read_count=read_count,
            scanned_count=scanned_count,
            verified_empty=verified_empty,
            headers=headers,
        )

    @staticmethod
    def error(http_status: int, reason: str) -> 'V3ComposedResponse':
        return V3ComposedResponse(
            http_status=http_status,
            body=None,
            public_error=_public_error(reason),
            decision=reason,
            source='none',
            headers={'X-Omi-Memory-Read-Source': 'none', 'X-Omi-Memory-Read-Decision': _public_error(reason)},
        )


NormalizeRequest = Callable[[V3ComposedRequestParams], object]
DecideDependency = Callable[[V3ComposedRequest, int], V3ComposedDependencyDecision]
BuildSnapshot = Callable[[str, V3ComposedRequest, int], V3ComposedSnapshotDecision]
DecodeCursor = Callable[[str | None, V3ComposedExecutionContext, int], V3ComposedCursor | None]
ReadProjection = Callable[
    [V3ComposedRequest, V3ComposedExecutionContext, V3ComposedCursor | None, int, int],
    V3ComposedProjectionPage,
]
EncodeCursor = Callable[[V3ComposedCursor, V3ComposedExecutionContext, int], str]
ReadLegacy = Callable[[V3ComposedRequest, int], V3ComposedResponse]
NowMs = Callable[[], int]


@dataclass(frozen=True)
class V3ComposedAdapters:
    normalize_request: NormalizeRequest
    decide_dependency: DecideDependency
    build_snapshot: BuildSnapshot
    decode_cursor: DecodeCursor
    read_projection: ReadProjection
    encode_cursor: EncodeCursor
    read_legacy: ReadLegacy
    now_ms: NowMs


def _budget(params: V3ComposedRequestParams, adapters: V3ComposedAdapters) -> int:
    deadline = params.deadline_ms if params.deadline_ms is not None else adapters.now_ms() + _DEFAULT_DEADLINE_MS
    return max(0, deadline - adapters.now_ms())


def _ensure_budget(params: V3ComposedRequestParams, adapters: V3ComposedAdapters) -> int | V3ComposedResponse:
    remaining = _budget(params, adapters)
    if remaining < _MIN_STAGE_BUDGET_MS:
        return V3ComposedResponse.error(504, 'deadline_exhausted')
    return remaining


def _valid_dependency(decision: object) -> V3ComposedDependencyDecision | V3ComposedResponse:
    if not isinstance(decision, V3ComposedDependencyDecision):
        return V3ComposedResponse.error(503, 'adapter_contract')
    if decision.status not in {'enrolled_ready', 'legacy', 'fail'}:
        return V3ComposedResponse.error(503, 'adapter_contract')
    if decision.status == 'enrolled_ready':
        if not decision.subject_uid or not decision.should_read_projection or decision.should_read_legacy:
            return V3ComposedResponse.error(503, 'adapter_contract')
    if decision.status == 'legacy':
        if not decision.subject_uid or not decision.should_read_legacy or decision.should_read_projection:
            return V3ComposedResponse.error(503, 'adapter_contract')
    if decision.status == 'fail' and not (400 <= decision.http_status <= 599):
        return V3ComposedResponse.error(503, 'adapter_contract')
    return decision


def _valid_snapshot(snapshot: object) -> V3ComposedSnapshotDecision | V3ComposedResponse:
    if not isinstance(snapshot, V3ComposedSnapshotDecision):
        return V3ComposedResponse.error(503, 'adapter_contract')
    if snapshot.status not in {'ready', 'fail'}:
        return V3ComposedResponse.error(503, 'adapter_contract')
    if snapshot.status == 'ready' and not isinstance(snapshot.context, V3ComposedExecutionContext):
        return V3ComposedResponse.error(503, 'adapter_contract')
    return snapshot


def _page_matches_context(page: V3ComposedProjectionPage, context: V3ComposedExecutionContext) -> bool:
    return (
        page.subject_uid == context.subject_uid
        and page.grant_epoch == context.grant_epoch
        and page.config_epoch == context.config_epoch
        and page.account_generation == context.account_generation
        and page.projection_generation == context.projection_generation
        and page.projection_commit == context.projection_commit
        and page.cursor_policy_version == context.cursor_policy_version
        and page.cursor_secret_version == context.cursor_secret_version
        and page.read_timestamp_ms == context.read_timestamp_ms
    )


def _row_fence_valid(row: V3ComposedRow, context: V3ComposedExecutionContext) -> bool:
    return (
        row.subject_uid == context.subject_uid
        and row.account_generation == context.account_generation
        and row.projection_generation == context.projection_generation
        and row.projection_commit == context.projection_commit
        and row.item_revision > 0
        and bool(row.source_version)
        and bool(row.source_commit)
    )


def _row_visible(row: V3ComposedRow, request: V3ComposedRequest) -> bool:
    decision = decide_default_visibility(
        {
            'visibility': row.visibility,
            'lifecycle_status': row.lifecycle_status,
            'source_freshness': row.source_freshness,
            'source_backed_projection': row.source_backed_projection,
            'memory_layer': 'l1_archive' if row.visibility == 'archived_evidence' else 'durable',
        },
        include_archive=request.include_archive,
        include_historical=request.include_historical,
        server_archive_capability=request.include_archive,
        server_historical_capability=request.include_historical,
    )
    return bool(decision.get('default_visible') or decision.get('opt_in_visible'))


def _normalize_or_default(
    params: V3ComposedRequestParams, adapters: V3ComposedAdapters
) -> V3ComposedRequest | V3ComposedResponse:
    normalized = adapters.normalize_request(params)
    if not isinstance(normalized, V3ComposedRequest):
        return V3ComposedResponse.error(503, 'adapter_contract')
    raw_limit = cast(int | None, normalized.limit)
    if raw_limit is None:
        return V3ComposedRequest(
            limit=_DEFAULT_LIMIT,
            offset=normalized.offset,
            cursor=normalized.cursor,
            include_archive=normalized.include_archive,
            include_historical=normalized.include_historical,
        )
    return normalized


def compose_v3_get(
    params: V3ComposedRequestParams,
    adapters: V3ComposedAdapters,
) -> V3ComposedResponse:
    """Compose future GET stages with fail-closed typed adapter boundaries."""

    try:
        budget = _ensure_budget(params, adapters)
        if isinstance(budget, V3ComposedResponse):
            return budget
        raw_request = _normalize_or_default(params, adapters)
        if isinstance(raw_request, V3ComposedResponse):
            return raw_request
        if raw_request.limit < 1 or raw_request.limit > _MAX_LIMIT:
            return V3ComposedResponse.error(400, 'bad_request')
        request = raw_request

        budget = _ensure_budget(params, adapters)
        if isinstance(budget, V3ComposedResponse):
            return budget
        dependency_or_response = _valid_dependency(adapters.decide_dependency(request, budget))
        if isinstance(dependency_or_response, V3ComposedResponse):
            return dependency_or_response
        dependency = dependency_or_response

        if dependency.status == 'fail':
            return V3ComposedResponse.error(dependency.http_status, dependency.reason)
        if dependency.status == 'legacy':
            budget = _ensure_budget(params, adapters)
            if isinstance(budget, V3ComposedResponse):
                return budget
            legacy = adapters.read_legacy(request, budget)
            return legacy

        if request.offset not in (None, 0):
            return V3ComposedResponse.error(400, 'offset_invalid')
        if request.offset == 0:
            request = V3ComposedRequest(
                limit=request.limit,
                cursor=request.cursor,
                include_archive=request.include_archive,
                include_historical=request.include_historical,
            )

        budget = _ensure_budget(params, adapters)
        if isinstance(budget, V3ComposedResponse):
            return budget
        snapshot_or_response = _valid_snapshot(adapters.build_snapshot(dependency.subject_uid or '', request, budget))
        if isinstance(snapshot_or_response, V3ComposedResponse):
            return snapshot_or_response
        snapshot = snapshot_or_response
        if snapshot.status == 'fail':
            if snapshot.reason == 'grant_denied' or (snapshot.grant is not None and snapshot.grant.revoked):
                return V3ComposedResponse.error(403, 'grant_denied')
            return V3ComposedResponse.error(snapshot.http_status, snapshot.reason)
        context = snapshot.context
        assert context is not None

        budget = _ensure_budget(params, adapters)
        if isinstance(budget, V3ComposedResponse):
            return budget
        if request.cursor is not None:
            try:
                after = adapters.decode_cursor(request.cursor, context, budget)
            except Exception:
                return V3ComposedResponse.error(400, 'cursor_invalid')
        else:
            after = None

        body: list[MemoryDbItem] = []
        scans = 0
        read_count = 0
        last_scanned_cursor: V3ComposedCursor | None = after
        next_page_cursor: V3ComposedCursor | None = after
        response_bytes = 0
        verified_projection_empty = False

        while len(body) < request.limit and read_count < params.max_projection_reads and scans < params.scan_budget:
            budget = _ensure_budget(params, adapters)
            if isinstance(budget, V3ComposedResponse):
                return budget
            remaining_items = request.limit - len(body)
            read_limit = min(max(remaining_items, 1) + 10, params.scan_budget - scans, _MAX_LIMIT)
            try:
                page = adapters.read_projection(request, context, next_page_cursor, read_limit, budget)
            except Exception:
                return V3ComposedResponse.error(503, 'adapter_exception')
            read_count += 1
            if page.partial:
                return V3ComposedResponse.error(503, 'partial_projection')
            if not _page_matches_context(page, context):
                return V3ComposedResponse.error(409, 'projection_attestation_mismatch')
            scans += page.scanned_count
            if not page.rows and page.next_cursor is None:
                verified_projection_empty = read_count == 1 and len(body) == 0 and scans == 0
                last_scanned_cursor = None
                break
            for candidate in page.rows:
                if not _row_fence_valid(candidate, context):
                    return V3ComposedResponse.error(409, 'row_fence_mismatch')
                last_scanned_cursor = V3ComposedCursor(candidate.created_at_ms, candidate.memory_id)
                if candidate.deleted or candidate.tombstoned:
                    continue
                if _row_visible(candidate, request) and len(body) < request.limit:
                    response_bytes += candidate.estimated_response_bytes
                    if response_bytes > params.response_byte_cap:
                        return V3ComposedResponse.error(413, 'response_too_large')
                    body.append(candidate.memorydb_item)
            next_page_cursor = page.next_cursor
            if page.next_cursor is None:
                break

        next_cursor_token = None
        if next_page_cursor is not None and last_scanned_cursor is not None:
            budget = _ensure_budget(params, adapters)
            if isinstance(budget, V3ComposedResponse):
                return budget
            try:
                next_cursor_token = adapters.encode_cursor(last_scanned_cursor, context, budget)
            except Exception:
                return V3ComposedResponse.error(503, 'adapter_exception')
            if not next_cursor_token:
                return V3ComposedResponse.error(503, 'adapter_contract')

        return V3ComposedResponse.success(
            body=body,
            next_cursor=next_cursor_token,
            source='memory_compatibility_projection',
            read_count=read_count,
            scanned_count=scans,
            verified_empty=verified_projection_empty,
        )
    except Exception:
        return V3ComposedResponse.error(503, 'adapter_exception')
