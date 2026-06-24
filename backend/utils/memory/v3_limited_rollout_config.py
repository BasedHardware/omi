"""Canonical module for ``utils.memory.v3_limited_rollout_config`` (WS-G8b).

Neutral ``v3_limited_rollout_config`` is the source of truth. Legacy ``v17_v3_limited_rollout_config`` remains an importable alias.
"""

from __future__ import annotations

from dataclasses import dataclass

from config.v17_memory import V17Mode
from database.v17_collections import V17Collections
from utils.memory.v17_default_read_rollout import V17_DEFAULT_READ_ROLLOUT_SCHEMA_VERSION

GLOBAL_READ_GATE_PATH = 'memory_control/v17_global_read_gate'
WRITE_CONVERGENCE_GATE_PATH = 'memory_control/v17_write_convergence_gate'
ROUTE_SCOPE = 'get_v3_memories'
OWNER = 'memory_platform'


@dataclass(frozen=True)
class V17LimitedRolloutConfigBundle:
    uid: str
    documents: dict[str, dict]
    apply_by_default: bool = False
    writes_executed: bool = False


def build_disabled_global_read_gate() -> dict:
    return {
        'route_scope': ROUTE_SCOPE,
        'purpose': 'v17_v3_runtime_enablement',
        'owner': OWNER,
        'config_schema_version': 1,
        'v17_reads_enabled': False,
        'kill_switch_active': True,
    }


def build_write_convergence_gate() -> dict:
    return {
        'route_scope': ROUTE_SCOPE,
        'purpose': 'v17_v3_write_convergence_gate',
        'owner': OWNER,
        'config_schema_version': 1,
        'durable_outbox_enabled': False,
        'dual_write_projection_ready': False,
        'delete_convergence_ready': False,
        'idempotency_contract_ready': False,
    }


def build_whitelisted_user_control_state(
    *,
    uid: str,
    account_generation: int,
    mode: V17Mode = V17Mode.off,
    projection_ready: bool = False,
    default_memory_grant: bool = False,
    archive_grant: bool = False,
) -> dict:
    if not uid:
        raise ValueError('uid required')
    if account_generation < 0:
        raise ValueError('account_generation must be nonnegative')
    return {
        'uid': uid,
        'schema_version': V17_DEFAULT_READ_ROLLOUT_SCHEMA_VERSION,
        'mode': mode.value,
        'mode_epoch': 1,
        'cutover_epoch': 1 if mode == V17Mode.read else 0,
        'account_generation': account_generation,
        'fallback_projection_ready': projection_ready,
        'persistent_v17_writes_started': False,
        'decommission_reconciled': False,
        'writes_blocked': True,
        'stage_gates': {
            'shadow': 'blocked',
            'write': 'blocked',
            'read': 'blocked',
        },
        'grants': {'omi_chat': {'default_memory': default_memory_grant, 'archive': archive_grant}},
    }


def build_limited_rollout_config_bundle(*, uid: str, account_generation: int) -> V17LimitedRolloutConfigBundle:
    """Build an inert, reviewable config template.

    This helper intentionally cannot assert readiness, open the global read gate,
    grant default-memory access, or fabricate `memory_state/head`. Activation must
    be performed by separate deployment tooling from validated production evidence.
    """
    paths = V17Collections(uid=uid)
    return V17LimitedRolloutConfigBundle(
        uid=uid,
        documents={
            GLOBAL_READ_GATE_PATH: build_disabled_global_read_gate(),
            WRITE_CONVERGENCE_GATE_PATH: build_write_convergence_gate(),
            paths.memory_control_state: build_whitelisted_user_control_state(
                uid=uid,
                account_generation=account_generation,
                mode=V17Mode.off,
                projection_ready=False,
                default_memory_grant=False,
            ),
        },
    )


# Neutral symbol aliases (V17 names remain valid via shim)
V3LimitedRolloutConfigBundle = V17LimitedRolloutConfigBundle
