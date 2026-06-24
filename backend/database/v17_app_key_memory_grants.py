"""Backward-compatible shim — implementation lives in ``database.memory_app_key_grants`` (WS-G7)."""

from database.memory_app_key_grants import (
    V17AppKeyMemoryGrantStateRead,
    V17_APP_KEY_MEMORY_GRANTS_COLLECTION,
    V17_APP_KEY_MEMORY_GRANT_DOC_ID,
    V17_APP_KEY_MEMORY_GRANT_SUBPATH,
    build_v17_app_key_scope_grant_contract_state,
    read_v17_app_key_memory_grants_state,
    v17_app_key_memory_grants_document_path,
)

__all__ = [
    "V17AppKeyMemoryGrantStateRead",
    "V17_APP_KEY_MEMORY_GRANTS_COLLECTION",
    "V17_APP_KEY_MEMORY_GRANT_DOC_ID",
    "V17_APP_KEY_MEMORY_GRANT_SUBPATH",
    "build_v17_app_key_scope_grant_contract_state",
    "read_v17_app_key_memory_grants_state",
    "v17_app_key_memory_grants_document_path",
]
