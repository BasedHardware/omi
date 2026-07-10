"""Shared memory read rollout decision primitives.

Both surface adapters (MCP/chat/developer via ``default_read_rollout``) and the
external ``/v3`` GET stack (``v3_control_reader_contract`` / ``v3_compatibility``)
normalize the same Firestore grant and operational-gate inputs. This module holds
that shared core so grant resolution and enrolled read-mode gate evaluation stay
aligned without collapsing surface-specific or v3-specific routing behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, cast


class MemoryReadGateBlock(str, Enum):
    NONE = 'none'
    GLOBAL_READ_GATE_CLOSED = 'global_read_gate_closed'
    NO_DEFAULT_MEMORY_GRANT = 'no_default_memory_grant'
    WRITE_CONVERGENCE_NOT_READY = 'write_convergence_not_ready'
    PROJECTION_NOT_READY = 'projection_not_ready'


SUPPORTED_ENROLLED_CONTROL_STATES = frozenset({'valid'})
ENROLLED_FAIL_CLOSED_CONTROL_STATES = frozenset(
    {
        'missing',
        'malformed',
        'uid_mismatch',
        'unsupported_schema',
        'control_timeout',
    }
)


@dataclass(frozen=True)
class ConsumerGrantSnapshot:
    default_memory: bool
    archive_capability: bool | None


@dataclass(frozen=True)
class EnrolledMemoryReadGateContext:
    """Normalized enrolled read-mode inputs for shared gate evaluation."""

    global_read_gate_open: bool
    default_memory_grant: bool | None
    memory_reads_enabled: bool
    write_convergence_ready: bool
    rollout_write_ready: bool = True
    check_global_read_gate: bool = True
    require_write_convergence: bool = True
    require_rollout_write_for_convergence: bool = True


@dataclass(frozen=True)
class EnrolledMemoryReadGateResult:
    blocked: bool
    block: MemoryReadGateBlock
    grant_denied: bool = False


def extract_consumer_grants(data: dict[str, Any], consumer: str) -> ConsumerGrantSnapshot:
    """Resolve per-consumer default-memory and archive grants from control state."""

    grants = data.get('grants')
    if not isinstance(grants, dict):
        return ConsumerGrantSnapshot(default_memory=False, archive_capability=False)
    grant_map = cast(dict[str, Any], grants)
    consumer_grants = grant_map.get(consumer)
    if not isinstance(consumer_grants, dict):
        return ConsumerGrantSnapshot(default_memory=False, archive_capability=False)
    consumer_grant_map = cast(dict[str, Any], consumer_grants)
    default_memory = consumer_grant_map.get('default_memory') is True
    if 'archive' not in consumer_grant_map:
        return ConsumerGrantSnapshot(default_memory=default_memory, archive_capability=False)
    archive_capability = consumer_grant_map.get('archive')
    if not isinstance(archive_capability, bool):
        return ConsumerGrantSnapshot(default_memory=default_memory, archive_capability=None)
    return ConsumerGrantSnapshot(default_memory=default_memory, archive_capability=archive_capability)


def evaluate_enrolled_memory_read_gates(context: EnrolledMemoryReadGateContext) -> EnrolledMemoryReadGateResult:
    """Evaluate shared enrolled read-mode operational gates.

    Surface default-read authorization checks global gate and grant/rollout mode
    separately and does not require write convergence for reads. The external
    ``/v3`` GET path sets ``require_write_convergence=True`` so split-brain legacy
    writes remain blocked until convergence is ready.
    """

    if context.check_global_read_gate and not context.global_read_gate_open:
        return EnrolledMemoryReadGateResult(
            blocked=True,
            block=MemoryReadGateBlock.GLOBAL_READ_GATE_CLOSED,
        )
    if context.default_memory_grant is not True:
        return EnrolledMemoryReadGateResult(
            blocked=True,
            block=MemoryReadGateBlock.NO_DEFAULT_MEMORY_GRANT,
            grant_denied=True,
        )
    if context.require_write_convergence:
        convergence_ready = context.write_convergence_ready
        if context.require_rollout_write_for_convergence:
            convergence_ready = convergence_ready and context.rollout_write_ready
        if not convergence_ready:
            return EnrolledMemoryReadGateResult(
                blocked=True,
                block=MemoryReadGateBlock.WRITE_CONVERGENCE_NOT_READY,
            )
    if not context.memory_reads_enabled:
        return EnrolledMemoryReadGateResult(
            blocked=True,
            block=MemoryReadGateBlock.PROJECTION_NOT_READY,
        )
    return EnrolledMemoryReadGateResult(blocked=False, block=MemoryReadGateBlock.NONE)


def surface_rollout_allows_memory_read(
    *,
    global_read_gate_open: bool,
    default_memory_grant: bool,
    memory_reads_enabled: bool,
) -> EnrolledMemoryReadGateResult:
    """Map surface adapter inputs onto the shared enrolled gate evaluator."""

    return evaluate_enrolled_memory_read_gates(
        EnrolledMemoryReadGateContext(
            global_read_gate_open=global_read_gate_open,
            default_memory_grant=default_memory_grant,
            memory_reads_enabled=memory_reads_enabled,
            write_convergence_ready=True,
            rollout_write_ready=True,
            check_global_read_gate=True,
            require_write_convergence=False,
            require_rollout_write_for_convergence=False,
        )
    )


def v3_rollout_allows_memory_read(
    *,
    global_read_gate_open: bool,
    default_memory_grant: bool,
    memory_reads_enabled: bool,
    write_convergence_ready: bool,
    rollout_write_ready: bool,
) -> EnrolledMemoryReadGateResult:
    """Map external ``/v3`` enrolled read-mode inputs onto the shared gate evaluator."""

    return evaluate_enrolled_memory_read_gates(
        EnrolledMemoryReadGateContext(
            global_read_gate_open=global_read_gate_open,
            default_memory_grant=default_memory_grant,
            memory_reads_enabled=memory_reads_enabled,
            write_convergence_ready=write_convergence_ready,
            rollout_write_ready=rollout_write_ready,
            check_global_read_gate=True,
            require_write_convergence=True,
            require_rollout_write_for_convergence=True,
        )
    )
