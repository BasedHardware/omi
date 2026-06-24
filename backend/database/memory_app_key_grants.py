"""Canonical app/key memory grant Firestore reader (WS-G7)."""

from dataclasses import dataclass
from typing import Any

APP_KEY_MEMORY_GRANTS_COLLECTION = "memory_control"
APP_KEY_MEMORY_GRANT_DOC_ID = "app_key_memory_grants"
APP_KEY_MEMORY_GRANT_SUBPATH = f"{APP_KEY_MEMORY_GRANTS_COLLECTION}/{APP_KEY_MEMORY_GRANT_DOC_ID}"


@dataclass(frozen=True)
class AppKeyMemoryGrantStateRead:
    present: bool
    malformed: bool
    state: dict[str, Any]
    source_path: str
    reason: str


def app_key_memory_grants_document_path(uid: str) -> str:
    return f"users/{uid}/{APP_KEY_MEMORY_GRANT_SUBPATH}"


def _looks_like_grants_contract(state: Any) -> bool:
    return isinstance(state, dict) and isinstance(state.get("grants"), dict)


def read_app_key_memory_grants_state(uid: str, db_client) -> AppKeyMemoryGrantStateRead:
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

    source_path = app_key_memory_grants_document_path(uid)
    snapshot = (
        db_client.collection(f"users/{uid}/{APP_KEY_MEMORY_GRANTS_COLLECTION}")
        .document(APP_KEY_MEMORY_GRANT_DOC_ID)
        .get()
    )
    if not getattr(snapshot, "exists", False):
        return AppKeyMemoryGrantStateRead(
            present=False,
            malformed=False,
            state={},
            source_path=source_path,
            reason="missing_app_key_memory_grants_state",
        )

    state = snapshot.to_dict()
    if not _looks_like_grants_contract(state):
        return AppKeyMemoryGrantStateRead(
            present=True,
            malformed=True,
            state=state if isinstance(state, dict) else {},
            source_path=source_path,
            reason="malformed_app_key_memory_grants_state",
        )

    return AppKeyMemoryGrantStateRead(
        present=True,
        malformed=False,
        state=state,
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
) -> dict[str, Any]:
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


__all__ = [
    "AppKeyMemoryGrantStateRead",
    "APP_KEY_MEMORY_GRANTS_COLLECTION",
    "APP_KEY_MEMORY_GRANT_DOC_ID",
    "APP_KEY_MEMORY_GRANT_SUBPATH",
    "build_app_key_scope_grant_contract_state",
    "read_app_key_memory_grants_state",
    "app_key_memory_grants_document_path",
]
