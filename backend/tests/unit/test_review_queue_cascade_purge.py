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
        store[f"{base}/{doc_id}"] = dict(data)


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
                "status": "pending",
            },
            "review-resolved": {
                "review_id": "review-resolved",
                "fact_id": "mem_deleted",
                "status": "accepted",
            },
        },
    )

    monkeypatch.setattr(review_queue, "_store", lambda: FakeDocumentStore(backing=store))

    purged = review_queue.purge_stale_review_conflicts_for_memories(uid, ["mem_deleted"])

    assert sorted(purged) == ["review-hit-conflict", "review-hit-fact"]
    assert store[f"users/{uid}/memory_review_queue/review-hit-fact"]["status"] == "dropped"
    assert store[f"users/{uid}/memory_review_queue/review-unrelated"]["status"] == "pending"
    assert store[f"users/{uid}/memory_review_queue/review-resolved"]["status"] == "accepted"
