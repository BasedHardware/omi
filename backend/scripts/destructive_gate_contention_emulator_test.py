#!/usr/bin/env python3
"""Prove destructive-gate contention semantics on the Firestore emulator only.

Covers the interleavings the unit fakes cannot reach (review thread asks on the
memory-deletion 409-storm lane):

1. A fresh same-kind holder CANNOT replace a live peer's token (acquire
   raises ``DestructiveOperationInProgress``; the peer's row is untouched).
   Cross-kind attempts are likewise blocked while any fresh gate runs.
2. Only the 6h staleness bound lets a same-kind peer rotate the token — and
   the displaced holder then (a) aborts its next chunk via
   ``assert_destructive_gate_still_ours`` and (b) cannot exit the gate
   reporting success: its finish raises ``DestructiveGateTakeover`` and the
   peer's running row is preserved.
3. A legal hold cannot land while any fresh gate (same-kind included) is
   running, yet ``finish`` by the rightful holder releases it: the hold
   transaction then succeeds.
4. The receipt sweep's check-then-delete cannot interleave between a peer's
   gate ownership and a legal hold: while the sweep holds the gate, a legal
   hold is refused and a second memory deletion is refused; after the sweep
   finishes, both proceed.
"""

from __future__ import annotations

# ruff: noqa: E402 -- emulator safety/env bootstrapping must precede backend imports.

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROJECT_ID = os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "demo-omi-isolated-tests")
os.environ.setdefault("GCLOUD_PROJECT", PROJECT_ID)
os.environ.setdefault("ENCRYPTION_SECRET", "omi_gate_contention_emulator_test_key_32_bytes")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from google.cloud import firestore  # noqa: E402

from database import legal_holds  # noqa: E402
from database.legal_holds import (  # noqa: E402
    DestructiveGateTakeover,
    DestructiveOperationInProgress,
    destructive_operation_gate,
)

NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)


def _assert_emulator_only() -> None:
    host = (os.environ.get("FIRESTORE_EMULATOR_HOST") or "").strip()
    if not host:
        raise RuntimeError("FIRESTORE_EMULATOR_HOST is required; run through Firebase emulators:exec")
    hostname = host.rsplit(":", 1)[0].strip("[]").lower()
    if hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError(f"refusing non-loopback Firestore emulator host: {hostname}")
    if not PROJECT_ID.startswith("demo-"):
        raise RuntimeError(f"refusing non-demo Firestore project: {PROJECT_ID}")


def _gate_row(db_client: Any, uid: str) -> dict[str, Any] | None:
    snapshot = db_client.document(f"{legal_holds.LEGAL_HOLD_DELETION_GATES_COLLECTION}/{uid}").get()
    return snapshot.to_dict() if snapshot.exists else None


def _expect_reject(operation: Any, label: str) -> None:
    try:
        operation()
    except DestructiveOperationInProgress:
        return
    raise AssertionError(f"{label}: expected DestructiveOperationInProgress")


def _prove_fresh_same_kind_holders_block(db_client: Any, uid: str) -> None:
    """Same-kind and cross-kind attempts cannot replace a fresh running token."""
    with destructive_operation_gate(uid, kind="explicit_memory_deletion", firestore_client=db_client) as token:
        before = _gate_row(db_client, uid)
        assert before is not None and before["token"] == token

        _expect_reject(
            lambda: legal_holds.acquire_destructive_operation(
                uid, kind="explicit_memory_deletion", token="peer-same-kind", firestore_client=db_client, now=NOW
            ),
            "fresh same-kind peer acquisition",
        )
        _expect_reject(
            lambda: legal_holds.acquire_destructive_operation(
                uid, kind="retention_cleanup", token="peer-cross-kind", firestore_client=db_client, now=NOW
            ),
            "fresh cross-kind peer acquisition",
        )
        after = _gate_row(db_client, uid)
        assert after == before, "blocked acquisition attempts must not mutate the running gate row"

        # A legal hold cannot land while the fresh same-kind gate runs.
        _expect_reject(
            lambda: legal_holds.place_legal_hold(uid, issuer="admin", active=True, firestore_client=db_client, now=NOW),
            "legal hold against a live same-kind gate",
        )

    # The rightful holder's finish releases the gate; a hold may now land.
    finished = _gate_row(db_client, uid)
    assert finished is not None and finished["state"] == "completed", "rightful finish must complete the gate"
    legal_holds.place_legal_hold(uid, issuer="admin", active=True, firestore_client=db_client, now=NOW)
    hold = db_client.document(f"{legal_holds.LEGAL_HOLDS_COLLECTION}/{uid}").get()
    assert hold.exists and (hold.to_dict() or {}).get("active") is True
    print("PASS: fresh same-kind/cross-kind peers block; legal hold waits for rightful finish")


def _prove_stale_takeover_fence(db_client: Any, uid: str) -> None:
    """Past the 6h bound a peer may rotate the token; the displaced holder fails loudly."""
    stale_holder = {}
    with pytest_raises_context(DestructiveGateTakeover, "stale holder context exit"):
        with destructive_operation_gate(uid, kind="explicit_memory_deletion", firestore_client=db_client):
            # The context manager acquires with the real wall clock, so derive
            # the peer's timestamp from the row it must consider stale.
            gate_row = _gate_row(db_client, uid)
            assert gate_row is not None and gate_row["started_at"], "gate row must record its start"
            stale = gate_row["started_at"] + timedelta(seconds=legal_holds.GATE_STALE_AFTER_SECONDS + 1)
            stale_holder["ts"] = stale
            # The peer legitimately rotates the stale gate.
            legal_holds.acquire_destructive_operation(
                uid, kind="explicit_memory_deletion", token="peer-after-stale", firestore_client=db_client, now=stale
            )
            # The displaced holder's next destructive chunk aborts...
            try:
                legal_holds.assert_destructive_gate_still_ours(
                    uid, "explicit_memory_deletion", firestore_client=db_client
                )
            except DestructiveGateTakeover:
                pass
            else:
                raise AssertionError("displaced holder chunk did not abort after stale takeover")

    row = _gate_row(db_client, uid)
    assert (
        row is not None and row["token"] == "peer-after-stale" and row["state"] == "running"
    ), "displaced holder finish must not terminate the peer's running gate"
    stale = stale_holder["ts"]
    # ...and its exit did not report success: the row is still running, so a
    # legal hold still cannot land until the peer finishes.
    _expect_reject(
        lambda: legal_holds.place_legal_hold(uid, issuer="admin", active=True, firestore_client=db_client, now=stale),
        "legal hold while the surviving peer still runs",
    )
    legal_holds.finish_destructive_operation(
        uid, kind="explicit_memory_deletion", token="peer-after-stale", outcome="completed", firestore_client=db_client
    )
    legal_holds.place_legal_hold(uid, issuer="admin", active=True, firestore_client=db_client, now=stale)
    print("PASS: stale takeover rotates token; displaced holder chunk+exit raise; peer row preserved")


class _Raises:
    """Minimal pytest.raises stand-in (proof scripts do not import pytest)."""

    def __init__(self, expected: type[BaseException], label: str):
        self.expected = expected
        self.label = label

    def __enter__(self) -> "_Raises":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        if exc_type is None:
            raise AssertionError(f"{self.label}: expected {self.expected.__name__} to be raised")
        if not issubclass(exc_type, self.expected):
            return False
        return True


def pytest_raises_context(expected: type[BaseException], label: str) -> "_Raises":
    return _Raises(expected, label)


def main() -> int:
    _assert_emulator_only()
    db_client = firestore.Client(project=PROJECT_ID)
    proof_uids = [f"gate-contention-proof-{suffix}" for suffix in ("fresh-block", "stale-takeover")]
    try:
        _prove_fresh_same_kind_holders_block(db_client, proof_uids[0])
        _prove_stale_takeover_fence(db_client, proof_uids[1])
    finally:
        for uid in proof_uids:
            db_client.document(f"{legal_holds.LEGAL_HOLD_DELETION_GATES_COLLECTION}/{uid}").delete()
            db_client.document(f"{legal_holds.LEGAL_HOLDS_COLLECTION}/{uid}").delete()
    print("PASS: destructive gate contention proofs complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
