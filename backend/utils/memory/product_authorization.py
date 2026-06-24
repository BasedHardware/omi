"""Canonical alias module for ``utils.memory.v17_product_authorization`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_product_authorization import (
    EXTERNAL_V17_MEMORY_CONSUMERS,
    ReadAppKeyGrantsState,
    ReadGlobalGate,
    ReadRollout,
    V17AppKeyScopeGrantDecision,
    V17MemoryGrantOperation,
    V17ProductAuthorizationContext,
    V17ProductAuthorizationDecision,
    V17_MEMORY_OPERATION_REQUIRED_SCOPES,
    authorize_v17_app_key_scope_memory_grant,
    authorize_v17_external_default_memory_read,
    authorize_v17_product_memory_route,
)

__all__ = [
    "EXTERNAL_V17_MEMORY_CONSUMERS",
    "ReadAppKeyGrantsState",
    "ReadGlobalGate",
    "ReadRollout",
    "V17AppKeyScopeGrantDecision",
    "V17MemoryGrantOperation",
    "V17ProductAuthorizationContext",
    "V17ProductAuthorizationDecision",
    "V17_MEMORY_OPERATION_REQUIRED_SCOPES",
    "authorize_v17_app_key_scope_memory_grant",
    "authorize_v17_external_default_memory_read",
    "authorize_v17_product_memory_route",
]
