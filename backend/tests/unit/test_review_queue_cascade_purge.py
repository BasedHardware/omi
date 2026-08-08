"""Review queue cascade purge when canonical memories are tombstoned or superseded."""

from __future__ import annotations

import os
import types
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import load_module_fresh, stub_modules
from tests.store_fakes import FakeDocumentStore

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

_BACKEND = Path(__file__).resolve().parents[2]
_CREATED_AT = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def review_queue():
    """Load a fresh database.review_queue against stubbed database deps.

    review_queue binds ``db`` and sibling database modules at import time
    (``from ._client import db``, ``from database import memories``, ...), so the
    fakes must be active before the module is exec'd. This is the sanctioned
    Tier-2 "fake must precede import" case -- see backend/docs/test_isolation.md
    and testing/import_isolation.load_module_fresh.
    """
    ledger_stub = types.ModuleType("database.memory_ledger")
    ledger_stub.add_fact = lambda fact: {"type": "add_fact", "fact": fact}
    ledger_stub.supersede_fact = lambda existing_id, **kwargs: {
        "type": "supersede_fact",
        "fact_id": existing_id,
        **kwargs,
    }
    ledger_stub.retract_fact = lambda fact_id, **kwargs: {"type": "retract_fact", "fact_id": fact_id, **kwargs}
    ledger_stub.refine_fact = lambda fact_id, arg_changes: {
        "type": "refine_fact",
        "fact_id": fact_id,
        "arg_changes": arg_changes,
    }
    ledger_stub.append_commit = MagicMock()

    fakes = {
        "database._client": MagicMock(),
        "database.memories": MagicMock(),
        "database.memory_ledger": ledger_stub,
        "database.short_term_memories": MagicMock(),
    }
    with stub_modules(fakes):
        module = load_module_fresh(
            "database.review_queue",
            os.path.join(str(_BACKEND), "database", "review_queue.py"),
        )
        yield module


def _seed_queue(store, uid: str, items: dict) -> None:
    base = f"users/{uid}/memory_review_queue"
    for doc_id, data in items.items():
        payload = dict(data)
        payload.setdefault("created_at", _CREATED_AT)
        store[f"{base}/{doc_id}"] = payload


def test_purge_drops_pending_items_referencing_deleted_memory(monkeypatch, review_queue):
    uid = "uid-review-purge"
    store = {}
    _seed_queue(
        store,
        uid,
        {
            "review-hit-fact": {
                "review_id": "review-hit-fact",
                "fact_id": "mem_deleted",
                "conflict_with": ["mem_other"],
                "candidate": {"id": "mem_deleted", "content": "deleted private fact"},
                "permitted_uses": ["answers_with_disclaimer"],
                "status": "pending",
            },
            "review-hit-conflict": {
                "review_id": "review-hit-conflict",
                "fact_id": "mem_survivor",
                "conflict_with": ["mem_deleted"],
                "status": "pending",
            },
            "review-unrelated": {
                "review_id": "review-unrelated",
                "fact_id": "mem_alive",
                "conflict_with": ["mem_other"],
                "referenced_memory_ids": ["mem_alive", "mem_other"],
                "status": "pending",
            },
            "review-resolved": {
                "review_id": "review-resolved",
                "fact_id": "mem_deleted",
                "conflict_with": [],
                "status": "accepted",
            },
        },
    )

    fake = FakeDocumentStore(backing=store)
    monkeypatch.setattr(review_queue, "_store", lambda: fake)

    purged = review_queue.purge_stale_review_conflicts_for_memories(uid, ["mem_deleted"])

    assert sorted(purged) == ["review-hit-conflict", "review-hit-fact", "review-resolved"]
    dropped = store[f"users/{uid}/memory_review_queue/review-hit-fact"]
    assert dropped["status"] == "tombstoned"
    assert dropped["candidate"] == {"id": "mem_deleted"}
    assert dropped["permitted_uses"] == []
    assert store[f"users/{uid}/memory_review_queue/review-unrelated"]["status"] == "pending"
    resolved = store[f"users/{uid}/memory_review_queue/review-resolved"]
    assert resolved["status"] == "tombstoned"
    assert resolved["previous_status"] == "accepted"
    assert resolved["candidate"] == {}
    assert resolved["permitted_uses"] == []

    # Idempotent replay: the already-redacted guard must skip the write, so the stored audit fields
    # and the row's last-write revision both stay put even when a different reason is supplied.
    resolved_path = f"users/{uid}/memory_review_queue/review-resolved"
    original_audit = {key: resolved[key] for key in ("previous_status", "reason", "resolved_at", "updated_at")}
    revision_before = fake.get(resolved_path).updated_at

    replayed = review_queue.purge_stale_review_conflicts_for_memories(
        uid,
        ["mem_deleted"],
        reason="different_replay_reason",
    )

    assert sorted(replayed) == ["review-hit-conflict", "review-hit-fact", "review-resolved"]
    assert fake.get(resolved_path).updated_at == revision_before
    resolved_after = store[resolved_path]
    assert {
        key: resolved_after[key] for key in ("previous_status", "reason", "resolved_at", "updated_at")
    } == original_audit


def test_purge_drops_every_matching_item_across_many_target_ids(monkeypatch, review_queue):
    uid = "uid-review-purge-pages"
    store = {}
    first_target = "mem-000"
    last_target = "mem-030"
    items = {
        f"review-{index}": {
            "review_id": f"review-{index}",
            "fact_id": first_target,
            "conflict_with": [],
            "referenced_memory_ids": [first_target],
            "candidate": {"id": first_target, "content": f"private-{index}"},
            "permitted_uses": ["answers_with_disclaimer"],
            "status": "pending",
        }
        for index in range(5)
    }
    items["review-cross"] = {
        "review_id": "review-cross",
        "fact_id": first_target,
        "conflict_with": [last_target],
        "referenced_memory_ids": [first_target, last_target],
        "candidate": {"id": first_target, "content": "cross-chunk private"},
        "permitted_uses": ["answers_with_disclaimer"],
        "status": "pending",
    }
    items["review-last"] = {
        "review_id": "review-last",
        "fact_id": last_target,
        "conflict_with": [],
        "referenced_memory_ids": [last_target],
        "candidate": {"id": last_target, "content": "last private"},
        "permitted_uses": ["answers_with_disclaimer"],
        "status": "pending",
    }
    _seed_queue(store, uid, items)
    monkeypatch.setattr(review_queue, "_store", lambda: FakeDocumentStore(backing=store))

    purged = review_queue.purge_stale_review_conflicts_for_memories(
        uid,
        [f"mem-{index:03d}" for index in range(31)],
    )

    # Every row referencing any target id -- whether through ``fact_id`` or ``conflict_with``,
    # including the cross-referencing row -- is tombstoned exactly once in one neutral scan.
    assert purged == sorted(items)
    for review_id in items:
        assert store[f"users/{uid}/memory_review_queue/{review_id}"]["status"] == "tombstoned"


def test_failed_review_purge_cannot_expose_tombstoned_canonical_candidate(monkeypatch, review_queue):
    uid = "uid-review-projection-fence"
    memory_id = "mem-private"
    review_id = "review-private"
    now = datetime(2026, 7, 28, tzinfo=timezone.utc)
    store = {
        f"users/{uid}/memory_review_queue/{review_id}": {
            "review_id": review_id,
            "fact_id": memory_id,
            "candidate": {"id": memory_id, "content": "Deleted private candidate"},
            "conflict_with": [],
            "authority": "canonical_memory",
            "source_commit_id": "commit-before-delete",
            "source_item_revision": 1,
            "source_content_hash": "hash-before-delete",
            "status": "pending",
            "impact": 0.5,
            "created_at": now,
            "permitted_uses": ["answers_with_disclaimer"],
        },
        f"users/{uid}/memory_items/{memory_id}": {
            "memory_id": memory_id,
            "uid": uid,
            "version": 2,
            "tier": "archive",
            "status": "tombstoned",
            "processing_state": "processed",
            "content": None,
            "evidence": [],
            "source_state": "tombstoned",
            "sensitivity_labels": [],
            "visibility": "private",
            "user_asserted": False,
            "captured_at": now,
            "updated_at": now,
            "ledger_commit_id": "commit-delete",
            "ledger_sequence": 2,
            "item_revision": 2,
            "source_commit_id": "commit-delete",
            "source_commit_sequence": 2,
            "content_hash": "hash-after-delete",
            "account_generation": 1,
        },
    }
    monkeypatch.setattr(review_queue, "_store", lambda: FakeDocumentStore(backing=store))

    fetched = review_queue.get_review_conflict(uid, review_id)
    listed = review_queue.list_review_conflicts(uid, status="", limit=10)

    assert fetched is not None
    assert fetched["status"] == "tombstoned"
    assert fetched["candidate"] == {"id": memory_id}
    assert fetched["permitted_uses"] == []
    assert listed == [fetched]
    assert store[f"users/{uid}/memory_review_queue/{review_id}"]["candidate"]["content"] == (
        "Deleted private candidate"
    )
