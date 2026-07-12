"""Canonical module for ``utils.memory.v3.production_runtime`` (WS-G8b).

This module wires the V3 memory-read production runtime.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Mapping, Protocol, TypeAlias, cast

from config.memory_rollout import (
    MemoryRolloutMode,
    MemoryRolloutConfig,
    parse_enabled_users,
    rollout_enabled_users_env_raw,
    rollout_mode_env_value,
    rollout_v3_get_enabled_env_value,
)
from database import memory_compatibility_projection as projection_db
from utils.memory.v3.account_generation_source import read_memory_v3_trusted_account_generation
from utils.memory.v3.account_generation_source import V3TrustedAccountGenerationResult
from utils.memory.v3.composed_get_service import (
    V3ComposedAdapters,
    V3ComposedCursor,
    V3ComposedDependencyDecision,
    V3ComposedExecutionContext,
    V3ComposedProjectionPage,
    V3ComposedRequest,
    V3ComposedRequestParams,
    V3ComposedResponse,
    V3ComposedRow,
    V3ComposedSnapshotDecision,
    compose_v3_get,
)
from utils.memory.v3.control_reader_contract import (
    V3ControlReaderRequest,
    V3ControlRouteFamily,
    decide_v3_control_route,
)
from utils.memory.v3.control_state_adapter import read_v3_control
from utils.memory.v3.control_reader_contract import V3ControlReadResult
from utils.memory.v3.cursor import (
    V3CursorContext,
    V3CursorError,
    V3Keyset,
    create_v3_cursor,
    parse_v3_cursor,
)
from utils.memory.v3.projection_reader_contract import V3ProjectionCursor, V3ProjectionPage, V3ProjectionReadRequest

V3GetSourceDecision: TypeAlias = Literal['disabled', 'legacy_primary', 'memory_read']
MemoryDbItem: TypeAlias = dict[str, Any]
EnvMapping: TypeAlias = Mapping[str, str]
_DEFAULT_LIMIT = 100
_DEFAULT_CURSOR_TTL_SECONDS = 600
_DEFAULT_CURSOR_POLICY_VERSION = 'v3-cursor-policy-1'
_DEFAULT_CURSOR_SECRET_VERSION = 'unconfigured'
_DEFAULT_READ_MODE = 'default_memory'
_MEMORY_SOURCE = 'memory_compatibility_projection'


class ProjectionReader(Protocol):
    def __call__(self, *, db_client: object, request: V3ProjectionReadRequest) -> V3ProjectionPage: ...


_projection_reader = cast(ProjectionReader, getattr(projection_db, 'read_v3_compatibility_projection_page'))


@dataclass(frozen=True)
class V3GetRuntime:
    enabled: bool = False
    source_decision: V3GetSourceDecision = 'disabled'
    service: object = None
    adapters: object = None
    source_selector: object = None
    control_reader: object = None
    legacy_reader: object = None
    projection_reader: object = None
    cursor_keyring: object = None
    cursor_codec: object = None
    clock: object = None
    deadline: object = None
    observer: object = None


@dataclass(frozen=True)
class _RuntimeConfig:
    uid: str
    db_client: object
    rollout_config: MemoryRolloutConfig
    cursor_secret: bytes | None
    cursor_policy_version: str
    cursor_secret_version: str
    cursor_ttl_seconds: int


class _ProductionV3Adapters:
    def __init__(self, config: _RuntimeConfig):
        self.config = config
        self._last_control: V3ControlReadResult | None = None
        self._last_route_decision: object | None = None
        self._last_trusted_generation: V3TrustedAccountGenerationResult | None = None
        self._projection_source_commit: str | None = None
        self._projection_source_version: str | None = None

    def normalize_request(self, params: V3ComposedRequestParams) -> V3ComposedRequest:
        return V3ComposedRequest(
            limit=params.limit or _DEFAULT_LIMIT,
            offset=params.offset,
            cursor=params.cursor,
            include_archive=params.include_archive,
            include_historical=params.include_historical,
        )

    def decide_dependency(self, request: V3ComposedRequest, budget_ms: int) -> V3ComposedDependencyDecision:
        control = read_v3_control(
            uid=self.config.uid,
            db_client=self.config.db_client,
            rollout_config=self.config.rollout_config,
        )
        if not control.cohort_enrolled:
            self._last_control = control
            self._last_trusted_generation = None
            return V3ComposedDependencyDecision.legacy(self.config.uid)
        trusted_generation = read_memory_v3_trusted_account_generation(
            uid=self.config.uid, db_client=self.config.db_client
        )
        expected_generation = trusted_generation.account_generation
        route_decision = decide_v3_control_route(
            V3ControlReaderRequest(
                uid=self.config.uid,
                expected_account_generation=expected_generation,
                cursor_memory_read_requested=bool(request.cursor),
                cursor_secret_config_present=self.config.cursor_secret is not None,
                archive_requested=request.include_archive,
            ),
            control,
        )
        self._last_control = control
        self._last_route_decision = route_decision
        self._last_trusted_generation = trusted_generation
        if route_decision.route_family == V3ControlRouteFamily.LEGACY_PRIMARY:
            return V3ComposedDependencyDecision.legacy(self.config.uid)
        if route_decision.route_family != V3ControlRouteFamily.MEMORY_PROJECTION or not route_decision.allowed:
            return V3ComposedDependencyDecision.fail(route_decision.reason.value, route_decision.http_status)
        return V3ComposedDependencyDecision.enrolled_ready(self.config.uid)

    def build_snapshot(
        self, subject_uid: str, request: V3ComposedRequest, budget_ms: int
    ) -> V3ComposedSnapshotDecision:
        if subject_uid != self.config.uid:
            return V3ComposedSnapshotDecision.fail('infrastructure_failure', 503)
        if self._last_control is None or self._last_control.state is None or self._last_trusted_generation is None:
            return V3ComposedSnapshotDecision.fail('infrastructure_failure', 503)
        control_state = self._last_control.state
        projection_state_data = _read_doc_dict(
            self.config.db_client, f'users/{subject_uid}/v3_compatibility_projection/state'
        )
        if not isinstance(projection_state_data, dict):
            return V3ComposedSnapshotDecision.fail('infrastructure_failure', 503)
        try:
            account_generation = _required_int(projection_state_data.get('account_generation'))
            projection_generation = _required_int(projection_state_data.get('projection_generation'))
            projection_commit = _required_str(projection_state_data.get('projection_commit_id'))
            source_commit = _required_str(projection_state_data.get('source_commit_id'))
            source_version = _required_str(projection_state_data.get('source_version'))
        except (TypeError, ValueError):
            return V3ComposedSnapshotDecision.fail('infrastructure_failure', 503)
        if account_generation != self._last_trusted_generation.account_generation:
            return V3ComposedSnapshotDecision.fail('infrastructure_failure', 503)
        now_ms = self.now_ms()
        context = V3ComposedExecutionContext(
            subject_uid=subject_uid,
            grant_epoch=f'mode-{control_state.mode_epoch}',
            config_epoch=f'schema-{control_state.schema_version}',
            account_generation=account_generation,
            projection_generation=projection_generation,
            projection_commit=projection_commit,
            cursor_policy_version=self.config.cursor_policy_version,
            cursor_secret_version=self.config.cursor_secret_version,
            read_timestamp_ms=now_ms,
            deadline_ms=now_ms + max(budget_ms, 1),
            filter_hash=_filter_hash(request),
            archive_requested=request.include_archive,
            source=_MEMORY_SOURCE,
            read_mode=_DEFAULT_READ_MODE,
        )
        self._projection_source_commit = source_commit
        self._projection_source_version = source_version
        return V3ComposedSnapshotDecision.ready(context)

    def decode_cursor(
        self, token: str | None, context: V3ComposedExecutionContext, budget_ms: int
    ) -> V3ComposedCursor | None:
        if token is None:
            return None
        if self.config.cursor_secret is None:
            raise V3CursorError('missing_cursor_secret')
        claims = parse_v3_cursor(token, _cursor_context(context, self.now_ms()), self.config.cursor_secret)
        return V3ComposedCursor(created_at_ms=claims.keyset.created_at_ms, memory_id=claims.keyset.memory_id)

    def read_projection(
        self,
        request: V3ComposedRequest,
        context: V3ComposedExecutionContext,
        after: V3ComposedCursor | None,
        limit: int,
        budget_ms: int,
    ) -> V3ComposedProjectionPage:
        projection_page = _projection_reader(
            db_client=self.config.db_client,
            request=V3ProjectionReadRequest(
                uid=context.subject_uid,
                limit=limit,
                expected_account_generation=context.account_generation,
                cursor=_projection_cursor(after, context),
                offset=request.offset,
                include_archive=request.include_archive,
            ),
        )
        rows = tuple(_projection_item_to_row(item, context, projection_page) for item in projection_page.items)
        return V3ComposedProjectionPage(
            rows=rows,
            next_cursor=_composed_cursor(projection_page.next_cursor),
            subject_uid=context.subject_uid,
            grant_epoch=context.grant_epoch,
            config_epoch=context.config_epoch,
            account_generation=projection_page.account_generation,
            projection_generation=projection_page.projection_generation,
            projection_commit=projection_page.projection_commit_id,
            cursor_policy_version=context.cursor_policy_version,
            cursor_secret_version=context.cursor_secret_version,
            read_timestamp_ms=context.read_timestamp_ms,
            scanned_count=len(rows),
            partial=False,
            estimated_response_bytes=sum(row.estimated_response_bytes for row in rows),
        )

    def encode_cursor(self, cursor: V3ComposedCursor, context: V3ComposedExecutionContext, budget_ms: int) -> str:
        if self.config.cursor_secret is None:
            raise V3CursorError('missing_cursor_secret')
        return create_v3_cursor(
            V3Keyset(created_at_ms=cursor.created_at_ms, memory_id=cursor.memory_id),
            _cursor_context(context, self.now_ms()),
            self.config.cursor_secret,
            ttl_seconds=self.config.cursor_ttl_seconds,
        )

    def read_legacy(self, request: V3ComposedRequest, budget_ms: int) -> V3ComposedResponse:
        return V3ComposedResponse.error(503, 'infrastructure_failure')

    def now_ms(self) -> int:
        return int(datetime.now(tz=timezone.utc).timestamp() * 1000)

    def as_composed_adapters(self) -> V3ComposedAdapters:
        return V3ComposedAdapters(
            normalize_request=self.normalize_request,
            decide_dependency=self.decide_dependency,
            build_snapshot=self.build_snapshot,
            decode_cursor=self.decode_cursor,
            read_projection=self.read_projection,
            encode_cursor=self.encode_cursor,
            read_legacy=self.read_legacy,
            now_ms=self.now_ms,
        )


def _read_doc_dict(db_client: Any, path: str) -> MemoryDbItem | None:
    snapshot: Any = db_client.document(path).get()
    if getattr(snapshot, 'exists', False) is False:
        return None
    data: object = snapshot.to_dict()
    return cast(MemoryDbItem, data) if isinstance(data, dict) else None


def _required_str(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError('missing_string')
    return value


def _required_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError('missing_int')
    return int(value)


def _filter_hash(request: V3ComposedRequest) -> str:
    archive = 'archive' if request.include_archive else 'noarchive'
    historical = 'historical' if request.include_historical else 'nohistorical'
    return f'default:{archive}:{historical}'


def _cursor_context(context: V3ComposedExecutionContext, now_ms: int) -> V3CursorContext:
    return V3CursorContext(
        uid=context.subject_uid,
        account_generation=context.account_generation,
        projection_generation=context.projection_generation,
        filter_hash=context.filter_hash,
        source=context.source,
        read_mode=context.read_mode,
        now_epoch_seconds=int(now_ms / 1000),
    )


def _projection_cursor(
    cursor: V3ComposedCursor | None, context: V3ComposedExecutionContext
) -> V3ProjectionCursor | None:
    if cursor is None:
        return None
    return V3ProjectionCursor(
        created_at=datetime.fromtimestamp(cursor.created_at_ms / 1000, tz=timezone.utc),
        memory_id=cursor.memory_id,
        account_generation=context.account_generation,
        projection_generation=context.projection_generation,
        projection_commit_id=context.projection_commit,
    )


def _composed_cursor(cursor: V3ProjectionCursor | None) -> V3ComposedCursor | None:
    if cursor is None:
        return None
    return V3ComposedCursor(created_at_ms=int(cursor.created_at.timestamp() * 1000), memory_id=cursor.memory_id)


def _projection_item_to_row(
    item: MemoryDbItem, context: V3ComposedExecutionContext, projection_page: V3ProjectionPage
) -> V3ComposedRow:
    created_at = item.get('created_at')
    if not isinstance(created_at, datetime):
        created_at = item.get('updated_at')
    created_at_ms = (
        int(created_at.timestamp() * 1000) if isinstance(created_at, datetime) else context.read_timestamp_ms
    )
    memory_id = str(item.get('id'))
    estimated_bytes = len(str(item).encode('utf-8'))
    return V3ComposedRow(
        memory_id=memory_id,
        created_at_ms=created_at_ms,
        subject_uid=context.subject_uid,
        account_generation=projection_page.account_generation,
        projection_generation=projection_page.projection_generation,
        projection_commit=projection_page.projection_commit_id,
        item_revision=1,
        source_version=projection_page.source_version,
        source_commit=projection_page.source_commit_id,
        deleted=False,
        tombstoned=False,
        visibility='long_term',
        lifecycle_status='active',
        source_freshness='stable',
        source_backed_projection=True,
        memorydb_item=item,
        estimated_response_bytes=estimated_bytes,
    )


def _cursor_secret_from_env(env: EnvMapping) -> bytes | None:
    raw = env.get('MEMORY_V3_CURSOR_SECRET') or ''
    return raw.encode('utf-8') if raw else None


def _cursor_ttl_from_env(env: EnvMapping) -> int:
    raw = env.get('MEMORY_V3_CURSOR_TTL_SECONDS') or ''
    if not raw:
        return _DEFAULT_CURSOR_TTL_SECONDS
    try:
        return max(1, int(raw))
    except ValueError:
        return _DEFAULT_CURSOR_TTL_SECONDS


def _v3_get_route_enabled(env: EnvMapping) -> bool:
    return rollout_v3_get_enabled_env_value(env)


def _runtime_enabled(rollout_config: MemoryRolloutConfig) -> bool:
    return rollout_config.mode == MemoryRolloutMode.read and bool(rollout_config.enabled_users)


def _rollout_config_from_env(env: EnvMapping) -> MemoryRolloutConfig:
    try:
        mode = MemoryRolloutMode(rollout_mode_env_value(env))
    except (TypeError, ValueError):
        return MemoryRolloutConfig()
    return MemoryRolloutConfig(
        enabled_users=parse_enabled_users(rollout_enabled_users_env_raw(env)),
        mode=mode,
    )


def _source_decision_for_uid(
    *, uid: str, db_client: object, rollout_config: MemoryRolloutConfig
) -> V3GetSourceDecision:
    if not _runtime_enabled(rollout_config):
        return 'disabled'
    control = read_v3_control(uid=uid, db_client=db_client, rollout_config=rollout_config)
    if not control.cohort_enrolled:
        return 'legacy_primary'
    if control.state is not None and control.state.effective_mode != MemoryRolloutMode.read:
        return 'legacy_primary'
    return 'memory_read'


def build_v3_production_runtime(*, uid: str, db_client: object, env: EnvMapping | None = None) -> V3GetRuntime:
    effective_env = env if env is not None else os.environ
    if not _v3_get_route_enabled(effective_env):
        return V3GetRuntime(enabled=False, source_decision='disabled')
    rollout_config = _rollout_config_from_env(effective_env)
    if not _runtime_enabled(rollout_config):
        return V3GetRuntime(enabled=False, source_decision='disabled')

    source_decision = _source_decision_for_uid(uid=uid, db_client=db_client, rollout_config=rollout_config)
    if source_decision == 'legacy_primary':
        return V3GetRuntime(enabled=True, source_decision='legacy_primary')

    config = _RuntimeConfig(
        uid=uid,
        db_client=db_client,
        rollout_config=rollout_config,
        cursor_secret=_cursor_secret_from_env(effective_env),
        cursor_policy_version=effective_env.get('MEMORY_V3_CURSOR_POLICY_VERSION') or _DEFAULT_CURSOR_POLICY_VERSION,
        cursor_secret_version=effective_env.get('MEMORY_V3_CURSOR_SECRET_VERSION') or _DEFAULT_CURSOR_SECRET_VERSION,
        cursor_ttl_seconds=_cursor_ttl_from_env(effective_env),
    )
    adapters = _ProductionV3Adapters(config)
    return V3GetRuntime(
        enabled=True,
        source_decision='memory_read',
        service=compose_v3_get,
        adapters=adapters.as_composed_adapters(),
        source_selector='server_side_rollout_config_and_control_state',
        control_reader=read_v3_control,
        projection_reader=_projection_reader,
        cursor_codec='v3_hmac_cursor',
        clock=adapters.now_ms,
    )
