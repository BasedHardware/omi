#!/usr/bin/env python3
"""Prove Dream idle parking never loses a wakeup, on the Firestore emulator only.

The idle-skip lever deletes an owner's ``dream_due`` row when no dirty work is
queued. A concurrent product write (``mark_dirty``) commits a non-transactional
batch: dirty doc + state score increment + due row. The parking transactions
read the state doc, so a mark_dirty landing between their read and commit must
abort and retry them. The invariant checked after every interleaving:

    dirty work queued  =>  a dream_due row exists.

1. ``park_if_idle``: the write is injected inside the transaction, after the
   state read and the dirty count.
2. ``acquire(skip_idle=True)``: the same injection inside admission.
3. Control: with no concurrent write, an idle owner is parked (no due row).

Scope: the emulator serializes with pessimistic locks, including the
transaction's dirty-count query, so a concurrent write waits for the park to
commit and then re-creates the due row. This proves the invariant on the real
SDK, but it cannot show that the state-doc read is necessary: an unfenced park
also passes here. The fence is defense in depth against a backend that does not
lock aggregation ranges.
"""

from __future__ import annotations

# ruff: noqa: E402 -- emulator safety/env bootstrapping must precede backend imports.

import os
import sys
import threading
from pathlib import Path
from typing import Any

PROJECT_ID = os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "demo-omi-isolated-tests")
os.environ.setdefault("GCLOUD_PROJECT", PROJECT_ID)
os.environ.setdefault("ENCRYPTION_SECRET", "omi_dream_park_race_emulator_key_32_bytes")
os.environ.setdefault("DREAM_AGENT_ENABLED", "true")
os.environ.setdefault("DREAM_AGENT_ELIGIBILITY", "all")
os.environ.setdefault("REVIEW_SURFACE_MODE", "on")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from google.api_core.exceptions import Aborted  # noqa: E402
from google.cloud import firestore  # noqa: E402

from config.dream_agent import Caps  # noqa: E402
from database import dream_store  # noqa: E402

TRIALS = 12


def _assert_emulator_only() -> None:
    host = (os.environ.get("FIRESTORE_EMULATOR_HOST") or "").strip()
    if not host:
        raise RuntimeError("FIRESTORE_EMULATOR_HOST is required; run through Firebase emulators:exec")
    hostname = host.rsplit(":", 1)[0].strip("[]").lower()
    if hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError(f"refusing non-loopback Firestore emulator host: {hostname}")
    if not PROJECT_ID.startswith("demo-"):
        raise RuntimeError(f"refusing non-demo Firestore project: {PROJECT_ID}")


def _reset(db: Any, uid: str) -> None:
    state = db.collection("dream_users").document(uid)
    for snapshot in state.collection("dirty").stream():
        snapshot.reference.delete()
    state.set({"score": 0})
    db.collection("users").document(uid).set({})
    db.collection("dream_due").document(uid).set({"due_at": firestore.SERVER_TIMESTAMP})


def _invariant(db: Any, uid: str, label: str) -> None:
    dirty = list(db.collection("dream_users").document(uid).collection("dirty").limit(1).stream())
    due = db.collection("dream_due").document(uid).get().exists
    if dirty and not due:
        raise AssertionError(f"{label}: dirty work is queued but the dream_due row was deleted (lost wakeup)")


class _InjectWrite:
    """Wrap dirty_count: on its first transactional call, commit a real mark_dirty from another thread."""

    def __init__(self, db: Any, uid: str, ref_id: str, hold: float):
        self.db, self.uid, self.ref_id, self.hold = db, uid, ref_id, hold
        self.outcome = 'not_run'
        self.original = dream_store.dirty_count
        self.fired = False
        self.thread: threading.Thread | None = None
        self.errors: list[BaseException] = []

    def _write(self) -> None:
        try:
            if not dream_store.mark_dirty(self.uid, [("conversations", self.ref_id)], firestore_client=self.db):
                raise AssertionError("mark_dirty refused the synthetic owner; the proof would be vacuous")
            self.outcome = 'landed'
        except Aborted:
            # The emulator serializes with pessimistic locks: a write held past the lock
            # timeout aborts and writes nothing, which is also a safe serialization.
            self.outcome = 'aborted'
        except BaseException as error:  # surfaced after the race
            self.errors.append(error)

    def __call__(self, uid: str, *, transaction: Any = None, firestore_client: Any = None) -> int:
        count = self.original(uid, transaction=transaction, firestore_client=firestore_client)
        if transaction is not None and not self.fired:
            self.fired = True
            self.thread = threading.Thread(target=self._write, daemon=True)
            self.thread.start()
            # The emulator may hold the write behind the transaction's locks; give it
            # a window to land first, then let the transaction try to commit.
            self.thread.join(timeout=self.hold)
        return count

    def finish(self) -> None:
        if self.thread is not None:
            self.thread.join(timeout=30)
            if self.thread.is_alive():
                raise AssertionError("concurrent mark_dirty never completed")
        if self.errors:
            raise self.errors[0]
        if not self.fired:
            raise AssertionError("the injected write never ran; the proof would be vacuous")


HOLDS = (0.0, 0.05, 0.2, 1.0)
OUTCOMES: dict[str, int] = {}


def _race(db: Any, uid: str, trial: int, label: str, operation: Any) -> None:
    _reset(db, uid)
    inject = _InjectWrite(db, uid, f"race-{label}-{trial}", HOLDS[trial % len(HOLDS)])
    dream_store.dirty_count = inject
    try:
        operation()
    finally:
        dream_store.dirty_count = inject.original
    inject.finish()
    OUTCOMES[f'{label}:{inject.outcome}'] = OUTCOMES.get(f'{label}:{inject.outcome}', 0) + 1
    _invariant(db, uid, f"{label} trial {trial}")


def _prove_park_if_idle_race(db: Any, uid: str) -> None:
    for trial in range(TRIALS):
        _race(db, uid, trial, "park_if_idle", lambda: dream_store.park_if_idle(uid, firestore_client=db))


def _prove_acquire_skip_idle_race(db: Any, uid: str) -> None:
    for trial in range(TRIALS):
        _race(
            db,
            uid,
            trial,
            "acquire_skip_idle",
            lambda: dream_store.acquire(uid, Caps(passes=1000), firestore_client=db, skip_idle=True),
        )


def _prove_idle_owner_is_parked(db: Any, uid: str) -> None:
    _reset(db, uid)
    assert dream_store.park_if_idle(uid, firestore_client=db) is True, "an idle owner must be parked"
    assert not db.collection("dream_due").document(uid).get().exists, "parking must delete the due row"


def main() -> int:
    _assert_emulator_only()
    db = firestore.Client(project=PROJECT_ID)
    # Product code paths read the default client (dream_control, eligibility); point them at the emulator too.
    dream_store.get_firestore_client = lambda: db
    uids = [f"dream-park-race-proof-{suffix}" for suffix in ("park", "acquire", "control")]
    try:
        _prove_park_if_idle_race(db, uids[0])
        _prove_acquire_skip_idle_race(db, uids[1])
        _prove_idle_owner_is_parked(db, uids[2])
        for label in ('park_if_idle', 'acquire_skip_idle'):
            if not OUTCOMES.get(f'{label}:landed'):
                raise AssertionError(f'{label}: no injected write landed; the race was never exercised ({OUTCOMES})')
    finally:
        for uid in uids:
            state = db.collection("dream_users").document(uid)
            for snapshot in state.collection("dirty").stream():
                snapshot.reference.delete()
            state.delete()
            db.collection("dream_due").document(uid).delete()
            db.collection("users").document(uid).delete()
    print(f"PASS: Dream idle parking keeps every wakeup across {2 * TRIALS} injected races {OUTCOMES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
