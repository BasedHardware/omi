import os
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

import pytest

from testing.import_isolation import fake_firestore_transactional, load_module_fresh, stub_modules

from database.memory_collections import MemoryCollections

from tests.unit.fixtures.non_active_firestore import TransactionalFakeDb as _FakeDb

_BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def nar():
    """Load a fresh database.memory_non_active_routes with a fake-transactional firestore_v1.

    ``_persist_non_active_route_outcome_transaction`` is bound to ``transactional`` at import
    time, and the real ``google.cloud.firestore_v1.transactional`` uses Firestore's internal
    transaction machinery (which the unit-test ``FakeTransaction`` does not implement). We
    therefore wrap the real ``firestore_v1`` module so every other attribute stays intact,
    override only ``transactional`` with the fake-transaction-compatible wrapper, and re-exec
    the module against that wrapper. See backend/docs/test_isolation.md and
    testing/import_isolation.load_module_fresh.
    """
    import google.cloud.firestore_v1 as real_fv1

    fv1_stub = ModuleType("google.cloud.firestore_v1")
    fv1_stub.__dict__.update(real_fv1.__dict__)
    setattr(fv1_stub, "transactional", fake_firestore_transactional)

    with stub_modules({"google.cloud.firestore_v1": fv1_stub}):
        module = load_module_fresh(
            "database.memory_non_active_routes",
            os.path.join(str(_BACKEND), "database", "memory_non_active_routes.py"),
        )
        yield module


def _outcome(nar, **overrides):
    data = dict(
        uid="u1",
        route=nar.NonActiveRoute.review,
        idempotency_key="idem-review-1",
        source_ids=["conv1", "ev1"],
        reason="low confidence needs user confirmation",
        run_id="run1",
        patch_id="patch1",
        audit_metadata={"actor": "l2", "score": 0.62},
        created_at=datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
    )
    data.update(overrides)
    return nar.NonActiveRouteOutcome(**data)


def test_persist_non_active_outcome_is_idempotent_and_uses_one_deterministic_document(nar):
    db = _FakeDb()
    outcome = _outcome(nar)

    first = nar.persist_non_active_route_outcome(outcome, db_client=db)
    second = nar.persist_non_active_route_outcome(outcome, db_client=db)

    assert first == second
    assert len(db.docs) == 1
    assert len(db.transaction_obj.sets) == 0
    path, stored = next(iter(db.docs.items()))
    assert path == f"users/u1/non_active_memory_routes/{first.outcome_id}"
    assert stored["idempotency_key"] == "idem-review-1"
    assert stored["source_ids"] == ["conv1", "ev1"]
    assert stored["reason"] == "low confidence needs user confirmation"
    assert stored["route"] == "review"
    assert stored["run_id"] == "run1"
    assert stored["patch_id"] == "patch1"
    assert stored["audit_metadata"] == {"actor": "l2", "score": 0.62}


def test_same_idempotency_key_with_different_payload_fails_closed(nar):
    db = _FakeDb()
    nar.persist_non_active_route_outcome(_outcome(nar), db_client=db)

    with pytest.raises(nar.NonActiveRouteStoreConflict, match="idempotency key payload mismatch"):
        nar.persist_non_active_route_outcome(_outcome(nar, reason="different", source_ids=["conv2"]), db_client=db)

    assert len(db.docs) == 1


def test_all_t17_non_active_routes_are_persistable_auditable_and_kept_out_of_default_memory_items(nar):
    db = _FakeDb()
    collections = MemoryCollections(uid="u1")

    for route in [
        nar.NonActiveRoute.review,
        nar.NonActiveRoute.archive,
        nar.NonActiveRoute.context_only,
        nar.NonActiveRoute.reject,
        nar.NonActiveRoute.hidden,
        nar.NonActiveRoute.skip,
    ]:
        persisted = nar.persist_non_active_route_outcome(
            _outcome(
                nar,
                route=route,
                idempotency_key=f"idem-{route.value}",
                reason=f"{route.value} decision",
                source_ids=[f"src-{route.value}"],
            ),
            db_client=db,
        )
        assert persisted.route == route
        assert persisted.default_long_term_visible is False
        assert persisted.audit_metadata["actor"] == "l2"

    assert len(db.docs) == 6
    assert all(path.startswith("users/u1/non_active_memory_routes/") for path in db.docs)
    assert not any(path.startswith(f"{collections.memory_items}/") for path in db.docs)
