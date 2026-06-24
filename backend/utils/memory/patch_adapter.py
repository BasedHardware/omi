"""Canonical alias module for ``utils.memory.v17_patch_adapter`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_patch_adapter import (
    apply_v17_patch_to_ledger_state,
    patch_to_ledger_mutations,
    persist_non_active_route_for_patch,
)

__all__ = [
    "apply_v17_patch_to_ledger_state",
    "patch_to_ledger_mutations",
    "persist_non_active_route_for_patch",
]
