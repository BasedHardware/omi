from __future__ import annotations

from datetime import datetime, timedelta, timezone

import database.conversations as conversations_db
import database.goals as goals_db
from google.cloud import firestore
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
    for effect in conversations_db.FIRST_OPEN_EFFECTS:
        assert conversations_db.complete_first_open_effect(
            "owner", "conversation", token, effect, firestore_client=store
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


def test_first_open_persists_and_fences_account_and_source_generation() -> None:
    store, path = _store()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert conversations_db.initialize_first_open_work("owner", "conversation", firestore_client=store)
    state = store.rows[path]["jit_first_open"]
    assert (state["account_generation"], state["source_generation"]) == (3, 7)

    control = store.rows[("users", "owner", "memory_state", "apply_control")]
    control["source_generation"] = 8
    assert conversations_db.claim_first_open_work("owner", "conversation", now=now, firestore_client=store) is None


def test_account_deletion_suspends_claim_and_fences_effect_commit() -> None:
    store, path = _store()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert conversations_db.initialize_first_open_work("owner", "conversation", firestore_client=store)
    token = conversations_db.claim_first_open_work("owner", "conversation", now=now, firestore_client=store)
    assert token is not None

    store.rows[("account_deletions", "owner")] = {"wipe_status": "queued"}
    assert not conversations_db.first_open_effect_is_authorized(
        "owner", "conversation", token, "folder_assignment", firestore_client=store
    )
    assert not conversations_db.commit_first_open_conversation_patch(
        "owner",
        "conversation",
        token,
        "folder_assignment",
        {"folder_id": "must-not-commit"},
        firestore_client=store,
    )
    assert "folder_id" not in store.rows[path]


def test_conversation_effect_output_commits_before_separate_completion_receipt() -> None:
    store, path = _store()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert conversations_db.initialize_first_open_work("owner", "conversation", firestore_client=store)
    token = conversations_db.claim_first_open_work("owner", "conversation", now=now, firestore_client=store)
    assert token is not None

    assert conversations_db.commit_first_open_conversation_patch(
        "owner", "conversation", token, "folder_assignment", {"folder_id": "folder"}, firestore_client=store
    )
    assert store.rows[path]["folder_id"] == "folder"
    assert store.rows[path]["jit_first_open"]["effects"]["folder_assignment"]["state"] == "pending"
    assert conversations_db.complete_first_open_effect(
        "owner", "conversation", token, "folder_assignment", firestore_client=store
    )


def test_app_usage_attribution_is_idempotent_and_deletion_fenced() -> None:
    store, path = _store()
    store.rows[("plugins_data", "app")] = {"id": "app"}
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert conversations_db.initialize_first_open_work("owner", "conversation", firestore_client=store)
    token = conversations_db.claim_first_open_work("owner", "conversation", now=now, firestore_client=store)
    assert token is not None

    assert conversations_db.commit_first_open_app_result(
        "owner",
        "conversation",
        token,
        "app",
        {"apps_results": [{"app_id": "app", "content": "result"}]},
        firestore_client=store,
    )
    assert conversations_db.commit_first_open_app_usage(
        "owner", "conversation", token, "app", "memory_created_prompt", firestore_client=store
    )
    usage_path = ("plugins", "app", "usage_history", "conversation")
    assert store.rows[usage_path]["uid"] == "owner"
    receipt = store.rows[path]["jit_first_open"]["effects"]["app_fanout"]["app_receipts"]["app"]
    assert receipt == {"result_persisted": True, "usage_persisted": True}

    writes_before_retry = sum(len(transaction.sets) + len(transaction.updates) for transaction in store.transactions)
    assert conversations_db.commit_first_open_app_usage(
        "owner", "conversation", token, "app", "memory_created_prompt", firestore_client=store
    )
    writes_after_retry = sum(len(transaction.sets) + len(transaction.updates) for transaction in store.transactions)
    assert writes_after_retry == writes_before_retry

    store.rows[("account_deletions", "owner")] = {"wipe_status": "running"}
    assert not conversations_db.commit_first_open_app_usage(
        "owner", "conversation", token, "other-app", "memory_created_prompt", firestore_client=store
    )
    assert ("plugins", "other-app", "usage_history", "conversation") not in store.rows


def test_plugin_deletion_after_usage_does_not_block_no_write_completion_retry() -> None:
    store, _path = _store()
    plugin_path = ("plugins_data", "app")
    store.rows[plugin_path] = {"id": "app"}
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert conversations_db.initialize_first_open_work("owner", "conversation", firestore_client=store)
    token = conversations_db.claim_first_open_work("owner", "conversation", now=now, firestore_client=store)
    assert token is not None
    assert conversations_db.commit_first_open_app_result(
        "owner",
        "conversation",
        token,
        "app",
        {"apps_results": [{"app_id": "app", "content": "paid result"}]},
        firestore_client=store,
    )
    assert conversations_db.commit_first_open_app_usage(
        "owner", "conversation", token, "app", "memory_created_prompt", firestore_client=store
    )

    del store.rows[plugin_path]
    writes_before_retry = sum(len(transaction.sets) + len(transaction.updates) for transaction in store.transactions)
    assert conversations_db.commit_first_open_app_usage(
        "owner", "conversation", token, "app", "memory_created_prompt", firestore_client=store
    )
    writes_after_retry = sum(len(transaction.sets) + len(transaction.updates) for transaction in store.transactions)
    assert writes_after_retry == writes_before_retry
    assert conversations_db.complete_first_open_effect(
        "owner", "conversation", token, "app_fanout", firestore_client=store
    )


def test_app_result_cannot_complete_until_usage_receipt_is_durable() -> None:
    store, path = _store()
    store.rows[("plugins_data", "app")] = {"id": "app"}
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert conversations_db.initialize_first_open_work("owner", "conversation", firestore_client=store)
    token = conversations_db.claim_first_open_work("owner", "conversation", now=now, firestore_client=store)
    assert token is not None

    assert conversations_db.commit_first_open_app_result(
        "owner",
        "conversation",
        token,
        "app",
        {"apps_results": [{"app_id": "app", "content": "paid result"}]},
        firestore_client=store,
    )
    assert not conversations_db.complete_first_open_effect(
        "owner", "conversation", token, "app_fanout", firestore_client=store
    )
    assert store.rows[path]["jit_first_open"]["effects"]["app_fanout"]["state"] == "pending"

    assert conversations_db.commit_first_open_app_usage(
        "owner", "conversation", token, "app", "memory_created_prompt", firestore_client=store
    )
    assert conversations_db.complete_first_open_effect(
        "owner", "conversation", token, "app_fanout", firestore_client=store
    )


def test_plugin_deletion_after_app_result_cannot_recreate_usage_child() -> None:
    store, _path = _store()
    plugin_path = ("plugins_data", "app")
    store.rows[plugin_path] = {"id": "app"}
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert conversations_db.initialize_first_open_work("owner", "conversation", firestore_client=store)
    token = conversations_db.claim_first_open_work("owner", "conversation", now=now, firestore_client=store)
    assert token is not None
    assert conversations_db.commit_first_open_app_result(
        "owner",
        "conversation",
        token,
        "app",
        {"apps_results": [{"app_id": "app", "content": "paid result"}]},
        firestore_client=store,
    )

    del store.rows[plugin_path]
    assert not conversations_db.commit_first_open_app_usage(
        "owner", "conversation", token, "app", "memory_created_prompt", firestore_client=store
    )
    assert ("plugins", "app", "usage_history", "conversation") not in store.rows


def test_account_recreation_generation_fences_old_in_flight_lease() -> None:
    store, path = _store()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert conversations_db.initialize_first_open_work("owner", "conversation", firestore_client=store)
    token = conversations_db.claim_first_open_work("owner", "conversation", now=now, firestore_client=store)
    assert token is not None

    control = store.rows[("users", "owner", "memory_state", "apply_control")]
    control["account_generation"] = 4
    control["source_generation"] = 1
    assert not conversations_db.first_open_effect_is_authorized(
        "owner", "conversation", token, "app_fanout", firestore_client=store
    )
    assert not conversations_db.complete_first_open_effect(
        "owner", "conversation", token, "app_fanout", firestore_client=store
    )
    assert not conversations_db.finish_first_open_work(
        "owner", "conversation", token, succeeded=True, firestore_client=store
    )


def test_goal_effect_commit_uses_same_account_deletion_and_generation_fence() -> None:
    store, _path = _store()

    @firestore.transactional
    def validate(transaction) -> None:
        goals_db.validate_first_open_authority(
            transaction,
            uid="owner",
            account_generation=3,
            source_generation=7,
            firestore_client=store,
        )

    validate(store.transaction())
    store.rows[("account_deletions", "owner")] = {"wipe_status": "running"}
    try:
        validate(store.transaction())
    except goals_db.GoalConflictError as error:
        assert "authority unavailable" in str(error)
    else:
        raise AssertionError("goal mutation must fail closed during account deletion")


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


def test_first_open_retry_preserves_completed_effect_receipts() -> None:
    store, path = _store()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conversations_db.initialize_first_open_work("owner", "conversation", firestore_client=store)
    first = conversations_db.claim_first_open_work("owner", "conversation", now=now, firestore_client=store)
    assert first is not None
    assert conversations_db.complete_first_open_effect(
        "owner", "conversation", first, "folder_assignment", firestore_client=store
    )

    # Simulate a process crash after the folder side effect and receipt.
    assert conversations_db.finish_first_open_work(
        "owner", "conversation", first, succeeded=False, firestore_client=store
    )
    state = store.rows[path]["jit_first_open"]
    assert state["state"] == "pending"
    assert state["effects"]["folder_assignment"]["state"] == "complete"

    retry = conversations_db.claim_first_open_work(
        "owner", "conversation", now=now + timedelta(minutes=1), firestore_client=store
    )
    assert retry is not None
    assert not conversations_db.complete_first_open_effect(
        "owner", "conversation", first, "goal_progress", firestore_client=store
    )
    for effect in ("goal_progress", "app_fanout"):
        assert conversations_db.complete_first_open_effect(
            "owner", "conversation", retry, effect, firestore_client=store
        )
    assert conversations_db.finish_first_open_work(
        "owner", "conversation", retry, succeeded=True, firestore_client=store
    )
    assert store.rows[path]["jit_first_open"]["state"] == "complete"
