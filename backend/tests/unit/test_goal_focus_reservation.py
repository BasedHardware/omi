"""The focused set is a collection query the point-based store transaction cannot pull into its
read-set, so concurrent focus_goal calls could jointly exceed focus_cap or collide on focus_rank
(cubic review PR 10887, backend/database/goals.py:521). The fix makes every *state-changing* focus
write a per-user reservation token; two concurrent focus transactions then write-write-conflict on
that single doc, and the store's optimistic concurrency (the same mechanism the store contract
exercises via create/AlreadyExists) aborts one and re-runs apply() against a fresh focused set.

These tests exercise focus_goal through the neutral store fake and assert the reservation token
advances on exactly the state-changing paths (a real focus) and stays put on the paths that change
nothing (idempotent replay, a no-op re-focus of an already-focused goal at the same rank) — proving
the conflict seam is wired where serialization is needed and nowhere it is not. The abort/retry
itself is the store adapter's contract-tested behavior, not goals.py's."""

import pytest

from database import goals as goals_db
from tests.store_fakes import FakeDocumentStore
from tests.unit.canonical_cohort_test_helpers import set_canonical_cohort

UID = "u1"
GENERATION = 3
RESERVATION_PATH = f"users/{UID}/{goals_db.TASK_INTELLIGENCE_CONTROL_COLLECTION}/{goals_db.FOCUS_RESERVATION_DOCUMENT}"
CONTROL_PATH = f"users/{UID}/{goals_db.TASK_INTELLIGENCE_CONTROL_COLLECTION}/{goals_db.TASK_INTELLIGENCE_CONTROL_DOCUMENT}"


@pytest.fixture
def store(monkeypatch):
    set_canonical_cohort(monkeypatch, UID)
    fake = FakeDocumentStore()
    monkeypatch.setattr(goals_db, "_store", lambda: fake)
    fake._docs[CONTROL_PATH] = {"workflow_mode": "read", "account_generation": GENERATION}
    return fake


def _create(store, goal_id, *, status="background", focus_rank=None):
    goals_db.create_goal(
        UID,
        {"id": goal_id, "title": goal_id, "desired_outcome": f"Outcome {goal_id}", "status": status, "focus_rank": focus_rank},
    )
    store._docs[f"users/{UID}/goals/{goal_id}"]["account_generation"] = GENERATION


def _reservation_version(store):
    return (store._docs.get(RESERVATION_PATH) or {}).get("version")


def test_state_changing_focus_bumps_reservation_token(store):
    _create(store, "g0")
    assert _reservation_version(store) is None  # untouched before any focus

    goals_db.focus_goal(UID, "g0", idempotency_key="focus-g0", account_generation=GENERATION)
    assert _reservation_version(store) == 1

    _create(store, "g1")
    goals_db.focus_goal(UID, "g1", idempotency_key="focus-g1", account_generation=GENERATION)
    assert _reservation_version(store) == 2  # each real focus advances the serialization token


def test_idempotent_replay_does_not_touch_reservation(store):
    _create(store, "g0")
    goals_db.focus_goal(UID, "g0", idempotency_key="focus-g0", account_generation=GENERATION)
    assert _reservation_version(store) == 1

    # Same idempotency key -> receipt replay returns the stored result without re-running the focus
    # write path, so it must not consume a reservation bump.
    goals_db.focus_goal(UID, "g0", idempotency_key="focus-g0", account_generation=GENERATION)
    assert _reservation_version(store) == 1


def test_noop_refocus_does_not_touch_reservation(store):
    _create(store, "g0")
    goals_db.focus_goal(UID, "g0", idempotency_key="focus-g0", account_generation=GENERATION)
    assert _reservation_version(store) == 1

    # Re-focusing an already-focused goal at its current rank changes nothing about the focused set
    # (a fresh idempotency key so it is not a receipt replay) -> no serialization needed, no bump.
    goals_db.focus_goal(UID, "g0", idempotency_key="refocus-g0", account_generation=GENERATION)
    assert _reservation_version(store) == 1
