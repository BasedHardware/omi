"""Canonical app/key memory grant Firestore reader (WS-G7).

Design: identifier validation fails fast with ValueError; missing grant state
degrades safely to ungranted/missing with fail-closed semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, cast

from google.api_core.exceptions import GoogleAPICallError, NotFound
from google.cloud import firestore

import database._client as db_client_module

StatePayload = dict[str, Any]

APP_KEY_MEMORY_GRANTS_COLLECTION = "memory_control"
APP_KEY_MEMORY_GRANT_DOC_ID = "app_key_memory_grants"
APP_KEY_MEMORY_GRANT_SUBPATH = f"{APP_KEY_MEMORY_GRANTS_COLLECTION}/{APP_KEY_MEMORY_GRANT_DOC_ID}"
MAX_SCOPES_PER_GRANT = 100


@dataclass(frozen=True)
class AppKeyMemoryGrantStateRead:
    present: bool
    malformed: bool
    state: StatePayload
    source_path: str
    reason: str


def _validate_non_empty_string(val: object, name: str) -> str:
    """Validate and return normalized non-empty string."""
    if not isinstance(val, str) or not val.strip():
        raise ValueError(f"{name} must be a non-empty string without whitespace")
    if "/" in val:
        raise ValueError(f"{name} cannot contain path delimiters")
    return val.strip()


def app_key_memory_grants_document_path(uid: str) -> str:
    clean_uid = _validate_non_empty_string(uid, "uid")
    return f"users/{clean_uid}/{APP_KEY_MEMORY_GRANT_SUBPATH}"


def _looks_like_grants_contract(state: object) -> bool:
    if not isinstance(state, dict):
        return False
    state_payload = cast(StatePayload, state)
    return isinstance(state_payload.get("grants"), dict)


def _default_db_client(db_client: Optional[Any]) -> Any:
    return db_client if db_client is not None else getattr(db_client_module, "db", None)


def read_app_key_memory_grants_state(uid: str, db_client: Any) -> AppKeyMemoryGrantStateRead:
    """Read the server-owned persisted memory app/key memory grant document.

    Firestore path:
      users/{uid}/memory_control/app_key_memory_grants

    Document shape is intentionally the same nested contract consumed by
    `authorize_app_key_scope_memory_grant(...)`:
      grants.<consumer>.apps.<app_id>.keys.<key_id>

    This helper only reads server-owned state through an explicitly supplied
    backend/Admin SDK client. It does not accept request-body fields, and
    missing/malformed state is surfaced so callers can fail closed through the
    authorization contract.
    """
    clean_uid = _validate_non_empty_string(uid, "uid")
    if db_client is None:
        raise ValueError("db_client is required")

    source_path = app_key_memory_grants_document_path(clean_uid)
    client: Any = db_client
    try:
        snapshot = (
            client.collection(f"users/{clean_uid}/{APP_KEY_MEMORY_GRANTS_COLLECTION}").document(APP_KEY_MEMORY_GRANT_DOC_ID).get()
        )
    except NotFound:
        return AppKeyMemoryGrantStateRead(
            present=False,
            malformed=False,
            state={},
            source_path=source_path,
            reason="missing_app_key_memory_grants_state",
        )
    except GoogleAPICallError:
        raise

    if not getattr(snapshot, "exists", False):
        return AppKeyMemoryGrantStateRead(
            present=False,
            malformed=False,
            state={},
            source_path=source_path,
            reason="missing_app_key_memory_grants_state",
        )

    raw_state = snapshot.to_dict() if hasattr(snapshot, "to_dict") else None
    state: object = raw_state if isinstance(raw_state, dict) else {}
    if not _looks_like_grants_contract(state):
        return AppKeyMemoryGrantStateRead(
            present=True,
            malformed=True,
            state=cast(StatePayload, state) if isinstance(state, dict) else {},
            source_path=source_path,
            reason="malformed_app_key_memory_grants_state",
        )

    return AppKeyMemoryGrantStateRead(
        present=True,
        malformed=False,
        state=cast(StatePayload, state),
        source_path=source_path,
        reason="ok",
    )


def build_app_key_scope_grant_contract_state(
    *,
    consumer: str,
    app_id: str,
    key_id: str,
    scopes: list[str],
    default_read: bool = False,
    archive_read: bool = False,
    write: bool = False,
    enabled: bool = True,
) -> StatePayload:
    """Build the persisted nested grant contract used by tests/admin tooling.

    This is a pure shape helper, not a client-write API. Server admin tooling may
    merge the returned nested map into
    `users/{uid}/memory_control/app_key_memory_grants`.
    """
    clean_consumer = _validate_non_empty_string(consumer, "consumer")
    clean_app_id = _validate_non_empty_string(app_id, "app_id")
    clean_key_id = _validate_non_empty_string(key_id, "key_id")
    if not isinstance(scopes, list) or any(not isinstance(s, str) or not s.strip() for s in scopes):
        raise ValueError("scopes must be a list of non-empty strings")
    if len(scopes) > MAX_SCOPES_PER_GRANT:
        raise ValueError("scopes list exceeds maximum allowed length")

    return {
        "grants": {
            clean_consumer: {
                "apps": {
                    clean_app_id: {
                        "keys": {
                            clean_key_id: {
                                "enabled": bool(enabled),
                                "scopes": [s.strip() for s in scopes],
                                "default_read": bool(default_read),
                                "archive_read": bool(archive_read),
                                "write": bool(write),
                            }
                        }
                    }
                }
            }
        }
    }


DEVELOPER_API_CONSUMER = 'developer_api'
DEVELOPER_API_DEFAULT_APP_ID = 'developer_api'
MCP_CONSUMER = 'mcp'
MCP_DEFAULT_APP_ID = 'mcp-api'


def seed_developer_api_key_memory_grant(
    uid: str,
    key_id: str,
    *,
    default_read: bool = False,
    write: bool = False,
    db_client: Optional[Any] = None,
) -> str:
    """Seed the server-owned app/key memory grant for a Developer API key.

    Developer API keys created with ``memories:read`` and/or ``memories:write``
    scopes need a matching persisted grant at
    ``users/{uid}/memory_control/app_key_memory_grants`` so the grant gate
    (``authorize_memory_external_default_memory_read`` / ``_write``) does not
    reject a freshly created key with ``missing_app_key_scope_grant``.

    This performs a merge write so existing grants for other keys are preserved.
    Returns the Firestore document path written.
    """
    clean_uid = _validate_non_empty_string(uid, "uid")
    clean_key_id = _validate_non_empty_string(key_id, "key_id")
    client = _default_db_client(db_client)
    if client is None:
        raise ValueError("db_client is required")

    scopes: list[str] = []
    if default_read:
        scopes.append('memories.read')
    if write:
        scopes.append('memories.write')

    contract = build_app_key_scope_grant_contract_state(
        consumer=DEVELOPER_API_CONSUMER,
        app_id=DEVELOPER_API_DEFAULT_APP_ID,
        key_id=clean_key_id,
        scopes=scopes,
        default_read=default_read,
        archive_read=False,
        write=write,
        enabled=True,
    )
    document_path = app_key_memory_grants_document_path(clean_uid)
    client.document(document_path).set(contract, merge=True)
    return document_path


def seed_mcp_api_key_memory_grant(
    uid: str,
    key_id: str,
    *,
    default_read: bool = False,
    write: bool = False,
    db_client: Optional[Any] = None,
) -> str:
    """Seed the server-owned app/key memory grant for a hosted MCP key."""
    clean_uid = _validate_non_empty_string(uid, "uid")
    clean_key_id = _validate_non_empty_string(key_id, "key_id")
    client = _default_db_client(db_client)
    if client is None:
        raise ValueError("db_client is required")

    scopes: list[str] = []
    if default_read:
        scopes.append('memories.read')
    if write:
        scopes.append('memories.write')

    contract = build_app_key_scope_grant_contract_state(
        consumer=MCP_CONSUMER,
        app_id=MCP_DEFAULT_APP_ID,
        key_id=clean_key_id,
        scopes=scopes,
        default_read=default_read,
        archive_read=False,
        write=write,
        enabled=True,
    )
    document_path = app_key_memory_grants_document_path(clean_uid)
    client.document(document_path).set(contract, merge=True)
    return document_path


def remove_developer_api_key_memory_grant(
    uid: str,
    key_id: str,
    *,
    db_client: Optional[Any] = None,
) -> None:
    """Remove the persisted app/key memory grant for a deleted Developer API key.

    Deletes only the nested key entry via field-path deletion, preserving grants
    for other keys under the same document.
    """
    clean_uid = _validate_non_empty_string(uid, "uid")
    clean_key_id = _validate_non_empty_string(key_id, "key_id")
    client = _default_db_client(db_client)
    if client is None:
        raise ValueError("db_client is required")

    document_path = app_key_memory_grants_document_path(clean_uid)
    doc_ref: Any = client.document(document_path)

    try:
        snapshot = doc_ref.get()
        if not getattr(snapshot, "exists", False):
            return
    except NotFound:
        return

    from google.cloud.firestore_v1.field_path import FieldPath

    field_path = FieldPath(
        "grants",
        DEVELOPER_API_CONSUMER,
        "apps",
        DEVELOPER_API_DEFAULT_APP_ID,
        "keys",
        clean_key_id,
    ).to_api_repr()
    try:
        doc_ref.update({field_path: firestore.DELETE_FIELD})
    except NotFound:
        return


__all__ = [
    "AppKeyMemoryGrantStateRead",
    "APP_KEY_MEMORY_GRANTS_COLLECTION",
    "APP_KEY_MEMORY_GRANT_DOC_ID",
    "APP_KEY_MEMORY_GRANT_SUBPATH",
    "MAX_SCOPES_PER_GRANT",
    "build_app_key_scope_grant_contract_state",
    "read_app_key_memory_grants_state",
    "app_key_memory_grants_document_path",
    "seed_developer_api_key_memory_grant",
    "seed_mcp_api_key_memory_grant",
    "remove_developer_api_key_memory_grant",
]

