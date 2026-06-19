from dataclasses import dataclass
from typing import Callable, Optional

from models.v17_product_memory import MemoryAccessPolicy
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


ReadGlobalGate = Callable[..., V17GlobalReadGateDecision]
ReadRollout = Callable[..., V17DefaultReadRolloutDecision]


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
