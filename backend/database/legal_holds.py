"""Server-owned legal-hold and destructive-operation coordination.

Every supported destructive path and the legal-hold writer contend on the
same per-account gate document. This gives the system a real linearization
point: either an active hold is committed first and deletion cannot start, or
deletion owns the gate and a later hold placement is rejected until its
outcome is known. User-facing routes never write either authority document.
"""

from __future__ import annotations

import logging
import random
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterator
from uuid import uuid4

from google.api_core.exceptions import Aborted
from google.cloud.firestore_v1 import transactional

from database import rpc_deadline
from database.account_deletion_marker import account_deletion_firestore_client
from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status
from database.fsr_read_cache import cache_writer
from database import privacy_check_metrics as metrics
from database.privacy_negative_cache import decide

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
# Backoff between acquisition attempts while a same-kind peer holds the gate.
_GATE_WAIT_BACKOFF_SECONDS = (0.1, 0.2, 0.4, 0.5)
# Bounded destructive units (background purges): body RPC deadline, total hold incl.
# release, and the gate document's own expiry, all from the winning attempt's start.
# The expiry leaves 2 s for clock skew and stays far inside the 20 s foreground wait.
UNIT_BODY_SECONDS = 5.0
UNIT_HOLD_SECONDS = 8.0
UNIT_EXPIRY_SECONDS = 10.0
UNIT_RELEASE_RETRY_SECONDS = 0.2
# Settling a remote erasure whose outcome is unknown, and clearing its mark, after the body deadline.
UNIT_REMOTE_RESOLVE_ATTEMPTS = 2
UNIT_REMOTE_RESOLVE_SECONDS = 3.0
UNIT_REMOTE_CLEAR_SECONDS = 3.0
# A gate held this long by an unknown remote outcome is settled by the next run.
UNIT_REMOTE_STUCK_SECONDS = 60.0
_gate_wait_sleep = time.sleep
_gate_wait_clock = time.monotonic
_RELEASE_CONTENTION_ATTEMPTS = 5


def _gate_wait_jitter() -> float:
    return random.uniform(0.0, 0.1)


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
    expires_at = payload.get("expires_at")
    if expires_at is not None and (
        not isinstance(expires_at, datetime) or expires_at.tzinfo is None or expires_at.utcoffset() is None
    ):
        raise LegalHoldAuthorityUnavailable("legal-hold deletion gate expiry is malformed")
    return payload


def _gate_blocks(gate: dict[str, Any] | None, now: datetime, *, kind: str | None = None) -> bool:
    """Block live work of a different kind; untyped fences stay conservative."""

    if gate is None or gate["state"] != "running":
        return False
    if gate["kind"] == _OBSOLETE_WRITER_GATE_KIND:
        return False
    age_seconds = (now - gate["started_at"]).total_seconds()
    if gate.get("remote_inflight"):
        # An erasure whose outcome is unknown may still land: no expiry and no
        # stale bound ever transfers authority; only settlement clears it.
        if age_seconds >= GATE_STALE_AFTER_SECONDS:
            logger.error(
                "event=destructive_gate_remote_unresolved uid=%s kind=%s age_seconds=%d",
                gate["uid"],
                gate["kind"],
                int(age_seconds),
            )
        return True
    expires_at = gate.get("expires_at")
    if expires_at is not None and now >= expires_at:
        # Past a bounded unit's expiry its Firestore erasures are fenced by token, so a successor is safe.
        return False
    return age_seconds < GATE_STALE_AFTER_SECONDS


def _gate_owned_by_this_context(gate: dict[str, Any] | None, uid: str) -> bool:
    """The running gate is the one this request acquired: its own cleanup is not a rival writer."""

    active = _ACTIVE_GATE.get()
    return gate is not None and gate["uid"] == uid and active == (uid, gate["kind"], gate["token"])


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


@cache_writer('legal_hold_fence_cache')
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
    expires_at: datetime | None = None,
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
            **({"expires_at": expires_at} if expires_at is not None else {}),
        },
    )


@cache_writer('legal_hold_fence_cache')
def acquire_destructive_operation(
    uid: str,
    *,
    kind: str,
    token: str,
    firestore_client: Any | None = None,
    now: datetime | None = None,
    expires_at: datetime | None = None,
    max_attempts: int | None = None,
) -> None:
    if not uid or not kind.strip() or not token.strip():
        raise LegalHoldAuthorityUnavailable("destructive operation identity is invalid")
    current = now or datetime.now(timezone.utc)
    client = account_deletion_firestore_client(firestore_client=firestore_client)
    transaction = client.transaction(max_attempts=max_attempts) if max_attempts else client.transaction()
    _acquire_destructive_operation_transaction(transaction, client, uid, kind, token, current, expires_at)


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


@cache_writer('legal_hold_fence_cache')
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


def _blocking_gate_kind(client: Any, uid: str) -> str | None:
    """Kind of the fresh running gate for ``uid``; None when free; "" when unreadable."""

    try:
        gate = _validated_gate(_document(client, f"{LEGAL_HOLD_DELETION_GATES_COLLECTION}/{uid}").get())
    except Exception:  # noqa: BLE001 - an unreadable gate never earns a wait
        return ""
    if gate is None or not _gate_blocks(gate, datetime.now(timezone.utc)):
        return None
    return gate["kind"] if gate["uid"] == uid else ""


def _is_transaction_contention(error: BaseException) -> bool:
    if isinstance(error, Aborted):
        return True
    return isinstance(error, ValueError) and str(error).startswith('Failed to commit transaction')


def same_kind_gate_running(uid: str, *, kind: str, firestore_client: Any | None = None) -> bool:
    """Lock-free read: a fresh running gate of ``kind`` holds the account (False if free, other, unreadable)."""

    return _blocking_gate_kind(account_deletion_firestore_client(firestore_client=firestore_client), uid) == kind


def gate_busy_with_peer(error: BaseException, uid: str, *, kind: str, firestore_client: Any | None = None) -> bool:
    """Whether a failed acquisition of ``kind`` only lost to a same-kind peer (or contention on the gate).

    Another kind (account wipe, retention, audio deletion), a legal hold, or an
    unreadable gate is never "busy with a peer".
    """

    if not isinstance(error, DestructiveOperationInProgress) and not _is_transaction_contention(error):
        return False
    client = account_deletion_firestore_client(firestore_client=firestore_client)
    return _blocking_gate_kind(client, uid) in {None, kind}


def _acquire_with_same_kind_wait(
    uid: str,
    *,
    kind: str,
    token: str,
    client: Any,
    wait_seconds: float,
    expires_in: float | None = None,
    max_attempts: int | None = None,
) -> float:
    """Acquire, waiting out a running gate of the same kind for at most ``wait_seconds``.

    Same-account deletes arrive in bursts (multi-select, client retries) and each
    holds the gate for seconds, so a peer of the same kind is waited for instead
    of answered with an immediate 409. Any other kind (account wipe, retention,
    audio deletion), a legal hold, or an unreadable gate still fails at once.
    """

    deadline = _gate_wait_clock() + max(0.0, wait_seconds)
    waits = 0
    while True:
        # A bounded unit measures its deadlines from the start of the attempt that wins.
        attempt_started = rpc_deadline.now()
        try:
            if expires_in is None and max_attempts:
                # One transaction attempt makes contention an immediate answer, not SDK backoff (1 s, 2 s, 4 s...).
                acquire_destructive_operation(
                    uid, kind=kind, token=token, firestore_client=client, max_attempts=max_attempts
                )
            elif expires_in is None:
                acquire_destructive_operation(uid, kind=kind, token=token, firestore_client=client)
            else:
                attempt_wall = datetime.now(timezone.utc)
                acquire_destructive_operation(
                    uid,
                    kind=kind,
                    token=token,
                    firestore_client=client,
                    now=attempt_wall,
                    expires_at=attempt_wall + timedelta(seconds=expires_in),
                )
        except (Aborted, ValueError) as error:
            # A same-account burst can exhaust the transaction's own retries on the
            # gate document; that is contention, not a verdict, so it shares the wait.
            remaining = deadline - _gate_wait_clock()
            if not _is_transaction_contention(error) or remaining <= 0:
                raise
            _gate_wait_sleep(
                min(_GATE_WAIT_BACKOFF_SECONDS[min(waits, len(_GATE_WAIT_BACKOFF_SECONDS) - 1)], remaining)
            )
            waits += 1
            continue
        except DestructiveOperationInProgress:
            # Wait on plain (lock-free) reads: a transactional retry per poll would lock the
            # gate document and delay the holder's own release write.
            while True:
                remaining = deadline - _gate_wait_clock()
                blocking_kind = _blocking_gate_kind(client, uid) if remaining > 0 else ""
                if blocking_kind not in {None, kind}:
                    if waits:
                        logger.warning("destructive operation gate wait exhausted kind=%s waits=%d", kind, waits)
                    raise
                if blocking_kind is None:
                    # Released: retry the transactional acquire, de-synchronised from other waiters.
                    jitter = _gate_wait_jitter()
                    if jitter > 0:
                        _gate_wait_sleep(min(jitter, max(remaining, 0.0)))
                    break
                backoff = _GATE_WAIT_BACKOFF_SECONDS[min(waits, len(_GATE_WAIT_BACKOFF_SECONDS) - 1)]
                _gate_wait_sleep(min(backoff, remaining))
                waits += 1
            continue
        if waits:
            logger.info("destructive operation gate acquired after waiting kind=%s waits=%d", kind, waits)
        return attempt_started


@contextmanager
def destructive_operation_gate(
    uid: str,
    *,
    kind: str = "explicit_memory_deletion",
    firestore_client: Any | None = None,
    wait_seconds: float = 0.0,
    max_attempts: int | None = None,
) -> Iterator[str]:
    """Acquire one account-wide gate, reusing it for nested deletion layers.

    ``wait_seconds`` bounds how long acquisition waits behind a running gate of
    the same kind; zero keeps the fail-fast contract for every other caller.
    ``max_attempts`` caps the acquisition transaction's own contention retries.
    """

    active = _ACTIVE_GATE.get()
    if active is not None:
        active_uid, active_kind, active_token = active
        if active_uid != uid or active_kind != kind:
            raise DestructiveOperationInProgress("nested destructive operation changed gate identity")
        yield active_token
        return
    token = uuid4().hex
    client = account_deletion_firestore_client(firestore_client=firestore_client)
    _acquire_with_same_kind_wait(
        uid, kind=kind, token=token, client=client, wait_seconds=wait_seconds, max_attempts=max_attempts
    )
    reset = _ACTIVE_GATE.set((uid, kind, token))
    try:
        yield token
    except BaseException:
        # Best-effort release: the original failure must never be masked by a
        # secondary authority error. An unreleased gate self-expires via the
        # staleness bound instead of blocking the account forever.
        try:
            _finish_through_contention(uid, kind, token, "failed", client)
        except Exception:
            pass
        raise
    else:
        _finish_through_contention(uid, kind, token, "completed", client)
    finally:
        _ACTIVE_GATE.reset(reset)


def _finish_through_contention(uid: str, kind: str, token: str, outcome: str, client: Any) -> None:
    """Release the gate; a release lost to waiter contention would otherwise pin it until stale."""
    for attempt in range(_RELEASE_CONTENTION_ATTEMPTS):
        try:
            finish_destructive_operation(uid, kind=kind, token=token, outcome=outcome, firestore_client=client)
            return
        except (Aborted, ValueError) as error:
            if not _is_transaction_contention(error) or attempt + 1 == _RELEASE_CONTENTION_ATTEMPTS:
                raise
            _gate_wait_sleep(0.05 * (attempt + 1) + _gate_wait_jitter())


@transactional
def _mark_remote_erasure_transaction(
    transaction: Any,
    client: Any,
    uid: str,
    kind: str,
    token: str,
    inflight: bool,
    now: datetime,
    target: str | None = None,
) -> None:
    hold_ref = _document(client, f"{LEGAL_HOLDS_COLLECTION}/{uid}")
    gate_ref = _document(client, f"{LEGAL_HOLD_DELETION_GATES_COLLECTION}/{uid}")
    if inflight:
        _assert_hold_inactive(hold_ref.get(transaction=transaction))
    gate = _validated_gate(gate_ref.get(transaction=transaction))
    if gate is None or gate["state"] != "running" or gate["uid"] != uid or gate["kind"] != kind:
        raise DestructiveGateTakeover("remote erasure no longer owns the account gate")
    if gate["token"] != token:
        raise DestructiveGateTakeover("remote erasure no longer owns the account gate")
    if inflight and gate.get("expires_at") is not None and now >= gate["expires_at"]:
        raise DestructiveGateTakeover("unit gate expired before its remote erasure was sent")
    transaction.set(
        gate_ref,
        {
            **gate,
            "remote_inflight": inflight,
            "remote_inflight_at": now if inflight else None,
            "remote_target": target if inflight else None,
        },
    )


def mark_remote_erasure(
    uid: str, *, kind: str, token: str, inflight: bool, firestore_client: Any, target: str | None = None
) -> None:
    """Record (or clear) that this unit has an irreversible remote erasure whose outcome is unknown."""
    _mark_remote_erasure_transaction(
        firestore_client.transaction(), firestore_client, uid, kind, token, inflight, datetime.now(timezone.utc), target
    )


def stuck_remote_erasure(uid: str, *, kind: str, firestore_client: Any) -> tuple[str, str] | None:
    """(token, target) of a unit gate left held by a remote erasure whose outcome stayed unknown."""
    gate = _validated_gate(_document(firestore_client, f"{LEGAL_HOLD_DELETION_GATES_COLLECTION}/{uid}").get())
    if gate is None or gate["state"] != "running" or gate["kind"] != kind or not gate.get("remote_inflight"):
        return None
    since = gate.get("remote_inflight_at")
    target = gate.get("remote_target")
    if not isinstance(since, datetime) or not isinstance(target, str) or not target:
        return None
    if (datetime.now(timezone.utc) - since).total_seconds() < UNIT_REMOTE_STUCK_SECONDS:
        return None
    return gate["token"], target


@transactional
def _settle_remote_erasure_transaction(
    transaction: Any, client: Any, uid: str, kind: str, token: str, now: datetime
) -> bool:
    gate_ref = _document(client, f"{LEGAL_HOLD_DELETION_GATES_COLLECTION}/{uid}")
    gate = _validated_gate(gate_ref.get(transaction=transaction))
    if gate is None or gate["state"] != "running" or gate["kind"] != kind or gate["token"] != token:
        return False
    if not gate.get("remote_inflight"):
        return False
    transaction.set(
        gate_ref,
        {**gate, "state": "failed", "finished_at": now, "remote_inflight": False, "remote_target": None},
    )
    return True


def settle_stuck_remote_erasure(uid: str, *, kind: str, token: str, firestore_client: Any) -> bool:
    """Release a stuck unit gate once its remote erasure is proven settled (same gate token, still in flight)."""
    return _settle_remote_erasure_transaction(
        firestore_client.transaction(), firestore_client, uid, kind, token, datetime.now(timezone.utc)
    )


def remote_outcome_known(error: BaseException) -> bool:
    """Whether a failed remote call provably did not leave a request that could still apply.

    Any HTTP response ends that request's server-side processing, and a call we
    refused to send never started. Only a transport failure without a response
    (timeout, reset, refused connection) is unknown.
    """
    if isinstance(error, rpc_deadline.RpcDeadlineExceeded):
        return True  # refused before sending
    if getattr(error, "response", None) is not None and isinstance(getattr(error, "code", None), int):
        return True  # google.api_core HTTP error: the server answered
    return not isinstance(error, (TimeoutError, ConnectionError, OSError)) and not _is_transport_error(error)


def settles_unknown_erasure(call: Callable[[], Any]) -> bool:
    """Re-issue the same generation-pinned delete; True only if it proves the earlier one can no longer act.

    A return means the target is gone now (deleted, or already absent); a 412
    means the pinned generation is no longer the live object. Either way the
    earlier request, pinned to that generation, can only be a no-op. Any other
    outcome (503, 403, timeout, refusal to send) says nothing about the earlier
    request, so the erasure stays unresolved and the gate stays held.
    """
    try:
        call()
        return True
    except BaseException as error:  # noqa: BLE001 - only a precondition miss proves absence
        return getattr(error, "code", None) == 412


def _is_transport_error(error: BaseException) -> bool:
    names = {klass.__name__ for klass in type(error).__mro__}
    return bool(names & {"RequestException", "TransportError", "Timeout", "ConnectionError", "ReadTimeout"})


class UnitAuthority:
    """The account-gate authority of one bounded unit, for the destructive work done under it."""

    def __init__(self, uid: str, kind: str, token: str, client: Any, ceiling: float | None):
        self.uid, self.kind, self.token, self.client = uid, kind, token, client
        self._ceiling = ceiling
        self.unresolved = False

    def fence(self, transaction: Any) -> None:
        """Re-prove, in the caller's erasing transaction, no active hold and this unit's gate token."""
        assert_destructive_operation_transaction(
            transaction, self.client, uid=self.uid, kind=self.kind, token=self.token
        )

    def _after_call(self, seconds: float) -> Any:
        at = rpc_deadline.now() + seconds
        return rpc_deadline.override(at if self._ceiling is None else min(at, self._ceiling))

    def remote(self, call: Callable[[], Any], *, target: str | None = None) -> Any:
        """Run one irreversible remote erasure without letting the gate change hands until its outcome is known.

        The in-flight mark commits before the request is sent and keeps the gate
        blocking (expiry ignored) until a definitive outcome clears it. An outcome
        that stays unknown leaves the gate held: fail closed.
        """
        mark_remote_erasure(
            self.uid, kind=self.kind, token=self.token, inflight=True, firestore_client=self.client, target=target
        )
        try:
            result = call()
        except BaseException as error:
            if not remote_outcome_known(error) and not self._resolve(call):
                self.unresolved = True
                logger.error("remote erasure outcome unknown; account gate stays held: %s", type(error).__name__)
                raise
            self._clear()
            raise
        self._clear()
        return result

    def _resolve(self, call: Callable[[], Any]) -> bool:
        for _ in range(UNIT_REMOTE_RESOLVE_ATTEMPTS):
            with self._after_call(UNIT_REMOTE_RESOLVE_SECONDS):
                if settles_unknown_erasure(call):
                    return True
        return False

    def _clear(self) -> None:
        with self._after_call(UNIT_REMOTE_CLEAR_SECONDS):
            for attempt in range(_RELEASE_CONTENTION_ATTEMPTS):
                try:
                    mark_remote_erasure(
                        self.uid, kind=self.kind, token=self.token, inflight=False, firestore_client=self.client
                    )
                    return
                except Exception as error:  # noqa: BLE001 - an uncleared mark only keeps the gate held
                    if attempt + 1 == _RELEASE_CONTENTION_ATTEMPTS:
                        self.unresolved = True
                        logger.error(
                            "remote erasure mark not cleared; account gate stays held: %s", type(error).__name__
                        )
                        return
                    _gate_wait_sleep(UNIT_RELEASE_RETRY_SECONDS)


@contextmanager
def bounded_destructive_unit(
    uid: str,
    *,
    kind: str = "explicit_memory_deletion",
    wait_seconds: float = 0.0,
    firestore_client: Any | None = None,
) -> Iterator[UnitAuthority]:
    """Hold the account gate for one short destructive unit.

    Authority, not a timer, decides safety: every Firestore erasure re-proves
    this unit's token and the absence of a hold inside its own transaction
    (``UnitAuthority.fence``), and a remote erasure keeps the gate held until its
    outcome is known (``UnitAuthority.remote``). The timers only bound latency:
    body RPCs on deadline-bound clients get ``UNIT_BODY_SECONDS`` from the
    winning acquisition attempt, the release the rest of ``UNIT_HOLD_SECONDS``,
    and the gate document expires at ``UNIT_EXPIRY_SECONDS`` unless a remote
    erasure is in flight, so a lost release cannot keep a foreground delete
    waiting past its budget.
    """

    if _ACTIVE_GATE.get() is not None:
        raise DestructiveOperationInProgress("bounded unit cannot nest inside another destructive gate")
    token = uuid4().hex
    client = rpc_deadline.bind_firestore_client(account_deletion_firestore_client(firestore_client=firestore_client))
    ceiling = rpc_deadline.current()
    started = _acquire_with_same_kind_wait(
        uid, kind=kind, token=token, client=client, wait_seconds=wait_seconds, expires_in=UNIT_EXPIRY_SECONDS
    )
    authority = UnitAuthority(uid, kind, token, client, ceiling)
    reset = _ACTIVE_GATE.set((uid, kind, token))
    outcome = "completed"
    try:
        with rpc_deadline.rpc_deadline(started + UNIT_BODY_SECONDS):
            yield authority
    except BaseException:
        outcome = "failed"
        raise
    finally:
        _ACTIVE_GATE.reset(reset)
        if not authority.unresolved:
            _release_bounded_unit(uid, kind, token, outcome, client, started + UNIT_HOLD_SECONDS)


def _release_bounded_unit(uid: str, kind: str, token: str, outcome: str, client: Any, deadline: float) -> None:
    with rpc_deadline.rpc_deadline(deadline):
        while True:
            try:
                finish_destructive_operation(uid, kind=kind, token=token, outcome=outcome, firestore_client=client)
                return
            except (DestructiveGateTakeover, LegalHoldAuthorityUnavailable):
                return  # Expired and taken over, or already terminal: nothing left to release.
            except Exception as error:  # noqa: BLE001 - the gate's expiry is the backstop
                left = rpc_deadline.remaining()
                if left is None or left <= UNIT_RELEASE_RETRY_SECONDS:
                    logger.warning("bounded unit release failed; gate expires on its own: %s", type(error).__name__)
                    return
                _gate_wait_sleep(UNIT_RELEASE_RETRY_SECONDS)


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

    metrics.called('external')
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
        metrics.decision('external', uid=uid)
        yield None
        return
    client = account_deletion_firestore_client(firestore_client=firestore_client)
    kwargs = {'transaction': transaction} if transaction is not None else {}
    reusable = False

    def live():
        nonlocal reusable
        account_payload = _snapshot_payload(
            metrics.read_snapshot('external', _document(client, f"account_deletions/{uid}"), uid=uid, **kwargs),
            label="account deletion authority",
        )
        account_status = normalize_account_deletion_status(
            marker_exists=account_payload is not None,
            raw_status=account_payload.get("wipe_status") if account_payload is not None else None,
        )
        if account_deletion_blocks_access(account_status):
            raise DestructiveOperationInProgress("external data write blocked by account deletion")
        gate = _validated_gate(
            metrics.read_snapshot(
                'external', _document(client, f"{LEGAL_HOLD_DELETION_GATES_COLLECTION}/{uid}"), uid=uid, **kwargs
            )
        )
        if _gate_blocks(gate, datetime.now(timezone.utc)) and not _gate_owned_by_this_context(gate, uid):
            raise DestructiveOperationInProgress("external data write blocked by destructive operation")
        # A backwards clock adjustment can change a stale-running verdict
        # without changing the writer token. Only timeless clears are reusable;
        # a gate-owner pass is running, so it is never cached for other writers.
        reusable = gate is None or gate['state'] != 'running'
        return True

    if transaction is not None:
        # Always enroll both authority reads in the caller's conflict set.
        try:
            live()
        except DestructiveOperationInProgress:
            metrics.decision('external', 'destructive_operation', uid=uid)
            raise
        except Exception:
            metrics.decision('external', 'authority_unavailable', uid=uid)
            raise
        metrics.decision('external', uid=uid)
    else:
        decide(
            'external',
            uid,
            client,
            'external',
            live,
            'legal_hold_fence_cache',
            blocked=(DestructiveOperationInProgress,),
            reuse_allowed=lambda: reusable,
        )
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
    "UnitAuthority",
    "bounded_destructive_unit",
    "mark_remote_erasure",
    "remote_outcome_known",
    "settles_unknown_erasure",
    "settle_stuck_remote_erasure",
    "stuck_remote_erasure",
    "assert_destructive_operation_transaction",
    "assert_destructive_gate_still_ours",
    "assert_no_destructive_operation_transaction",
    "current_destructive_operation_token",
    "destructive_operation_gate",
    "external_write_fence",
    "finish_destructive_operation",
    "gate_busy_with_peer",
    "same_kind_gate_running",
    "place_legal_hold",
]
