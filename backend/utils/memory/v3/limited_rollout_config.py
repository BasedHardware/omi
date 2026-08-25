"""Canonical module for ``utils.memory.v3.limited_rollout_config`` (WS-G8b).

This module owns V3 limited-rollout configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config.memory_rollout import MemoryRolloutMode
from database.memory_collections import MemoryCollections
from utils.memory.default_read_rollout import DEFAULT_READ_ROLLOUT_SCHEMA_VERSION

GLOBAL_READ_GATE_PATH = 'memory_control/global_read_gate'
WRITE_CONVERGENCE_GATE_PATH = 'memory_control/write_convergence_gate'
ROUTE_SCOPE = 'get_v3_memories'
OWNER = 'memory_platform'


@dataclass(frozen=True)
class LimitedRolloutConfigBundle:
    uid: str
    documents: dict[str, dict[str, Any]]
    apply_by_default: bool = False
    writes_executed: bool = False


def build_disabled_global_read_gate() -> dict[str, Any]:
    return {
        'route_scope': ROUTE_SCOPE,
        'purpose': 'v3_runtime_enablement',
        'owner': OWNER,
        'config_schema_version': 1,
        'memory_reads_enabled': False,
        'kill_switch_active': True,
    }


def build_write_convergence_gate() -> dict[str, Any]:
    return {
        'route_scope': ROUTE_SCOPE,
        'purpose': 'v3_write_convergence_gate',
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
    mode: MemoryRolloutMode = MemoryRolloutMode.off,
    projection_ready: bool = False,
    default_memory_grant: bool = False,
    archive_grant: bool = False,
) -> dict[str, Any]:
    if not uid:
        raise ValueError('uid required')
    if account_generation < 0:
        raise ValueError('account_generation must be nonnegative')
    return {
        'uid': uid,
        'schema_version': DEFAULT_READ_ROLLOUT_SCHEMA_VERSION,
        'mode': mode.value,
        'mode_epoch': 1,
        'cutover_epoch': 1 if mode == MemoryRolloutMode.read else 0,
        'account_generation': account_generation,
        'fallback_projection_ready': projection_ready,
        'persistent_memory_writes_started': False,
        'decommission_reconciled': False,
        'writes_blocked': True,
        'stage_gates': {
            'shadow': 'blocked',
            'write': 'blocked',
            'read': 'blocked',
        },
        'grants': {'omi_chat': {'default_memory': default_memory_grant, 'archive': archive_grant}},
    }


def build_limited_rollout_config_bundle(*, uid: str, account_generation: int) -> LimitedRolloutConfigBundle:
    """Build an inert, reviewable config template.

    This helper intentionally cannot assert readiness, open the global read gate,
    grant default-memory access, or fabricate `memory_state/head`. Activation must
    be performed by separate deployment tooling from validated production evidence.
    """
    paths = MemoryCollections(uid=uid)
    return LimitedRolloutConfigBundle(
        uid=uid,
        documents={
            GLOBAL_READ_GATE_PATH: build_disabled_global_read_gate(),
            WRITE_CONVERGENCE_GATE_PATH: build_write_convergence_gate(),
            paths.memory_control_state: build_whitelisted_user_control_state(
                uid=uid,
                account_generation=account_generation,
                mode=MemoryRolloutMode.off,
                projection_ready=False,
                default_memory_grant=False,
            ),
        },
    )


# Neutral symbol aliases (memory names remain valid via shim)
V3LimitedRolloutConfigBundle = LimitedRolloutConfigBundle
