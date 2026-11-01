"""Outbox interface: durable rows woken by Cloud Tasks or claimed by pull (contract (b)).

The row is the source of truth; a task is only a wake. Implementations:

- Firestore: ``database/outbox_firestore.py`` (lane 9). ``OutboxKind.ENRICHMENT`` stays row-compatible with
  ``sync_reprocess_outbox`` (collection, document id ``reprocess.key(...)``, field names, ``sr-`` prefix).
- Postgres: ``database/jobstore/outbox_pg.py`` (lane 12), conformance-tested only in this window.

Both must pass ``tests/integration/test_outbox_conformance.py`` (lane 12). ``Outcome`` and ``Claim`` live
here; ``utils/workers/consumer.py`` re-exports them. This module imports nothing from ``utils.workers``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal, Mapping, Protocol

if TYPE_CHECKING:
    from database.batch_pipeline_store import Transaction


class OutboxKind(StrEnum):
    ENRICHMENT = 'enrichment'  # row-compatible with sync_reprocess_outbox
    PROVIDER_STT = 'provider_stt'
    CAP_HOLD_REDRIVE = 'cap_hold_redrive'  # reserved; not built in this window
    PROJECT_CONVERSATION = 'project_conversation'  # A4, reserved; not built in this window


class Outcome(StrEnum):
    DONE = 'done'  # work committed; row acked
    DEFERRED = 'deferred'  # not due / policy defer; row re-armed with a new wake token
    RETRY = 'retry'  # expected transient condition; lease released; caller retries (HTTP 409)
    DISCARDED = 'discarded'  # privacy fence / deleted target / superseded; row closed
    STALE = 'stale'  # token no longer current; no-op
    BUSY = 'busy'  # another live lease holds the row; no-op (watchdog keeps custody)


@dataclass(frozen=True)
class Claim:
    kind: OutboxKind
    row_id: str  # Outbox row id (Firestore doc id; Postgres id as str)
    lease_token: str  # fencing token minted at claim; required on every later call
    wake_token: str  # the Cloud Tasks task-name token that delivered this claim ('' for pull)
    attempt: int  # 1-based delivery attempt for this row
    lease_until: float  # epoch seconds
    owner_id: str
    payload: Mapping[str, Any]  # content-free, <= 4 KiB serialized
    policy_id: str | None  # from the unit's policy snapshot, contract (c)


@dataclass(frozen=True)
class EnqueueResult:
    row_id: str
    coalesced: bool  # True when dedupe_key already had an open row (version bumped)
    wake_token: str | None  # wake for this row; with tx= the caller calls Outbox.wake(row_id, wake_token) after
    # commit; without tx the outbox already created it. None when no wake is needed.


@dataclass(frozen=True)
class SweepCounts:
    rewoken: int
    expired_leases: int
    discarded: int
    errors: int


class Outbox(Protocol):
    kind: OutboxKind

    def enqueue(
        self,
        dedupe_key: str,
        owner_id: str,
        payload: Mapping[str, Any],
        available_at: float,
        *,
        policy_id: str | None = None,
        coalesce: Literal['min', 'max'] = 'max',
        tx: 'Transaction | None' = None,
        now: float,
    ) -> EnqueueResult:
        """Durable before wake. Without ``tx`` the outbox commits the row, then creates its wake. With ``tx`` the
        row is written in the caller's transaction and the caller calls ``wake(row_id, wake_token)`` after commit.

        ``policy_id`` is copied onto the row and surfaces as ``Claim.policy_id``. ``coalesce`` picks the
        ``available_at`` rule when ``dedupe_key`` already has an open row: 'min' for first-summary deadlines,
        'max' for settle. With ``tx`` the row is written in the caller's ``Store`` transaction.
        """
        ...

    def claim(self, n: int, lease_seconds: float, *, now: float) -> list[Claim]: ...

    def claim_key(self, row_id: str, wake_token: str, lease_seconds: float, *, now: float) -> Claim | Outcome:
        """A wrong wake token returns ``Outcome.STALE``; a live foreign lease returns ``Outcome.BUSY``; a row that is
        not yet due is re-armed (new wake created by the outbox) and returns ``Outcome.DEFERRED``; a privacy-fenced
        or deleted row is closed and returns ``Outcome.DISCARDED``."""
        ...

    def heartbeat(self, claim: Claim, lease_seconds: float, *, now: float) -> bool: ...

    def ack(self, claim: Claim, reason: str, *, now: float) -> bool: ...

    def defer(self, claim: Claim, available_at: float, reason: str, *, now: float) -> str | None:
        """Re-arm the row and create its new wake; returns the new wake token (old deliveries become STALE)."""
        ...

    def release(self, claim: Claim, reason: str, *, now: float) -> bool:
        """RETRY: lease_until=0, keep the wake token."""
        ...

    def wake(self, row_id: str, wake_token: str) -> None:
        """Create the wake task for ``(row_id, wake_token)``; idempotent on that pair (named-task 409 = success).

        Called by transactional enqueuers after commit. A failed create leaves the row for ``sweep``.
        """
        ...

    def sweep(self, *, now: float, limit: int = 100) -> SweepCounts: ...


def outbox_for(kind: OutboxKind) -> Outbox:
    """Select the outbox implementation for ``kind``.

    Reads the table-group mode 'outbox' from A's ``BATCH_JOBSTORE_MODE``; in this window it always returns the
    Firestore implementation (lane 9). The mode for a unit is pinned in its policy snapshot (``jobstore_mode``).
    """
    from database.outbox_firestore import firestore_outbox

    return firestore_outbox(kind)
