from datetime import datetime, timezone

import pytest

import database.memory_non_active_routes as nar_module
from database.memory_collections import MemoryCollections

from tests.store_fakes import FakeDocumentStore


class _Nar:
    """Test handle: the migrated module plus the backing dict its store writes into."""

    def __init__(self, docs):
        self.docs = docs

    def __getattr__(self, name):
        return getattr(nar_module, name)


@pytest.fixture
def nar(monkeypatch):
    """Bind the module's neutral ``_store`` seam to a fresh in-memory FakeDocumentStore.

    The persistence path migrated off the raw Firestore client onto the storage port
    (ADR-0002); tests assert on returned values and stored state, not Firestore call
    mechanics. ``nar.docs`` is the path->data dict the store persists into.
    """
    docs = {}
    monkeypatch.setattr(nar_module, "_store", lambda: FakeDocumentStore(backing=docs))
    return _Nar(docs)


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
    outcome = _outcome(nar)

    first = nar.persist_non_active_route_outcome(outcome)
    second = nar.persist_non_active_route_outcome(outcome)

    assert first == second
    assert len(nar.docs) == 1
    path, stored = next(iter(nar.docs.items()))
    assert path == f"users/u1/non_active_memory_routes/{first.outcome_id}"
    assert stored["idempotency_key"] == "idem-review-1"
    assert stored["source_ids"] == ["conv1", "ev1"]
    assert stored["reason"] == "low confidence needs user confirmation"
    assert stored["route"] == "review"
    assert stored["run_id"] == "run1"
    assert stored["patch_id"] == "patch1"
    assert stored["audit_metadata"] == {"actor": "l2", "score": 0.62}


def test_same_idempotency_key_with_different_payload_fails_closed(nar):
    nar.persist_non_active_route_outcome(_outcome(nar))

    with pytest.raises(nar.NonActiveRouteStoreConflict, match="idempotency key payload mismatch"):
        nar.persist_non_active_route_outcome(_outcome(nar, reason="different", source_ids=["conv2"]))

    assert len(nar.docs) == 1


def test_all_t17_non_active_routes_are_persistable_auditable_and_kept_out_of_default_memory_items(nar):
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
        )
        assert persisted.route == route
        assert persisted.default_long_term_visible is False
        assert persisted.audit_metadata["actor"] == "l2"

    assert len(nar.docs) == 6
    assert all(path.startswith("users/u1/non_active_memory_routes/") for path in nar.docs)
    assert not any(path.startswith(f"{collections.memory_items}/") for path in nar.docs)
