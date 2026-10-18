from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import database.conversations as conversations_db
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore


def _store() -> tuple[StrictFirestore, tuple[str, ...]]:
    path = ("users", "owner", "conversations", "conversation")
    return (
        StrictFirestore(
            {
                ("users", "owner"): {"uid": "owner"},
                ("users", "owner", "memory_state", "apply_control"): {
                    "uid": "owner",
                    "head_commit_id": "head0",
                    "account_generation": 3,
                    "source_generation": 7,
                },
                path: {"id": "conversation"},
            }
        ),
        path,
    )


def test_invalid_identifiers_fail_closed_without_exceptions() -> None:
    store, _ = _store()
    invalid_ids = ["", "  ", "owner/traversal", "bad\0id", "..", ".", " leading", "trailing "]

    for bad_id in invalid_ids:
        # initialize_first_open_work
        assert not conversations_db.initialize_first_open_work(bad_id, "conversation", firestore_client=store)
        assert not conversations_db.initialize_first_open_work("owner", bad_id, firestore_client=store)

        # claim_first_open_work
        assert conversations_db.claim_first_open_work(bad_id, "conversation", firestore_client=store) is None
        assert conversations_db.claim_first_open_work("owner", bad_id, firestore_client=store) is None

        # first_open_effect_is_authorized
        assert not conversations_db.first_open_effect_is_authorized(
            bad_id, "conversation", "tok", "folder_assignment", firestore_client=store
        )

        # complete_first_open_effect
        assert not conversations_db.complete_first_open_effect(
            bad_id, "conversation", "tok", "folder_assignment", firestore_client=store
        )

        # commit_first_open_folder_count
        assert not conversations_db.commit_first_open_folder_count(
            "owner", "conversation", "tok", bad_id, firestore_client=store
        )

        # commit_first_open_app_usage
        assert not conversations_db.commit_first_open_app_usage(
            "owner", "conversation", "tok", bad_id, "usage", firestore_client=store
        )

        # commit_first_open_app_result
        assert not conversations_db.commit_first_open_app_result(
            "owner", "conversation", "tok", bad_id, {"res": 1}, firestore_client=store
        )


def test_lease_seconds_clamping_and_non_finite_handling() -> None:
    store, path = _store()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conversations_db.initialize_first_open_work("owner", "conversation", firestore_client=store)

    # 1. Negative or sub-30s clamped to at least 30s
    tok1 = conversations_db.claim_first_open_work(
        "owner", "conversation", lease_seconds=5, now=now, firestore_client=store
    )
    assert tok1 is not None
    state1 = store.rows[path]["jit_first_open"]
    assert state1["lease_expires_at"] == now + timedelta(seconds=30)

    # 2. Huge duration clamped to 86400s
    now2 = now + timedelta(seconds=35)
    tok2 = conversations_db.claim_first_open_work(
        "owner", "conversation", lease_seconds=999999, now=now2, firestore_client=store
    )
    assert tok2 is not None
    state2 = store.rows[path]["jit_first_open"]
    assert state2["lease_expires_at"] == now2 + timedelta(seconds=86400)

    # 3. Non-finite floats (NaN, Inf) safely default to 300s without timedelta crashing
    now3 = now2 + timedelta(seconds=86405)
    tok3 = conversations_db.claim_first_open_work(
        "owner", "conversation", lease_seconds=float("nan"), now=now3, firestore_client=store
    )
    assert tok3 is not None
    state3 = store.rows[path]["jit_first_open"]
    assert state3["lease_expires_at"] == now3 + timedelta(seconds=300)

    now4 = now3 + timedelta(seconds=305)
    tok4 = conversations_db.claim_first_open_work(
        "owner", "conversation", lease_seconds=float("inf"), now=now4, firestore_client=store
    )
    assert tok4 is not None
    state4 = store.rows[path]["jit_first_open"]
    assert state4["lease_expires_at"] == now4 + timedelta(seconds=300)


def test_commit_first_open_folder_count_guards_aggregation_query() -> None:
    store, _ = _store()

    # When query build or execution fails, fail closed cleanly without unhandled exception
    mock_spec = MagicMock()
    mock_spec.build.side_effect = RuntimeError("Index building in progress")
    with patch(
        "database.first_open_obligations.FIRST_OPEN_FOLDER_CONVERSATION_COUNT_QUERY",
        mock_spec,
    ):
        result = conversations_db.commit_first_open_folder_count(
            "owner", "conversation", "tok", "f123", firestore_client=store
        )
        assert result is False


def test_complete_first_open_effect_rejects_unsupported_effect_cleanly() -> None:
    store, _ = _store()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conversations_db.initialize_first_open_work("owner", "conversation", firestore_client=store)
    token = conversations_db.claim_first_open_work("owner", "conversation", now=now, firestore_client=store)
    assert token is not None

    # Unsupported effect should fail closed returning False, not raise ValueError or KeyError
    assert not conversations_db.complete_first_open_effect(
        "owner", "conversation", token, "unsupported_retired_effect", firestore_client=store
    )


def test_database_error_boundary_catches_transaction_failures() -> None:
    store, _ = _store()

    with patch(
        "database.first_open_obligations.run_transactional",
        side_effect=RuntimeError("Firestore connection dropped"),
    ):
        assert not conversations_db.initialize_first_open_work("owner", "conversation", firestore_client=store)
        assert conversations_db.claim_first_open_work("owner", "conversation", firestore_client=store) is None
        assert not conversations_db.first_open_effect_is_authorized(
            "owner", "conversation", "tok", "folder_assignment", firestore_client=store
        )
        assert not conversations_db.complete_first_open_effect(
            "owner", "conversation", "tok", "folder_assignment", firestore_client=store
        )
        assert not conversations_db.finish_first_open_work(
            "owner", "conversation", "tok", succeeded=True, firestore_client=store
        )
