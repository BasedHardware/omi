"""Canonical product authorization module (WS-G8a).

Neutral ``product_authorization`` is the source of truth. Canonical product authorization.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional, cast

from database import memory_app_key_grants as app_key_grants_db
from database.memory_app_key_grants import AppKeyMemoryGrantStateRead
from models.product_memory import MemoryAccessPolicy, MemoryConsumer
from utils.memory import default_read_rollout as default_read_rollout_mod
from utils.memory.default_read_rollout import (
    DefaultReadRolloutDecision,
    GlobalReadGateDecision,
    MemoryReadDecision,
    read_archive_read_rollout,
    read_default_read_rollout,
    read_global_read_gate,
)

ObservabilityPayload = Dict[str, Any]
GrantPayload = Dict[str, Any]
GrantStatePayload = Dict[str, Any]


@dataclass(frozen=True)
class ProductAuthorizationContext:
    """Server-side context for memory product memory route authorization.

    This is intentionally route-owned and fake-injectable. Request flags can
    express intent (for example, explicit Archive search), but authorization is
    derived from server-read rollout/control state and persisted capabilities.
    """

    uid: str
    consumer: str
    surface: str
    app_id: Optional[str] = None
    key_id: Optional[str] = None
    scopes: tuple[str, ...] = ()
    explicit_archive_request: bool = False
    requires_archive_capability: bool = False


@dataclass(frozen=True)
class ProductAuthorizationDecision:
    allowed: bool
    context: ProductAuthorizationContext
    db_client: object
    read_decision: MemoryReadDecision
    reason: str
    observability: ObservabilityPayload
    policy: Optional[MemoryAccessPolicy] = None
    global_gate: Optional[GlobalReadGateDecision] = None
    rollout: Optional[DefaultReadRolloutDecision] = None
    status_code: int = 403


class MemoryGrantOperation(str, Enum):
    DEFAULT_READ = 'default_read'
    ARCHIVE_READ = 'archive_read'
    WRITE = 'write'


@dataclass(frozen=True)
class AppKeyScopeGrantDecision:
    allowed: bool
    context: ProductAuthorizationContext
    operation: MemoryGrantOperation
    reason: str
    required_scope: str
    observability: ObservabilityPayload
    policy: Optional[MemoryAccessPolicy] = None
    grant_path: Optional[str] = None
    status_code: int = 403


ReadGlobalGate = Callable[..., GlobalReadGateDecision]
ReadRollout = Callable[..., DefaultReadRolloutDecision]
ReadAppKeyGrantsState = Callable[..., AppKeyMemoryGrantStateRead]

EXTERNAL_MEMORY_CONSUMERS = {'third_party', 'developer_api', 'mcp'}
MEMORY_OPERATION_REQUIRED_SCOPES = {
    MemoryGrantOperation.DEFAULT_READ: 'memories.read',
    MemoryGrantOperation.ARCHIVE_READ: 'memories.archive.read',
    MemoryGrantOperation.WRITE: 'memories.write',
}


def _app_context_payload(context: ProductAuthorizationContext) -> ObservabilityPayload:
    return {
        'app_id': context.app_id,
        'key_id': context.key_id,
        'scopes': list(context.scopes),
    }


def _global_read_gate_observability(
    gate: GlobalReadGateDecision, context: ProductAuthorizationContext
) -> ObservabilityPayload:
    return {
        'consumer': context.consumer,
        'surface': context.surface,
        'source_path': gate.source_path,
        'read_decision': gate.read_decision.value,
        'fallback_reason': gate.fallback_reason,
        'reason': gate.fallback_reason or gate.reason,
        'archive_default_visible': False,
        'archive_capability_required': context.requires_archive_capability,
        'explicit_archive_request': context.explicit_archive_request,
        'app_context': _app_context_payload(context),
    }


def _rollout_observability(
    rollout: DefaultReadRolloutDecision, context: ProductAuthorizationContext
) -> ObservabilityPayload:
    build_observability = cast(
        Callable[[DefaultReadRolloutDecision], ObservabilityPayload],
        getattr(default_read_rollout_mod, 'build_default_read_rollout_observability'),
    )
    observability = build_observability(rollout)
    observability.update(
        {
            'surface': context.surface,
            'archive_default_visible': False,
            'archive_capability_required': context.requires_archive_capability,
            'archive_capability_granted': rollout.archive_capability,
            'explicit_archive_request': context.explicit_archive_request,
            'app_context': _app_context_payload(context),
        }
    )
    return observability


def _deny(
    *,
    context: ProductAuthorizationContext,
    db_client: object,
    read_decision: MemoryReadDecision,
    reason: str,
    observability: ObservabilityPayload,
    global_gate: GlobalReadGateDecision | None = None,
    rollout: DefaultReadRolloutDecision | None = None,
) -> ProductAuthorizationDecision:
    observability['reason'] = reason
    if read_decision != MemoryReadDecision.USE_MEMORY:
        observability['fallback_reason'] = reason
    return ProductAuthorizationDecision(
        allowed=False,
        context=context,
        db_client=db_client,
        read_decision=read_decision,
        reason=reason,
        observability=observability,
        policy=None,
        global_gate=global_gate,
        rollout=rollout,
        status_code=403,
    )


def _allow(
    *,
    context: ProductAuthorizationContext,
    db_client: object,
    global_gate: GlobalReadGateDecision,
    rollout: DefaultReadRolloutDecision,
    policy: MemoryAccessPolicy,
    observability: ObservabilityPayload,
) -> ProductAuthorizationDecision:
    return ProductAuthorizationDecision(
        allowed=True,
        context=context,
        db_client=db_client,
        read_decision=MemoryReadDecision.USE_MEMORY,
        reason='ok',
        observability=observability,
        policy=policy,
        global_gate=global_gate,
        rollout=rollout,
        status_code=200,
    )


def _grant_observability(
    context: ProductAuthorizationContext,
    operation: MemoryGrantOperation,
    required_scope: str,
    reason: str,
    grant_path: str | None = None,
) -> ObservabilityPayload:
    return {
        'consumer': context.consumer,
        'surface': context.surface,
        'operation': operation.value,
        'required_scope': required_scope,
        'reason': reason,
        'app_id': context.app_id,
        'key_id': context.key_id,
        'authenticated_scopes': list(context.scopes),
        'grant_path': grant_path,
        'archive_default_visible': False,
    }


def _grant_decision(
    *,
    context: ProductAuthorizationContext,
    operation: MemoryGrantOperation,
    required_scope: str,
    reason: str,
    allowed: bool = False,
    policy: MemoryAccessPolicy | None = None,
    grant_path: str | None = None,
    status_code: int = 403,
) -> AppKeyScopeGrantDecision:
    return AppKeyScopeGrantDecision(
        allowed=allowed or policy is not None,
        context=context,
        operation=operation,
        reason=reason,
        required_scope=required_scope,
        observability=_grant_observability(context, operation, required_scope, reason, grant_path),
        policy=policy,
        grant_path=grant_path,
        status_code=status_code,
    )


def _lookup_app_key_grant(
    context: ProductAuthorizationContext, persisted_grant_state: object
) -> tuple[GrantPayload | None, str | None, bool]:
    if not isinstance(persisted_grant_state, dict):
        return None, None, False
    state = cast(GrantStatePayload, persisted_grant_state)
    grants = state.get('grants')
    if not isinstance(grants, dict):
        return None, None, False
    grant_map = cast(GrantPayload, grants)
    consumer_grants = grant_map.get(context.consumer)
    if not isinstance(consumer_grants, dict):
        return None, None, True
    consumer_grant = cast(GrantPayload, consumer_grants)
    apps = consumer_grant.get('apps')
    if not isinstance(apps, dict):
        return None, None, False
    apps_by_id = cast(GrantPayload, apps)
    app_grant = apps_by_id.get(context.app_id) if context.app_id is not None else None
    if not isinstance(app_grant, dict):
        return None, None, True
    app_grant_payload = cast(GrantPayload, app_grant)
    keys = app_grant_payload.get('keys')
    if not isinstance(keys, dict):
        return None, None, False
    keys_by_id = cast(GrantPayload, keys)
    key_grant = keys_by_id.get(context.key_id) if context.key_id is not None else None
    if key_grant is None:
        return None, None, True
    if not isinstance(key_grant, dict):
        return None, None, False
    return cast(GrantPayload, key_grant), f'grants.{context.consumer}.apps.{context.app_id}.keys.{context.key_id}', True


def _memory_consumer_for_context(context: ProductAuthorizationContext) -> MemoryConsumer:
    try:
        return MemoryConsumer(context.consumer)
    except ValueError:
        return MemoryConsumer.unknown


def authorize_app_key_scope_memory_grant(
    context: ProductAuthorizationContext,
    *,
    persisted_grant_state: object,
    operation: MemoryGrantOperation,
) -> AppKeyScopeGrantDecision:
    """Authorize memory memory access for external app/key/scope consumers.

    First-party Omi chat continues to be governed by the rollout/default-grant
    path in `authorize_memory_product_memory_route`. External consumers must present
    a server-authenticated app id, key id, verified scope, and matching persisted
    app/key grant. Request-provided scopes alone never grant access.
    """

    required_scope = MEMORY_OPERATION_REQUIRED_SCOPES[operation]
    if context.consumer not in EXTERNAL_MEMORY_CONSUMERS:
        return _grant_decision(
            context=context,
            operation=operation,
            required_scope=required_scope,
            reason='first_party_rollout_authorization',
            allowed=True,
            status_code=200,
        )

    if not context.app_id or not context.key_id:
        return _grant_decision(
            context=context,
            operation=operation,
            required_scope=required_scope,
            reason='missing_app_or_key_identity',
        )
    if required_scope not in set(context.scopes):
        return _grant_decision(
            context=context,
            operation=operation,
            required_scope=required_scope,
            reason=f'missing_authenticated_scope_{required_scope}',
        )

    grant, grant_path, structurally_valid = _lookup_app_key_grant(context, persisted_grant_state)
    if not structurally_valid:
        return _grant_decision(
            context=context,
            operation=operation,
            required_scope=required_scope,
            reason='malformed_app_key_scope_grant',
            grant_path=grant_path,
        )
    if grant is None:
        return _grant_decision(
            context=context,
            operation=operation,
            required_scope=required_scope,
            reason='missing_app_key_scope_grant',
            grant_path=grant_path,
        )

    grant_scopes_raw = grant.get('scopes')
    if not isinstance(grant.get('enabled'), bool) or not isinstance(grant_scopes_raw, list):
        return _grant_decision(
            context=context,
            operation=operation,
            required_scope=required_scope,
            reason='malformed_app_key_scope_grant',
            grant_path=grant_path,
        )
    grant_scopes = cast(list[object], grant_scopes_raw)
    if not all(isinstance(scope, str) and scope for scope in grant_scopes):
        return _grant_decision(
            context=context,
            operation=operation,
            required_scope=required_scope,
            reason='malformed_app_key_scope_grant',
            grant_path=grant_path,
        )
    if not grant['enabled']:
        return _grant_decision(
            context=context,
            operation=operation,
            required_scope=required_scope,
            reason='app_key_scope_grant_disabled',
            grant_path=grant_path,
        )
    typed_grant_scopes = [scope for scope in grant_scopes if isinstance(scope, str)]
    if required_scope not in set(typed_grant_scopes):
        return _grant_decision(
            context=context,
            operation=operation,
            required_scope=required_scope,
            reason=f'missing_persisted_scope_{required_scope}',
            grant_path=grant_path,
        )

    operation_flag = operation.value
    if not isinstance(grant.get(operation_flag), bool):
        return _grant_decision(
            context=context,
            operation=operation,
            required_scope=required_scope,
            reason='malformed_app_key_scope_grant',
            grant_path=grant_path,
        )
    if not grant[operation_flag]:
        return _grant_decision(
            context=context,
            operation=operation,
            required_scope=required_scope,
            reason=f'missing_{operation.value}_grant',
            grant_path=grant_path,
        )

    policy = MemoryAccessPolicy(
        consumer=_memory_consumer_for_context(context),
        app_has_default_memory_grant=operation
        in {MemoryGrantOperation.DEFAULT_READ, MemoryGrantOperation.ARCHIVE_READ},
        archive_capability=operation == MemoryGrantOperation.ARCHIVE_READ,
        raw_provenance_capability=False,
    )
    return _grant_decision(
        context=context,
        operation=operation,
        required_scope=required_scope,
        reason='ok',
        policy=policy,
        grant_path=grant_path,
        status_code=200,
    )


def authorize_memory_external_default_memory_read(
    context: ProductAuthorizationContext,
    *,
    db_client: object,
    read_app_key_grants_state: ReadAppKeyGrantsState = cast(
        ReadAppKeyGrantsState, getattr(app_key_grants_db, 'read_app_key_memory_grants_state')
    ),
) -> AppKeyScopeGrantDecision:
    """Compose authenticated external context with stored memory app/key grants.

    This is the narrow route-ready seam for developer/MCP/third-party default
    reads. It requires the caller to supply server-authenticated uid/app/key/scope
    context, reads the server-owned grant document, and delegates to the shared
    app/key/scope grant contract. Missing identity, missing scope, malformed
    stored state, or missing grants fail closed; default-read policies never carry
    Archive capability.
    """

    grant_state_read = read_app_key_grants_state(uid=context.uid, db_client=db_client)
    decision = authorize_app_key_scope_memory_grant(
        context,
        persisted_grant_state=getattr(grant_state_read, 'state', {}),
        operation=MemoryGrantOperation.DEFAULT_READ,
    )
    decision.observability['grant_state_reason'] = getattr(grant_state_read, 'reason', 'unknown_grant_state')
    decision.observability['grant_state_source_path'] = getattr(grant_state_read, 'source_path', None)
    return decision


def authorize_memory_external_default_memory_write(
    context: ProductAuthorizationContext,
    *,
    db_client: object,
    read_app_key_grants_state: ReadAppKeyGrantsState = cast(
        ReadAppKeyGrantsState, getattr(app_key_grants_db, 'read_app_key_memory_grants_state')
    ),
) -> AppKeyScopeGrantDecision:
    """Authorize an external memory write mutation (create/edit/delete).

    Mirrors the read seam but delegates to the WRITE operation so the shared
    app/key/scope grant contract enforces a persisted ``memories.write`` scope and
    matching ``write`` capability flag. Legacy/read-only keys (``scopes=None`` or
    no persisted ``write`` grant) fail closed, preventing mutations to canonical
    memories before any external-memory service call.
    """

    grant_state_read = read_app_key_grants_state(uid=context.uid, db_client=db_client)
    decision = authorize_app_key_scope_memory_grant(
        context,
        persisted_grant_state=getattr(grant_state_read, 'state', {}),
        operation=MemoryGrantOperation.WRITE,
    )
    decision.observability['grant_state_reason'] = getattr(grant_state_read, 'reason', 'unknown_grant_state')
    decision.observability['grant_state_source_path'] = getattr(grant_state_read, 'source_path', None)
    return decision


def authorize_memory_product_memory_route(
    context: ProductAuthorizationContext,
    *,
    db_client: object,
    read_global_gate: ReadGlobalGate = read_global_read_gate,
    read_default_rollout: ReadRollout = read_default_read_rollout,
    read_archive_rollout: ReadRollout = read_archive_read_rollout,
) -> ProductAuthorizationDecision:
    """Authorize a memory product memory route before any `memory_items` access.

    The shared seam performs the server-side decision in one place:
    global read gate/kill switch first, then persisted per-user rollout/grant
    state, and for Archive routes both explicit Archive intent and persisted
    Archive capability. It never creates a default policy with Archive enabled.
    """

    global_gate = read_global_gate(db_client=db_client)
    global_observability = _global_read_gate_observability(global_gate, context)
    if global_gate.read_decision != MemoryReadDecision.USE_MEMORY:
        return _deny(
            context=context,
            db_client=db_client,
            read_decision=global_gate.read_decision,
            reason=global_gate.fallback_reason or global_gate.reason,
            observability=global_observability,
            global_gate=global_gate,
        )

    if context.requires_archive_capability and not context.explicit_archive_request:
        return _deny(
            context=context,
            db_client=db_client,
            read_decision=MemoryReadDecision.DENY_MEMORY,
            reason='missing_explicit_archive_request',
            observability=global_observability,
            global_gate=global_gate,
        )

    rollout_reader = read_archive_rollout if context.requires_archive_capability else read_default_rollout
    rollout = rollout_reader(uid=context.uid, db_client=db_client, consumer=context.consumer)
    rollout_observability = _rollout_observability(rollout, context)

    # Rollout normalization already encodes grant + projection gates in
    # `read_decision` (including SHADOW_ONLY / USE_LEGACY_SAFE / explicit-deny
    # and Archive-capability outcomes with their exact reason strings).
    if rollout.read_decision != MemoryReadDecision.USE_MEMORY:
        return _deny(
            context=context,
            db_client=db_client,
            read_decision=rollout.read_decision,
            reason=rollout.fallback_reason or rollout.reason,
            observability=rollout_observability,
            global_gate=global_gate,
            rollout=rollout,
        )

    if context.requires_archive_capability:
        policy = MemoryAccessPolicy.for_omi_chat(archive_capability=True)
    else:
        policy = MemoryAccessPolicy.for_omi_chat(archive_capability=False)
        rollout_observability['archive_capability_granted'] = False

    return _allow(
        context=context,
        db_client=db_client,
        global_gate=global_gate,
        rollout=rollout,
        policy=policy,
        observability=rollout_observability,
    )
