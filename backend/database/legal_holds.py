"""Server-owned legal-hold and destructive-operation coordination.

Every supported destructive path and the legal-hold writer contend on the
same per-account gate document. This gives the system a real linearization
point: either an active hold is committed first and deletion cannot start, or
deletion owns the gate and a later hold placement is rejected until its
outcome is known. User-facing routes never write either authority document.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Iterator
from uuid import uuid4

from google.cloud.firestore_v1 import transactional

from database.account_deletion_marker import account_deletion_firestore_client
from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status

logger = logging.getLogger(__name__)

LEGAL_HOLDS_COLLECTION = "legal_holds"
LEGAL_HOLD_DELETION_GATES_COLLECTION = "legal_hold_deletion_gates"
LEGAL_HOLD_SCHEMA_VERSION = "legal_hold.v1"
LEGAL_HOLD_DELETION_GATE_SCHEMA_VERSION = "legal_hold_deletion_gate.v1"
_AUTHORIZED_ISSUERS = frozenset({"admin", "legal_hold_service"})
_GATE_STATES = frozenset({"running", "failed", "completed"})
_DREAM_RETRYABLE_GATE_KINDS = frozenset(
    {"explicit_memory_deletion", "retention_cleanup", "audio_conversation_deletion"}
)
# A gate row whose holder crashed before finishing would otherwise block that
# account forever: there is no janitor for this collection. A "running" gate
# older than this bound is treated as abandoned — acquire may take it over and
# fences stop honoring it. Real destructive operations finish in minutes; the
# bound is deliberately generous so it can never race a live wipe.
GATE_STALE_AFTER_SECONDS = 6 * 60 * 60
# Historical kind written by provider-write paths in earlier builds of this
# branch. Writers now use ``external_write_fence`` and never own the gate, so
# a lingering "running" row of this kind is always an abandoned artifact.
_OBSOLETE_WRITER_GATE_KIND = "external_data_write"
_ACTIVE_GATE: ContextVar[tuple[str, str, str] | None] = ContextVar("active_legal_hold_deletion_gate", default=None)
_EXTERNAL_TRANSACTION: ContextVar[tuple[str, Any, Any] | None] = ContextVar("external_write_transaction", default=None)


class LegalHoldAuthorityUnavailable(RuntimeError):
    """The server cannot prove that destructive deletion is permitted."""


class LegalHoldActive(RuntimeError):
    """A server/admin-owned active legal hold blocks destructive deletion."""


class DestructiveOperationInProgress(RuntimeError):
    """Another destructive operation owns the account gate."""


class DestructiveGateTakeover(RuntimeError):
    """The active holder lost its authority and must stop destructive work."""


def _document(client: Any, path: str) -> Any:
    collection_name, document_id = path.split("/", 1)
    document = getattr(client, "document", None)
    if callable(document):
        return document(path)
    collection = getattr(client, "collection", None)
    if callable(collection):
        collection_ref: Any = collection(collection_name)
        return collection_ref.document(document_id)
    raise LegalHoldAuthorityUnavailable("Firestore document authority is unavailable")


def _snapshot_payload(snapshot: Any, *, label: str) -> dict[str, Any] | None:
    exists = getattr(snapshot, "exists", None)
    if not isinstance(exists, bool):
        raise LegalHoldAuthorityUnavailable(f"{label} existence state is malformed")
    if not exists:
        return None
    try:
        payload = snapshot.to_dict() or {}
    except Exception as exc:  # noqa: BLE001 - authority reads fail closed
        raise LegalHoldAuthorityUnavailable(f"{label} is unreadable") from exc
    if not isinstance(payload, dict):
        raise LegalHoldAuthorityUnavailable(f"{label} is malformed")
    return payload


def _validated_hold(snapshot: Any) -> dict[str, Any] | None:
    payload = _snapshot_payload(snapshot, label="legal-hold authority")
    if payload is None:
        return None
    if payload.get("schema_version") != LEGAL_HOLD_SCHEMA_VERSION:
        raise LegalHoldAuthorityUnavailable("legal-hold authority schema is unsupported")
    if payload.get("issuer") not in _AUTHORIZED_ISSUERS:
        raise LegalHoldAuthorityUnavailable("legal-hold authority issuer is not trusted")
    if not isinstance(payload.get("active"), bool):
        raise LegalHoldAuthorityUnavailable("legal-hold authority active state is malformed")
    return payload


def _validated_gate(snapshot: Any) -> dict[str, Any] | None:
    payload = _snapshot_payload(snapshot, label="legal-hold deletion gate")
    if payload is None:
        return None
    if payload.get("schema_version") != LEGAL_HOLD_DELETION_GATE_SCHEMA_VERSION:
        raise LegalHoldAuthorityUnavailable("legal-hold deletion gate schema is unsupported")
    if payload.get("state") not in _GATE_STATES:
        raise LegalHoldAuthorityUnavailable("legal-hold deletion gate state is malformed")
    for key in ("uid", "kind", "token"):
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            raise LegalHoldAuthorityUnavailable(f"legal-hold deletion gate {key} is malformed")
    started_at = payload.get("started_at")
    if not isinstance(started_at, datetime) or started_at.tzinfo is None or started_at.utcoffset() is None:
        raise LegalHoldAuthorityUnavailable("legal-hold deletion gate timestamp is malformed")
    return payload


def _gate_blocks(gate: dict[str, Any] | None, now: datetime, *, kind: str | None = None) -> bool:
    """Block live work of a different kind; untyped fences stay conservative."""

    if gate is None or gate["state"] != "running":
        return False
    if gate["kind"] == _OBSOLETE_WRITER_GATE_KIND:
        return False
    return (now - gate["started_at"]).total_seconds() < GATE_STALE_AFTER_SECONDS


def _assert_hold_inactive(snapshot: Any) -> None:
    hold = _validated_hold(snapshot)
    if hold is not None and hold["active"] is True:
        raise LegalHoldActive("destructive deletion is blocked by an active legal hold")


def assert_account_deletion_permitted(uid: str, *, firestore_client: Any | None = None) -> None:
    """Point preflight for admission; irreversible work uses the transaction gate."""

    if not uid:
        raise LegalHoldAuthorityUnavailable("account deletion legal-hold lookup requires a uid")
    client = account_deletion_firestore_client(firestore_client=firestore_client)
    try:
        snapshot = _document(client, f"{LEGAL_HOLDS_COLLECTION}/{uid}").get()
        _assert_hold_inactive(snapshot)
    except (LegalHoldActive, LegalHoldAuthorityUnavailable):
        raise
    except Exception as exc:  # noqa: BLE001 - fail closed on authority outage
        raise LegalHoldAuthorityUnavailable("legal-hold authority unavailable") from exc


@transactional
def _place_legal_hold_transaction(
    transaction: Any,
    client: Any,
    uid: str,
    issuer: str,
    active: bool,
    now: datetime,
) -> None:
    hold_ref = _document(client, f"{LEGAL_HOLDS_COLLECTION}/{uid}")
    gate_ref = _document(client, f"{LEGAL_HOLD_DELETION_GATES_COLLECTION}/{uid}")
    account_ref = _document(client, f"account_deletions/{uid}")
    gate = _validated_gate(gate_ref.get(transaction=transaction))
    account = _snapshot_payload(account_ref.get(transaction=transaction), label="account deletion authority")
    if active and (_gate_blocks(gate, now) or (account is not None and account.get("wipe_status") == "running")):
        raise DestructiveOperationInProgress("legal hold cannot overtake deletion already in progress")
    transaction.set(
        hold_ref,
        {
            "schema_version": LEGAL_HOLD_SCHEMA_VERSION,
            "issuer": issuer,
            "active": active,
            "updated_at": now,
        },
        merge=True,
    )


def place_legal_hold(
    uid: str,
    *,
    issuer: str,
    active: bool = True,
    firestore_client: Any | None = None,
    now: datetime | None = None,
) -> None:
    """Server/admin-only legal-hold writer coordinated with destructive work."""

    if not uid or issuer not in _AUTHORIZED_ISSUERS:
        raise LegalHoldAuthorityUnavailable("legal-hold placement authority is invalid")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise LegalHoldAuthorityUnavailable("legal-hold placement timestamp must be timezone-aware")
    client = account_deletion_firestore_client(firestore_client=firestore_client)
    _place_legal_hold_transaction(client.transaction(), client, uid, issuer, active, current)


@transactional
def _acquire_destructive_operation_transaction(
    transaction: Any,
    client: Any,
    uid: str,
    kind: str,
    token: str,
    now: datetime,
) -> None:
    hold_ref = _document(client, f"{LEGAL_HOLDS_COLLECTION}/{uid}")
    gate_ref = _document(client, f"{LEGAL_HOLD_DELETION_GATES_COLLECTION}/{uid}")
    if kind == "external_data_write":
        account_ref = _document(client, f"account_deletions/{uid}")
        account_snapshot = account_ref.get(transaction=transaction)
        account_payload = _snapshot_payload(account_snapshot, label="account deletion authority")
        account_status = normalize_account_deletion_status(
            marker_exists=account_payload is not None,
            raw_status=account_payload.get("wipe_status") if account_payload is not None else None,
        )
        if account_deletion_blocks_access(account_status):
            raise DestructiveOperationInProgress("external data write blocked by account deletion")
    else:
        _assert_hold_inactive(hold_ref.get(transaction=transaction))
    gate = _validated_gate(gate_ref.get(transaction=transaction))
    if gate is not None and gate["state"] == "running":
        if gate["uid"] == uid and gate["kind"] == kind and gate["token"] == token:
            return
        if _gate_blocks(gate, now):
            # ANY fresh running gate blocks — including same-kind. A replacing
            # token would let a peer's check-then-delete chunks run after a
            # legal hold lands (the original holder keeps deleting post-takeover
            # and post-hold). Same-kind overlap waits like every other kind;
            # abandoned (stale) and obsolete-kind gates still allow takeover.
            raise DestructiveOperationInProgress("another destructive operation owns the account gate")
    transaction.set(
        gate_ref,
        {
            "schema_version": LEGAL_HOLD_DELETION_GATE_SCHEMA_VERSION,
            "uid": uid,
            "kind": kind,
            "token": token,
            "state": "running",
            "started_at": now,
            "finished_at": None,
        },
    )


def acquire_destructive_operation(
    uid: str,
    *,
    kind: str,
    token: str,
    firestore_client: Any | None = None,
    now: datetime | None = None,
) -> None:
    if not uid or not kind.strip() or not token.strip():
        raise LegalHoldAuthorityUnavailable("destructive operation identity is invalid")
    current = now or datetime.now(timezone.utc)
    client = account_deletion_firestore_client(firestore_client=firestore_client)
    _acquire_destructive_operation_transaction(client.transaction(), client, uid, kind, token, current)


@transactional
def _finish_destructive_operation_transaction(
    transaction: Any,
    client: Any,
    uid: str,
    kind: str,
    token: str,
    outcome: str,
    now: datetime,
) -> None:
    gate_ref = _document(client, f"{LEGAL_HOLD_DELETION_GATES_COLLECTION}/{uid}")
    gate = _validated_gate(gate_ref.get(transaction=transaction))
    if gate is None or gate["uid"] != uid or gate["kind"] != kind:
        raise LegalHoldAuthorityUnavailable("destructive operation gate ownership changed")
    if gate["token"] != token:
        # A same-kind peer owns this row now: only the stale-takeover path can
        # reach here, and the original holder must not exit reporting success
        # (or record its outcome on the peer's row). Preserve the peer's row
        # and fail the caller so it re-maps to the account-gate response.
        logger.warning("destructive operation finish aborted after same-kind takeover")
        raise DestructiveGateTakeover("destructive operation gate was taken over by a same-kind peer")
    if gate["state"] != "running":
        if gate["state"] == outcome:
            logger.info("destructive operation finish already recorded")
            return
        raise LegalHoldAuthorityUnavailable("destructive operation gate is already terminal")
    transaction.set(gate_ref, {**gate, "state": outcome, "finished_at": now})


def finish_destructive_operation(
    uid: str,
    *,
    kind: str,
    token: str,
    outcome: str,
    firestore_client: Any | None = None,
    now: datetime | None = None,
) -> None:
    if outcome not in {"failed", "completed"}:
        raise ValueError("destructive operation outcome must be failed or completed")
    client = account_deletion_firestore_client(firestore_client=firestore_client)
    _finish_destructive_operation_transaction(
        client.transaction(), client, uid, kind, token, outcome, now or datetime.now(timezone.utc)
    )


def assert_destructive_gate_still_ours(
    uid: str,
    kind: str,
    *,
    token: str | None = None,
    firestore_client: Any | None = None,
) -> None:
    """Re-read gate authority immediately before each destructive chunk.

    A caller that does not currently hold the gate in this context (legacy
    helpers, test seams, sync-bridge paths that never claimed it) has nothing
    to revalidate: this check is a takeover abort signal, not an authority
    grant, so absence of an active gate is a no-op rather than a failure.
    Callers that require held authority assert it separately with
    ``current_destructive_operation_token``.
    """
    if token is None:
        active = _ACTIVE_GATE.get()
        if active is None or active[0] != uid or active[1] != kind:
            return
        token = active[2]
    if not uid or not kind.strip() or not token.strip():
        raise LegalHoldAuthorityUnavailable("destructive operation identity is invalid")
    try:
        client = account_deletion_firestore_client(firestore_client=firestore_client)
        gate = _validated_gate(_document(client, f"{LEGAL_HOLD_DELETION_GATES_COLLECTION}/{uid}").get())
        if gate is None or gate["uid"] != uid:
            raise LegalHoldAuthorityUnavailable("destructive operation gate is missing or mismatched")
        if gate["kind"] != kind or gate["token"] != token or gate["state"] != "running":
            raise DestructiveGateTakeover("destructive operation gate was taken over or finished")
    except (DestructiveGateTakeover, LegalHoldAuthorityUnavailable):
        raise
    except Exception as exc:
        raise LegalHoldAuthorityUnavailable("destructive operation gate authority unavailable") from exc


def assert_destructive_operation_transaction(
    transaction: Any,
    client: Any,
    *,
    uid: str,
    kind: str,
    token: str,
) -> None:
    """Revalidate hold plus matching gate inside an irreversible transaction."""

    hold_ref = _document(client, f"{LEGAL_HOLDS_COLLECTION}/{uid}")
    gate_ref = _document(client, f"{LEGAL_HOLD_DELETION_GATES_COLLECTION}/{uid}")
    _assert_hold_inactive(hold_ref.get(transaction=transaction))
    gate = _validated_gate(gate_ref.get(transaction=transaction))
    if (
        gate is None
        or gate["state"] != "running"
        or gate["uid"] != uid
        or gate["kind"] != kind
        or gate["token"] != token
    ):
        raise LegalHoldAuthorityUnavailable("destructive operation transaction lacks gate authority")


def assert_no_destructive_operation_transaction(
    transaction: Any,
    client: Any,
    *,
    uid: str,
) -> None:
    """Fence non-destructive writes against an in-flight destructive operation.

    Reading the account gate in the same transaction as a canonical write
    prevents that write from committing between a privacy tombstone and its
    mandatory derived-data cleanup.  Completed/failed gates are historical
    receipts and do not block later writes; malformed authority fails closed.
    """

    gate_ref = _document(client, f"{LEGAL_HOLD_DELETION_GATES_COLLECTION}/{uid}")
    gate = _validated_gate(gate_ref.get(transaction=transaction))
    if _gate_blocks(gate, datetime.now(timezone.utc)):
        raise DestructiveOperationInProgress("canonical mutation blocked by destructive operation")


def dream_gate_contention_retry_allowed(
    uid: str,
    *,
    firestore_client: Any | None = None,
    now: datetime | None = None,
) -> bool:
    """Allow Dream to retry only around short destructive operations, never account deletion."""

    if not uid:
        return False
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        return False
    try:
        client = account_deletion_firestore_client(firestore_client=firestore_client)
        account_payload = _snapshot_payload(
            _document(client, f"account_deletions/{uid}").get(), label="account deletion authority"
        )
        status = normalize_account_deletion_status(
            marker_exists=account_payload is not None,
            raw_status=account_payload.get("wipe_status") if account_payload is not None else None,
        )
        if account_deletion_blocks_access(status):
            return False
        gate = _validated_gate(_document(client, f"{LEGAL_HOLD_DELETION_GATES_COLLECTION}/{uid}").get())
    except Exception as exc:  # noqa: BLE001 - failed authority reads must disable retry
        logger.warning("Dream gate retry authority read failed: %s", type(exc).__name__)
        return False
    if gate is None:
        return True
    if gate["uid"] != uid:
        return False
    if not _gate_blocks(gate, current):
        return True
    return gate["kind"] in _DREAM_RETRYABLE_GATE_KINDS


@contextmanager
def destructive_operation_gate(
    uid: str,
    *,
    kind: str = "explicit_memory_deletion",
    firestore_client: Any | None = None,
) -> Iterator[str]:
    """Acquire one account-wide gate, reusing it for nested deletion layers."""

    active = _ACTIVE_GATE.get()
    if active is not None:
        active_uid, active_kind, active_token = active
        if active_uid != uid or active_kind != kind:
            raise DestructiveOperationInProgress("nested destructive operation changed gate identity")
        yield active_token
        return
    token = uuid4().hex
    client = account_deletion_firestore_client(firestore_client=firestore_client)
    acquire_destructive_operation(uid, kind=kind, token=token, firestore_client=client)
    reset = _ACTIVE_GATE.set((uid, kind, token))
    try:
        yield token
    except BaseException:
        # Best-effort release: the original failure must never be masked by a
        # secondary authority error. An unreleased gate self-expires via the
        # staleness bound instead of blocking the account forever.
        try:
            finish_destructive_operation(uid, kind=kind, token=token, outcome="failed", firestore_client=client)
        except Exception:
            pass
        raise
    else:
        finish_destructive_operation(uid, kind=kind, token=token, outcome="completed", firestore_client=client)
    finally:
        _ACTIVE_GATE.reset(reset)


@contextmanager
def external_write_fence(
    uid: str, *, firestore_client: Any | None = None, transaction: Any | None = None
) -> Iterator[None]:
    """Fence one owner-scoped provider write against destructive operations.

    A supplied transaction reads and locks both authorities through its commit;
    nested writes reuse only that exact uid/client/transaction scope.
    Without a transaction this takes no lock and writes
    nothing: it performs two plain reads and raises when the account is being
    deleted or a live destructive operation owns the gate. Concurrent provider
    writes for one account therefore never contend with each other — the
    exclusive gate is reserved for genuinely destructive work. The residual
    race (a write already in flight when deletion begins) is closed by the
    deletion side, which verifies its purges left nothing behind and fails
    closed otherwise.
    """

    if not uid:
        raise LegalHoldAuthorityUnavailable("external write fence requires a uid")
    active = _EXTERNAL_TRANSACTION.get()
    if active is not None:
        if (
            active[0] != uid
            or (transaction is not None and active[1] is not transaction)
            or (firestore_client is not None and active[2] is not firestore_client)
        ):
            raise DestructiveOperationInProgress("nested external write changed transaction identity")
        yield None
        return
    client = account_deletion_firestore_client(firestore_client=firestore_client)
    kwargs = {'transaction': transaction} if transaction is not None else {}
    account_payload = _snapshot_payload(
        _document(client, f"account_deletions/{uid}").get(**kwargs), label="account deletion authority"
    )
    account_status = normalize_account_deletion_status(
        marker_exists=account_payload is not None,
        raw_status=account_payload.get("wipe_status") if account_payload is not None else None,
    )
    if account_deletion_blocks_access(account_status):
        raise DestructiveOperationInProgress("external data write blocked by account deletion")
    gate = _validated_gate(_document(client, f"{LEGAL_HOLD_DELETION_GATES_COLLECTION}/{uid}").get(**kwargs))
    if _gate_blocks(gate, datetime.now(timezone.utc)):
        raise DestructiveOperationInProgress("external data write blocked by destructive operation")
    # Transactional reads hold the authorities through provider upload and
    # manifest commit. Nested storage gates reuse this exact synchronous scope;
    # ordinary nontransactional fences retain their fresh-read behavior.
    reset = _EXTERNAL_TRANSACTION.set((uid, transaction, client)) if transaction is not None else None
    try:
        yield None
    finally:
        if reset is not None:
            _EXTERNAL_TRANSACTION.reset(reset)


def current_destructive_operation_token(uid: str, *, kind: str) -> str:
    active = _ACTIVE_GATE.get()
    if active is None or active[0] != uid or active[1] != kind:
        raise LegalHoldAuthorityUnavailable("destructive operation gate is not active in this context")
    return active[2]


__all__ = [
    "LEGAL_HOLDS_COLLECTION",
    "LEGAL_HOLD_DELETION_GATES_COLLECTION",
    "LEGAL_HOLD_SCHEMA_VERSION",
    "LEGAL_HOLD_DELETION_GATE_SCHEMA_VERSION",
    "DestructiveOperationInProgress",
    "DestructiveGateTakeover",
    "LegalHoldActive",
    "LegalHoldAuthorityUnavailable",
    "acquire_destructive_operation",
    "assert_account_deletion_permitted",
    "assert_destructive_operation_transaction",
    "assert_destructive_gate_still_ours",
    "assert_no_destructive_operation_transaction",
    "current_destructive_operation_token",
    "destructive_operation_gate",
    "external_write_fence",
    "finish_destructive_operation",
    "place_legal_hold",
]
