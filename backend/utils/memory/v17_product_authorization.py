from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from models.v17_product_memory import MemoryAccessPolicy, MemoryConsumer
from utils.memory.v17_default_read_rollout import (
    V17DefaultReadRolloutDecision,
    V17GlobalReadGateDecision,
    V17ReadDecision,
    build_v17_default_read_rollout_observability,
    read_v17_archive_read_rollout,
    read_v17_default_read_rollout,
    read_v17_global_read_gate,
)


@dataclass(frozen=True)
class V17ProductAuthorizationContext:
    """Server-side context for V17 product memory route authorization.

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
class V17ProductAuthorizationDecision:
    allowed: bool
    context: V17ProductAuthorizationContext
    db_client: object
    read_decision: V17ReadDecision
    reason: str
    observability: dict
    policy: Optional[MemoryAccessPolicy] = None
    global_gate: Optional[V17GlobalReadGateDecision] = None
    rollout: Optional[V17DefaultReadRolloutDecision] = None
    status_code: int = 403


class V17MemoryGrantOperation(str, Enum):
    DEFAULT_READ = 'default_read'
    ARCHIVE_READ = 'archive_read'
    WRITE = 'write'


@dataclass(frozen=True)
class V17AppKeyScopeGrantDecision:
    allowed: bool
    context: V17ProductAuthorizationContext
    operation: V17MemoryGrantOperation
    reason: str
    required_scope: str
    observability: dict
    policy: Optional[MemoryAccessPolicy] = None
    grant_path: Optional[str] = None
    status_code: int = 403


ReadGlobalGate = Callable[..., V17GlobalReadGateDecision]
ReadRollout = Callable[..., V17DefaultReadRolloutDecision]

EXTERNAL_V17_MEMORY_CONSUMERS = {'third_party', 'developer_api', 'mcp'}
V17_MEMORY_OPERATION_REQUIRED_SCOPES = {
    V17MemoryGrantOperation.DEFAULT_READ: 'memories.read',
    V17MemoryGrantOperation.ARCHIVE_READ: 'memories.archive.read',
    V17MemoryGrantOperation.WRITE: 'memories.write',
}


def _app_context_payload(context: V17ProductAuthorizationContext) -> dict:
    return {
        'app_id': context.app_id,
        'key_id': context.key_id,
        'scopes': list(context.scopes),
    }


def _global_read_gate_observability(gate: V17GlobalReadGateDecision, context: V17ProductAuthorizationContext) -> dict:
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


def _rollout_observability(rollout: V17DefaultReadRolloutDecision, context: V17ProductAuthorizationContext) -> dict:
    observability = build_v17_default_read_rollout_observability(rollout)
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
    context: V17ProductAuthorizationContext,
    db_client,
    read_decision: V17ReadDecision,
    reason: str,
    observability: dict,
    global_gate: V17GlobalReadGateDecision | None = None,
    rollout: V17DefaultReadRolloutDecision | None = None,
) -> V17ProductAuthorizationDecision:
    observability['reason'] = reason
    if read_decision != V17ReadDecision.USE_V17:
        observability['fallback_reason'] = reason
    return V17ProductAuthorizationDecision(
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
    context: V17ProductAuthorizationContext,
    db_client,
    global_gate: V17GlobalReadGateDecision,
    rollout: V17DefaultReadRolloutDecision,
    policy: MemoryAccessPolicy,
    observability: dict,
) -> V17ProductAuthorizationDecision:
    return V17ProductAuthorizationDecision(
        allowed=True,
        context=context,
        db_client=db_client,
        read_decision=V17ReadDecision.USE_V17,
        reason='ok',
        observability=observability,
        policy=policy,
        global_gate=global_gate,
        rollout=rollout,
        status_code=200,
    )


def _grant_observability(
    context: V17ProductAuthorizationContext,
    operation: V17MemoryGrantOperation,
    required_scope: str,
    reason: str,
    grant_path: str | None = None,
) -> dict:
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
    context: V17ProductAuthorizationContext,
    operation: V17MemoryGrantOperation,
    required_scope: str,
    reason: str,
    allowed: bool = False,
    policy: MemoryAccessPolicy | None = None,
    grant_path: str | None = None,
    status_code: int = 403,
) -> V17AppKeyScopeGrantDecision:
    return V17AppKeyScopeGrantDecision(
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
    context: V17ProductAuthorizationContext, persisted_grant_state
) -> tuple[dict | None, str | None, bool]:
    if not isinstance(persisted_grant_state, dict):
        return None, None, False
    grants = persisted_grant_state.get('grants')
    if not isinstance(grants, dict):
        return None, None, False
    consumer_grants = grants.get(context.consumer)
    if not isinstance(consumer_grants, dict):
        return None, None, True
    apps = consumer_grants.get('apps')
    if not isinstance(apps, dict):
        return None, None, False
    app_grant = apps.get(context.app_id)
    if not isinstance(app_grant, dict):
        return None, None, True
    keys = app_grant.get('keys')
    if not isinstance(keys, dict):
        return None, None, False
    key_grant = keys.get(context.key_id)
    if key_grant is None:
        return None, None, True
    if not isinstance(key_grant, dict):
        return None, None, False
    return key_grant, f'grants.{context.consumer}.apps.{context.app_id}.keys.{context.key_id}', True


def _memory_consumer_for_context(context: V17ProductAuthorizationContext) -> MemoryConsumer:
    try:
        return MemoryConsumer(context.consumer)
    except ValueError:
        return MemoryConsumer.unknown


def authorize_v17_app_key_scope_memory_grant(
    context: V17ProductAuthorizationContext,
    *,
    persisted_grant_state,
    operation: V17MemoryGrantOperation,
) -> V17AppKeyScopeGrantDecision:
    """Authorize V17 memory access for external app/key/scope consumers.

    First-party Omi chat continues to be governed by the rollout/default-grant
    path in `authorize_v17_product_memory_route`. External consumers must present
    a server-authenticated app id, key id, verified scope, and matching persisted
    app/key grant. Request-provided scopes alone never grant access.
    """

    required_scope = V17_MEMORY_OPERATION_REQUIRED_SCOPES[operation]
    if context.consumer not in EXTERNAL_V17_MEMORY_CONSUMERS:
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

    grant_scopes = grant.get('scopes')
    if not isinstance(grant.get('enabled'), bool) or not isinstance(grant_scopes, list):
        return _grant_decision(
            context=context,
            operation=operation,
            required_scope=required_scope,
            reason='malformed_app_key_scope_grant',
            grant_path=grant_path,
        )
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
    if required_scope not in set(grant_scopes):
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
        in {V17MemoryGrantOperation.DEFAULT_READ, V17MemoryGrantOperation.ARCHIVE_READ},
        archive_capability=operation == V17MemoryGrantOperation.ARCHIVE_READ,
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


def authorize_v17_product_memory_route(
    context: V17ProductAuthorizationContext,
    *,
    db_client,
    read_global_gate: ReadGlobalGate = read_v17_global_read_gate,
    read_default_rollout: ReadRollout = read_v17_default_read_rollout,
    read_archive_rollout: ReadRollout = read_v17_archive_read_rollout,
) -> V17ProductAuthorizationDecision:
    """Authorize a V17 product memory route before any `memory_items` access.

    The shared seam performs the server-side decision in one place:
    global read gate/kill switch first, then persisted per-user rollout/grant
    state, and for Archive routes both explicit Archive intent and persisted
    Archive capability. It never creates a default policy with Archive enabled.
    """

    global_gate = read_global_gate(db_client=db_client)
    global_observability = _global_read_gate_observability(global_gate, context)
    if global_gate.read_decision != V17ReadDecision.USE_V17:
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
            read_decision=V17ReadDecision.DENY_MEMORY,
            reason='missing_explicit_archive_request',
            observability=global_observability,
            global_gate=global_gate,
        )

    rollout_reader = read_archive_rollout if context.requires_archive_capability else read_default_rollout
    rollout = rollout_reader(uid=context.uid, db_client=db_client, consumer=context.consumer)
    rollout_observability = _rollout_observability(rollout, context)
    if rollout.read_decision != V17ReadDecision.USE_V17:
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
        if not rollout.archive_capability:
            return _deny(
                context=context,
                db_client=db_client,
                read_decision=V17ReadDecision.DENY_MEMORY,
                reason=rollout.fallback_reason or f'missing_{rollout.grant_reason_key}_archive_capability',
                observability=rollout_observability,
                global_gate=global_gate,
                rollout=rollout,
            )
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
