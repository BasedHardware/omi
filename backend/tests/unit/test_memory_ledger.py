"""Memory ledger unit tests.

``database.memory_ledger`` binds ``db`` from ``database._client`` and imports
``transactional`` from ``google.cloud.firestore_v1`` at import time, so a fake
``database._client`` + firestore chain must be active before the module is exec'd.
This is the sanctioned Tier-2 "fake must precede import" case (see
``backend/docs/test_isolation.md`` and ``testing/import_isolation.load_module_fresh``).
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module", autouse=True)
def _load_modules():
    """Load fresh database.memory_ledger (+ its database.projection_repair dep) against
    a stubbed database._client + google.cloud.firestore_v1 chain."""
    client_stub = ModuleType("database._client")
    client_stub.db = MagicMock(name="db")
    client_stub.document_id_from_seed = lambda seed: "id-" + str(abs(hash(seed)) % (10**12))

    google_pkg = ModuleType("google")
    google_pkg.__path__ = []  # type: ignore[attr-defined]
    google_cloud_pkg = ModuleType("google.cloud")
    google_cloud_pkg.__path__ = []  # type: ignore[attr-defined]
    firestore_v1_stub = ModuleType("google.cloud.firestore_v1")
    firestore_v1_stub.transactional = lambda func: func

    fakes = {
        "database._client": client_stub,
        "google": google_pkg,
        "google.cloud": google_cloud_pkg,
        "google.cloud.firestore_v1": firestore_v1_stub,
    }
    with stub_modules(fakes):
        memory_ledger = load_module_fresh(
            "database.memory_ledger",
            os.path.join(str(_BACKEND), "database", "memory_ledger.py"),
        )
        projection_repair = memory_ledger.projection_repair
        globals()["memory_ledger"] = memory_ledger
        globals()["projection_repair"] = projection_repair
        yield


def _fact(fact_id, content, *, valid_from=None, valid_to=None):
    qualifiers = {}
    if valid_from:
        qualifiers["valid_from"] = valid_from
    if valid_to:
        qualifiers["valid_to"] = valid_to
    return {
        "id": fact_id,
        "content": content,
        "predicate": "resides_in",
        "arguments": {"location": content.removeprefix("Lives in ")},
        "subject_entity_id": "user",
        "qualifiers": qualifiers,
    }


def test_fold_commits_replays_head_and_valid_time():
    january = datetime(2026, 1, 15, tzinfo=timezone.utc)
    february = datetime(2026, 2, 1, tzinfo=timezone.utc)
    learned = datetime(2026, 6, 1, tzinfo=timezone.utc)
    fact = _fact("m1", "Lives in NYC", valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc), valid_to=january)
    commit = memory_ledger.build_commit(None, [memory_ledger.add_fact(fact)], commit_time=learned)

    assert "m1" in memory_ledger.fold_commits([commit], valid_time=january)
    assert "m1" not in memory_ledger.fold_commits([commit], valid_time=february)


def test_add_fact_normalizes_legacy_valid_at_for_replay():
    valid_from = datetime(2026, 6, 1, tzinfo=timezone.utc)
    before_valid = datetime(2026, 5, 31, tzinfo=timezone.utc)
    fact = _fact("m1", "Lives in NYC")
    fact["valid_at"] = valid_from
    commit = memory_ledger.build_commit(None, [memory_ledger.add_fact(fact)], commit_time=valid_from)

    assert "m1" not in memory_ledger.fold_commits([commit], valid_time=before_valid)
    assert "m1" in memory_ledger.fold_commits([commit], valid_time=valid_from)
    assert commit["mutations"][0]["fact"]["qualifiers"]["valid_from"] == valid_from


def test_supersede_commit_flips_materialized_head_like_invalidate():
    first = memory_ledger.build_commit(
        None,
        [memory_ledger.add_fact(_fact("m1", "Lives in NYC"))],
        commit_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    second = memory_ledger.build_commit(
        first["commit_id"],
        [memory_ledger.supersede_fact("m1", by="m2", kind="contradict")],
        commit_time=datetime(2026, 6, 2, tzinfo=timezone.utc),
    )

    head = memory_ledger.fold_commits([first, second])

    assert "m1" not in head


def test_valid_time_query_can_return_superseded_fact_for_past_window():
    june_1 = datetime(2026, 6, 1, tzinfo=timezone.utc)
    june_2 = datetime(2026, 6, 2, tzinfo=timezone.utc)
    old_fact = _fact("m1", "Lives in NYC", valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc))
    first = memory_ledger.build_commit(None, [memory_ledger.add_fact(old_fact)], commit_time=june_1)
    second = memory_ledger.build_commit(
        first["commit_id"],
        [memory_ledger.supersede_fact("m1", by="m2", kind="contradict", valid_interval={"valid_to": june_2})],
        commit_time=june_2,
    )

    past_truth = memory_ledger.fold_commits([first, second], valid_time=datetime(2026, 5, 1, tzinfo=timezone.utc))
    current_head = memory_ledger.fold_commits([first, second])

    assert "m1" in past_truth
    assert "m1" not in current_head


def test_retract_payload_tombstones_historical_checkout():
    june_1 = datetime(2026, 6, 1, tzinfo=timezone.utc)
    june_2 = datetime(2026, 6, 2, tzinfo=timezone.utc)
    first = memory_ledger.build_commit(None, [memory_ledger.add_fact(_fact("m1", "Lives in NYC"))], commit_time=june_1)
    second = memory_ledger.build_commit(
        first["commit_id"],
        [memory_ledger.retract_fact("m1", reason="source_tombstoned")],
        commit_time=june_2,
    )

    facts = {}
    for commit in [first, second]:
        for mutation in commit["mutations"]:
            memory_ledger._apply_mutation(facts, mutation, commit["commit_time"])

    assert facts["m1"]["content"] is None
    assert facts["m1"]["arguments"] == {}
    assert facts["m1"]["redaction_status"] == "payload_tombstoned"


def test_tombstone_evidence_marks_evidence_without_removing_it():
    june_1 = datetime(2026, 6, 1, tzinfo=timezone.utc)
    june_2 = datetime(2026, 6, 2, tzinfo=timezone.utc)
    fact = _fact("m1", "Lives in NYC")
    fact["evidence"] = [{"evidence_id": "ev1", "source_id": "conv1"}]
    first = memory_ledger.build_commit(None, [memory_ledger.add_fact(fact)], commit_time=june_1)
    second = memory_ledger.build_commit(
        first["commit_id"],
        [memory_ledger.tombstone_evidence("m1", "ev1", june_2)],
        commit_time=june_2,
    )

    head = memory_ledger.fold_commits([first, second])

    assert head["m1"]["evidence"][0]["evidence_id"] == "ev1"
    assert head["m1"]["evidence"][0]["redaction_status"] == "tombstoned"


def test_tombstone_evidence_recomputes_replayed_veracity_from_active_evidence():
    june_1 = datetime(2026, 6, 1, tzinfo=timezone.utc)
    june_2 = datetime(2026, 6, 2, tzinfo=timezone.utc)
    fact = _fact("m1", "Lives in NYC")
    fact["capture_confidence"] = 0.8
    fact["veracity"] = 0.67
    fact["evidence"] = [
        {
            "evidence_id": "ev-conv",
            "source_id": "conv1",
            "independence_group": "conv1",
            "capture_confidence": 0.65,
        },
        {
            "evidence_id": "ev-calendar",
            "source_id": "calendar1",
            "independence_group": "calendar1",
            "capture_confidence": 0.8,
        },
    ]
    first = memory_ledger.build_commit(None, [memory_ledger.add_fact(fact)], commit_time=june_1)
    second = memory_ledger.build_commit(
        first["commit_id"],
        [memory_ledger.tombstone_evidence("m1", "ev-conv", june_2)],
        commit_time=june_2,
    )

    head = memory_ledger.fold_commits([first, second])

    assert head["m1"]["evidence"][0]["redaction_status"] == "tombstoned"
    assert head["m1"]["veracity"] == 0.45
    assert head["m1"]["uncertainty_reasons"] == ["single_source"]


def test_diff_returns_typed_mutations_between_parent_child():
    first = memory_ledger.build_commit(
        None,
        [memory_ledger.add_fact(_fact("m1", "Lives in NYC"))],
        commit_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    mutation = memory_ledger.supersede_fact("m1", by="m2", kind="contradict")
    second = memory_ledger.build_commit(
        first["commit_id"],
        [mutation],
        commit_time=datetime(2026, 6, 2, tzinfo=timezone.utc),
    )

    assert memory_ledger.diff(first, second) == [mutation]


def test_append_commit_to_history_is_idempotent_for_same_commit():
    state = {"current_head_commit_id": None}
    commits = {}
    mutations = [memory_ledger.add_fact(_fact("m1", "Lives in NYC"))]

    first = memory_ledger.append_commit_to_history(state, commits, None, mutations)
    second = memory_ledger.append_commit_to_history(state, commits, first["commit"]["parent_commit_id"], mutations)

    assert first["applied"] is True
    assert second["applied"] is False
    assert len(commits) == 1


def test_append_commit_to_history_rejects_sibling_heads():
    state = {"current_head_commit_id": None}
    commits = {}
    parent = None

    first = memory_ledger.append_commit_to_history(
        state,
        commits,
        parent,
        [memory_ledger.add_fact(_fact("m1", "Lives in NYC"))],
    )

    try:
        memory_ledger.append_commit_to_history(
            state,
            commits,
            parent,
            [memory_ledger.add_fact(_fact("m2", "Lives in SF"))],
        )
    except memory_ledger.HeadConflict as exc:
        assert exc.expected_parent == parent
        assert exc.current_head == first["commit"]["commit_id"]
    else:
        raise AssertionError("Expected same-parent sibling append to fail")


def test_projection_repair_extracts_affected_fact_ids_and_metadata():
    mutations = [
        memory_ledger.add_fact({"id": "m1", "subject_entity_id": "user", "object_entity_ids": ["project"]}),
        memory_ledger.supersede_fact("m2", by="m1"),
    ]

    assert projection_repair.affected_fact_ids(mutations) == ["m1", "m2"]
    assert projection_repair.projection_metadata_for_fact(
        {
            "id": "m1",
            "subject_entity_id": "user",
            "object_entity_ids": ["project"],
            "qualifiers": {"scope": "work", "valid_from": "2026-06-01"},
            "status": "pending_review",
            "redaction_status": "active",
        },
        source_commit_id="commit1",
    ) == {
        "fact_id": "m1",
        "memory_id": "m1",
        "source_commit_id": "commit1",
        "projection_version": projection_repair.PROJECTION_VERSION,
        "entity_ids": ["user", "project"],
        "valid_time": "2026-06-01",
        "scope": "work",
        "epistemic_status": "pending_review",
        "source_tombstone_state": "active",
    }


def test_reconcile_projection_detects_and_repairs_drift_to_zero():
    facts = [
        {"id": "active", "content": "Active"},
        {"id": "retracted", "content": None, "invalid_at": datetime(2026, 6, 1, tzinfo=timezone.utc)},
    ]

    drift = projection_repair.reconcile_memory_projection("uid-1", facts, ["retracted"])
    repaired = projection_repair.reconcile_memory_projection("uid-1", facts, ["active"])

    assert drift["missing_upserts"] == ["active"]
    assert drift["stale_deletes"] == ["retracted"]
    assert drift["projection_fail_count"] == 2
    assert repaired["drift_count"] == 0
    assert repaired["projection_fail_count"] == 0


def test_append_commit_enqueues_projection_repairs(monkeypatch):
    queued = []
    commit = memory_ledger.build_commit(None, [memory_ledger.add_fact({"id": "m1"})])

    monkeypatch.setattr(
        memory_ledger,
        "_append_commit_transaction",
        lambda *args, **kwargs: {"commit": commit, "applied": True},
    )
    monkeypatch.setattr(
        memory_ledger.projection_repair,
        "enqueue_projection_repairs",
        lambda uid, item, **_kwargs: queued.append((uid, item)) or ["repair"],
    )

    result = memory_ledger.append_commit("uid-1", None, commit["mutations"])

    assert result["applied"] is True
    assert queued == [("uid-1", commit)]


def test_process_projection_repairs_applies_queued_vector_repairs(monkeypatch):
    updates = []

    class FakeDoc:
        id = "repair1"

        @property
        def reference(self):
            return self

        def to_dict(self):
            return {"repair_id": "repair1", "fact_id": "m1", "status": "queued"}

        def update(self, payload):
            updates.append(payload)

    class FakeQuery:
        def limit(self, value):
            return self

        def stream(self):
            return [FakeDoc()]

    class FakeCollection:
        def document(self, value):
            return self

        def collection(self, value):
            return self

        def where(self, *args):
            return FakeQuery()

    class FakeDB:
        def collection(self, value):
            return FakeCollection()

    monkeypatch.setattr(projection_repair, "db", FakeDB())

    result = projection_repair.process_projection_repairs(
        "uid-1",
        fact_loader=lambda fact_id: {"id": fact_id, "invalid_at": datetime(2026, 6, 1, tzinfo=timezone.utc)},
        repair_func=lambda uid, fact: "delete" if fact and fact.get("invalid_at") else "upsert",
    )

    assert result == {"repaired": ["repair1"], "failed": [], "processed": 1}
    assert updates[0]["status"] == "repaired"
    assert updates[0]["repair_action"] == "delete"
