"""Unit tests for utils.experiments: assignment determinism, balance, and the
both-arms-enrolled anti-pattern guard.

The module's whole reason to exist is that a holdout must never silently
vanish from the denominator (see utils/experiments.py's module docstring for
the 2026-08-26 churn-cohort story this is defending against). The tests here
are written to make that failure mode loud if it ever regresses.
"""

from __future__ import annotations

import pytest

from tests.unit.fixtures.generic_firestore_fake import FakeFirestore
from utils.experiments import (
    CONTROL,
    ENROLLED_EVENT,
    TREATMENT,
    assigned_variant,
    bucket_of,
    enroll,
    enrollment_counts,
    existing_assignment,
)
from utils.product_telemetry import set_product_telemetry_client_for_tests


class _FakePosthog:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.events: list[dict] = []

    def capture(self, **event):
        if self.fail:
            raise RuntimeError('posthog unavailable')
        self.events.append(event)


@pytest.fixture(autouse=True)
def _posthog(monkeypatch):
    monkeypatch.setenv('POSTHOG_PROJECT_API_KEY', 'fake-key')
    fake = _FakePosthog()
    set_product_telemetry_client_for_tests(fake)
    yield fake
    set_product_telemetry_client_for_tests(None)


EXPERIMENT_A = 'EXP-TEST-A'
EXPERIMENT_B = 'EXP-TEST-B'


def test_assignment_is_deterministic_and_stable():
    for uid in ('uid-1', 'uid-2', 'uid-3'):
        first = assigned_variant(EXPERIMENT_A, uid)
        for _ in range(5):
            assert assigned_variant(EXPERIMENT_A, uid) == first
        # bucket_of underlies assigned_variant and must be equally stable.
        assert bucket_of(EXPERIMENT_A, uid) == bucket_of(EXPERIMENT_A, uid)


def test_split_is_roughly_balanced_over_many_synthetic_uids():
    n = 4000
    treatment_count = sum(1 for i in range(n) if assigned_variant(EXPERIMENT_A, f'synthetic-{i}') == TREATMENT)
    fraction = treatment_count / n
    # 50/50 draw over 4000 independent-ish hash buckets; a generous +/-3pp band
    # comfortably separates "roughly balanced" from "the split is broken"
    # without making the test flaky.
    assert 0.47 <= fraction <= 0.53


def test_changing_experiment_id_rerandomizes_but_nothing_else_does():
    uids = [f'uid-{i}' for i in range(200)]
    variants_a1 = [assigned_variant(EXPERIMENT_A, uid) for uid in uids]
    variants_a2 = [assigned_variant(EXPERIMENT_A, uid) for uid in uids]
    variants_b = [assigned_variant(EXPERIMENT_B, uid) for uid in uids]

    # Same experiment id, same uids, called again: identical draw every time.
    assert variants_a1 == variants_a2

    # A different experiment id (a different salt) must re-randomize enough of
    # the population that it is not just a relabeling of the same split.
    differences = sum(1 for a, b in zip(variants_a1, variants_b) if a != b)
    assert differences > len(uids) * 0.2


def test_enroll_is_idempotent_and_emits_posthog_exactly_once(_posthog):
    db = FakeFirestore()

    first = enroll(experiment_id=EXPERIMENT_A, uid='uid-idempotent', firestore_client=db)
    assert first is not None
    assert first.newly_enrolled is True
    assert len(_posthog.events) == 1

    second = enroll(experiment_id=EXPERIMENT_A, uid='uid-idempotent', firestore_client=db)
    assert second is not None
    assert second.newly_enrolled is False
    assert second.variant == first.variant
    # No second PostHog event on the idempotent replay.
    assert len(_posthog.events) == 1


def test_both_arms_emit_experiment_enrolled_so_the_holdout_is_never_invisible(_posthog):
    """Regression guard for the exact failure this module exists to prevent:
    a holdout arm with no exposure event, silently missing from analysis.

    Enrolls enough synthetic uids that both arms are certain to appear, then
    asserts every single one produced an ``Experiment Enrolled`` PostHog
    event — not just the ones who would go on to receive treatment.
    """
    db = FakeFirestore()
    uids = [f'holdout-guard-{i}' for i in range(60)]
    enrollments = [enroll(experiment_id=EXPERIMENT_A, uid=uid, firestore_client=db) for uid in uids]
    assert all(e is not None for e in enrollments)

    variants_seen = {e.variant for e in enrollments}
    assert variants_seen == {CONTROL, TREATMENT}, 'fixture is not exercising both arms; widen the uid pool'

    assert len(_posthog.events) == len(uids)
    emitted_variants = {event['properties']['variant'] for event in _posthog.events}
    assert emitted_variants == {CONTROL, TREATMENT}
    assert all(event['event'] == ENROLLED_EVENT for event in _posthog.events)

    # In particular: every control-arm uid, not just treatment, is present.
    control_uids = {e.uid for e in enrollments if e.variant == CONTROL}
    emitted_uids = {event['distinct_id'] for event in _posthog.events}
    assert control_uids <= emitted_uids


def test_enroll_write_failure_returns_none_and_does_not_emit(_posthog):
    class _RaisingFirestore(FakeFirestore):
        def collection(self, path):
            raise RuntimeError('firestore unavailable')

    result = enroll(experiment_id=EXPERIMENT_A, uid='uid-write-fails', firestore_client=_RaisingFirestore())
    assert result is None
    assert _posthog.events == []


def test_existing_assignment_read_failure_returns_none_not_raise():
    class _RaisingFirestore(FakeFirestore):
        def collection(self, path):
            raise RuntimeError('firestore unavailable')

    assert existing_assignment(EXPERIMENT_A, 'uid-x', firestore_client=_RaisingFirestore()) is None


def test_enrollment_counts_reflects_persisted_assignments():
    db = FakeFirestore()
    uids = [f'count-{i}' for i in range(40)]
    for uid in uids:
        enroll(experiment_id=EXPERIMENT_A, uid=uid, firestore_client=db)

    counts = enrollment_counts(EXPERIMENT_A, firestore_client=db)
    assert counts[CONTROL] + counts[TREATMENT] == len(uids)
    assert counts[CONTROL] > 0 and counts[TREATMENT] > 0
