"""Canonical app/key memory grant Firestore reader (WS-G7)."""

from dataclasses import dataclass
from typing import Any

V17_APP_KEY_MEMORY_GRANTS_COLLECTION = "memory_control"
V17_APP_KEY_MEMORY_GRANT_DOC_ID = "v17_app_key_memory_grants"
V17_APP_KEY_MEMORY_GRANT_SUBPATH = f"{V17_APP_KEY_MEMORY_GRANTS_COLLECTION}/{V17_APP_KEY_MEMORY_GRANT_DOC_ID}"


@dataclass(frozen=True)
class V17AppKeyMemoryGrantStateRead:
    present: bool
    malformed: bool
    state: dict[str, Any]
    source_path: str
    reason: str


def v17_app_key_memory_grants_document_path(uid: str) -> str:
    return f"users/{uid}/{V17_APP_KEY_MEMORY_GRANT_SUBPATH}"


def _looks_like_grants_contract(state: Any) -> bool:
    return isinstance(state, dict) and isinstance(state.get("grants"), dict)


def read_v17_app_key_memory_grants_state(uid: str, db_client) -> V17AppKeyMemoryGrantStateRead:
    """Read the server-owned persisted V17 app/key memory grant document.

    Firestore path:
      users/{uid}/memory_control/v17_app_key_memory_grants

    Document shape is intentionally the same nested contract consumed by
    `authorize_v17_app_key_scope_memory_grant(...)`:
      grants.<consumer>.apps.<app_id>.keys.<key_id>

    This helper only reads server-owned state through an explicitly supplied
    backend/Admin SDK client. It does not accept request-body fields, and
    missing/malformed state is surfaced so callers can fail closed through the
    authorization contract.
    """

    source_path = v17_app_key_memory_grants_document_path(uid)
    snapshot = (
        db_client.collection(f"users/{uid}/{V17_APP_KEY_MEMORY_GRANTS_COLLECTION}")
        .document(V17_APP_KEY_MEMORY_GRANT_DOC_ID)
        .get()
    )
    if not getattr(snapshot, "exists", False):
        return V17AppKeyMemoryGrantStateRead(
            present=False,
            malformed=False,
            state={},
            source_path=source_path,
            reason="missing_v17_app_key_memory_grants_state",
        )

    state = snapshot.to_dict()
    if not _looks_like_grants_contract(state):
        return V17AppKeyMemoryGrantStateRead(
            present=True,
            malformed=True,
            state=state if isinstance(state, dict) else {},
            source_path=source_path,
            reason="malformed_v17_app_key_memory_grants_state",
        )

    return V17AppKeyMemoryGrantStateRead(
        present=True,
        malformed=False,
        state=state,
        source_path=source_path,
        reason="ok",
    )


def build_v17_app_key_scope_grant_contract_state(
    *,
    consumer: str,
    app_id: str,
    key_id: str,
    scopes: list[str],
    default_read: bool = False,
    archive_read: bool = False,
    write: bool = False,
    enabled: bool = True,
) -> dict[str, Any]:
    """Build the persisted nested grant contract used by tests/admin tooling.

    This is a pure shape helper, not a client-write API. Server admin tooling may
    merge the returned nested map into
    `users/{uid}/memory_control/v17_app_key_memory_grants`.
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


__all__ = [
    "V17AppKeyMemoryGrantStateRead",
    "V17_APP_KEY_MEMORY_GRANTS_COLLECTION",
    "V17_APP_KEY_MEMORY_GRANT_DOC_ID",
    "V17_APP_KEY_MEMORY_GRANT_SUBPATH",
    "build_v17_app_key_scope_grant_contract_state",
    "read_v17_app_key_memory_grants_state",
    "v17_app_key_memory_grants_document_path",
]
