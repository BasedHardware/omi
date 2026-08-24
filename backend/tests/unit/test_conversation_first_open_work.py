from __future__ import annotations

from datetime import datetime, timedelta, timezone

import database.conversations as conversations_db
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore


def _store() -> tuple[StrictFirestore, tuple[str, ...]]:
    path = ("users", "owner", "conversations", "conversation")
    return StrictFirestore({path: {"id": "conversation"}}), path


def test_first_open_obligation_claim_completion_is_idempotent() -> None:
    store, path = _store()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    assert conversations_db.initialize_first_open_work("owner", "conversation", firestore_client=store)
    token = conversations_db.claim_first_open_work("owner", "conversation", now=now, firestore_client=store)

    assert token is not None
    assert (
        conversations_db.claim_first_open_work(
            "owner", "conversation", now=now + timedelta(seconds=1), firestore_client=store
        )
        is None
    )
    assert conversations_db.finish_first_open_work(
        "owner", "conversation", token, succeeded=True, firestore_client=store
    )
    assert (
        conversations_db.claim_first_open_work(
            "owner", "conversation", now=now + timedelta(hours=1), firestore_client=store
        )
        is None
    )
    assert store.rows[path]["jit_first_open"]["state"] == "complete"


def test_failed_and_expired_first_open_claims_are_retryable_and_fenced() -> None:
    store, path = _store()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conversations_db.initialize_first_open_work("owner", "conversation", firestore_client=store)
    first = conversations_db.claim_first_open_work(
        "owner", "conversation", lease_seconds=30, now=now, firestore_client=store
    )
    assert first is not None
    assert not conversations_db.finish_first_open_work(
        "owner", "conversation", "wrong", succeeded=True, firestore_client=store
    )

    expired_retry = conversations_db.claim_first_open_work(
        "owner", "conversation", now=now + timedelta(seconds=31), firestore_client=store
    )
    assert expired_retry is not None and expired_retry != first
    assert not conversations_db.finish_first_open_work(
        "owner", "conversation", first, succeeded=True, firestore_client=store
    )
    assert conversations_db.finish_first_open_work(
        "owner", "conversation", expired_retry, succeeded=False, firestore_client=store
    )
    assert store.rows[path]["jit_first_open"]["state"] == "pending"
    assert store.rows[path]["jit_first_open"]["attempt"] == 2
