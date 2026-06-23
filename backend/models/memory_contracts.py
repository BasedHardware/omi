"""Canonical alias module for ``models.v17_memory_contracts`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from models.v17_memory_contracts import (
    DurableMemoryPatch,
    DurablePatchDecision,
    LifecycleState,
    deterministic_contract_id,
)

__all__ = [
    "DurableMemoryPatch",
    "DurablePatchDecision",
    "LifecycleState",
    "deterministic_contract_id",
]
