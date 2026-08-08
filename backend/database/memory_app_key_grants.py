"""Canonical app/key memory grant reader/writer over the neutral storage port (WS-G7)."""

from dataclasses import dataclass
from typing import Any, cast

from database.store import get_document_store
from database.store.sentinels import DELETE

StatePayload = dict[str, Any]

APP_KEY_MEMORY_GRANTS_COLLECTION = "memory_control"
APP_KEY_MEMORY_GRANT_DOC_ID = "app_key_memory_grants"
APP_KEY_MEMORY_GRANT_SUBPATH = f"{APP_KEY_MEMORY_GRANTS_COLLECTION}/{APP_KEY_MEMORY_GRANT_DOC_ID}"


def _store():
    return get_document_store()


@dataclass(frozen=True)
class AppKeyMemoryGrantStateRead:
    present: bool
    malformed: bool
    state: StatePayload
    source_path: str
    reason: str


def app_key_memory_grants_document_path(uid: str) -> str:
    return f"users/{uid}/{APP_KEY_MEMORY_GRANT_SUBPATH}"


def _looks_like_grants_contract(state: object) -> bool:
    if not isinstance(state, dict):
        return False
    state_payload = cast(StatePayload, state)
    return isinstance(state_payload.get("grants"), dict)


def read_app_key_memory_grants_state(uid: str) -> AppKeyMemoryGrantStateRead:
    """Read the server-owned persisted memory app/key memory grant document.

    Logical path:
      users/{uid}/memory_control/app_key_memory_grants

    Document shape is intentionally the same nested contract consumed by
    `authorize_app_key_scope_memory_grant(...)`:
      grants.<consumer>.apps.<app_id>.keys.<key_id>

    This helper only reads server-owned state through the neutral storage port.
    It does not accept request-body fields, and missing/malformed state is
    surfaced so callers can fail closed through the authorization contract.
    """

    source_path = app_key_memory_grants_document_path(uid)
    snapshot = _store().get(source_path)
    if not snapshot.exists:
        return AppKeyMemoryGrantStateRead(
            present=False,
            malformed=False,
            state={},
            source_path=source_path,
            reason="missing_app_key_memory_grants_state",
        )

    state: object = snapshot.to_dict()
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

    return {
        "grants": {
            consumer: {
                "apps": {
                    app_id: {
                        "keys": {
                            key_id: {
                                "enabled": enabled,
                                "scopes": scopes,
                                "default_read": default_read,
                                "archive_read": archive_read,
                                "write": write,
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


def _memory_scopes(default_read: bool, write: bool) -> list[str]:
    scopes: list[str] = []
    if default_read:
        scopes.append('memories.read')
    if write:
        scopes.append('memories.write')
    return scopes


def _seed_app_key_memory_grant(
    uid: str,
    consumer: str,
    app_id: str,
    key_id: str,
    *,
    default_read: bool,
    write: bool,
) -> str:
    """Create-or-merge the single nested key grant, preserving sibling grants.

    The persisted contract is a nested map keyed by consumer/app/key. Firestore
    ``set(merge=True)`` deep-merges nested maps, but that is a backend-specific
    guarantee — the neutral port merges a nested map by writing a *dotted-key
    update* (honored identically across backends). A dotted-key update raises on
    a missing document, so the create-or-merge runs inside a transaction: on an
    existing document only the ``...keys.<key_id>`` leaf is written (siblings
    preserved); on a missing document the full nested contract is created.
    """

    contract = build_app_key_scope_grant_contract_state(
        consumer=consumer,
        app_id=app_id,
        key_id=key_id,
        scopes=_memory_scopes(default_read, write),
        default_read=default_read,
        archive_read=False,
        write=write,
        enabled=True,
    )
    leaf = contract["grants"][consumer]["apps"][app_id]["keys"][key_id]
    field_path = f"grants.{consumer}.apps.{app_id}.keys.{key_id}"
    document_path = app_key_memory_grants_document_path(uid)

    def _write(tx) -> None:
        snapshot = tx.get(document_path)
        if snapshot.exists:
            tx.update(document_path, {field_path: leaf})
        else:
            tx.set(document_path, contract)

    _store().run_transaction(_write)
    return document_path


def seed_developer_api_key_memory_grant(
    uid: str,
    key_id: str,
    *,
    default_read: bool = False,
    write: bool = False,
) -> str:
    """Seed the server-owned app/key memory grant for a Developer API key.

    Developer API keys created with ``memories:read`` and/or ``memories:write``
    scopes need a matching persisted grant at
    ``users/{uid}/memory_control/app_key_memory_grants`` so the grant gate
    (``authorize_memory_external_default_memory_read`` / ``_write``) does not
    reject a freshly created key with ``missing_app_key_scope_grant``.

    This performs a merge write so existing grants for other keys are preserved.
    Returns the document path written.
    """
    return _seed_app_key_memory_grant(
        uid,
        DEVELOPER_API_CONSUMER,
        DEVELOPER_API_DEFAULT_APP_ID,
        key_id,
        default_read=default_read,
        write=write,
    )


def seed_mcp_api_key_memory_grant(
    uid: str,
    key_id: str,
    *,
    default_read: bool = False,
    write: bool = False,
) -> str:
    """Seed the server-owned app/key memory grant for a hosted MCP key."""
    return _seed_app_key_memory_grant(
        uid,
        MCP_CONSUMER,
        MCP_DEFAULT_APP_ID,
        key_id,
        default_read=default_read,
        write=write,
    )


def remove_developer_api_key_memory_grant(uid: str, key_id: str) -> None:
    """Remove the persisted app/key memory grant for a deleted Developer API key.

    Deletes only the nested key entry via a dotted field-path deletion,
    preserving grants for other keys under the same document.
    """
    document_path = app_key_memory_grants_document_path(uid)
    store = _store()

    # Guard against legacy keys that were created without memory scopes or
    # predate grant seeding: a dotted-key ``update`` on a missing document raises
    # NotFound, which would turn a successful key deletion into a 500. If the
    # grant document does not exist, there is nothing to remove.
    if not store.exists(document_path):
        return

    # UUID key ids contain hyphens; the neutral port splits a dotted key on '.'
    # only, so the hyphenated leaf is targeted unambiguously without escaping.
    field_path = f"grants.{DEVELOPER_API_CONSUMER}.apps.{DEVELOPER_API_DEFAULT_APP_ID}.keys.{key_id}"
    store.update(document_path, {field_path: DELETE})


__all__ = [
    "AppKeyMemoryGrantStateRead",
    "APP_KEY_MEMORY_GRANTS_COLLECTION",
    "APP_KEY_MEMORY_GRANT_DOC_ID",
    "APP_KEY_MEMORY_GRANT_SUBPATH",
    "build_app_key_scope_grant_contract_state",
    "read_app_key_memory_grants_state",
    "app_key_memory_grants_document_path",
    "seed_developer_api_key_memory_grant",
    "seed_mcp_api_key_memory_grant",
    "remove_developer_api_key_memory_grant",
]
