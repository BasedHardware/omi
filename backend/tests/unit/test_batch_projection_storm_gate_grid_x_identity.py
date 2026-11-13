"""Identity and boundary grid for the projection storm gate.

These cells pin the facts the parameterised grids assume: the process damper
is per-label (arming ``batch_projection`` damps that label and nothing
else), the label resolves through the store's static grammar, the accessor
resolves per call against both kill switches, the wave ladder caps at the
damper ceiling, the lane survives a hostile damper without losing its
retry schedule, and the docs page stays in parity with the shipped
behavior.

Failure-Class: FC-projection-contention-chain-collides-inside-armed-storm-window
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import Aborted

from database import batch_pipeline_projection as projection_module
from database import batch_pipeline_store as storage
from database.batch_pipeline_transaction_labels import require_operation_label
from database.firestore_transaction_retry import equal_jitter_delay

BACKEND = Path(__file__).resolve().parents[2]


class PinnedClock:
    """Deterministic monotonic clock, sleeper recorder and jitter source."""

    def __init__(self, now=100.0, jitter=0.0):
        self.now = now
        self.jitter = jitter
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(round(seconds, 9))
        self.now += seconds

    def random_value(self):
        return self.jitter


def make_damper(jitter=0.0):
    clock = PinnedClock(jitter=jitter)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    return damper, clock


def build_store(monkeypatch, damper, client=None):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    return storage.FirestoreStore(
        'batch_pipeline_dev', firestore_client=client if client is not None else Mock(), storm_damper=damper
    )


# --------------------------------------------------------------------------
# Per-label isolation on the real damper
# --------------------------------------------------------------------------


def test_identity_arming_projection_label_damps_only_that_label(monkeypatch):
    damper, clock = make_damper()
    damper.arm('batch_projection')
    residual = damper.peek('batch_projection')[0]
    assert residual > 0
    waited_claim, _ = damper.consult('batch_claim')
    waited_complete, _ = damper.consult('batch_complete')
    waited_merge, _ = damper.consult('batch_merge_commit')
    waited_projection, _ = damper.consult('batch_projection')
    assert (waited_claim, waited_complete, waited_merge) == (0.0, 0.0, 0.0)
    assert waited_projection == pytest.approx(residual)
    assert clock.sleeps == [pytest.approx(residual)]


def test_identity_projection_label_window_is_bounded_by_the_damper_cap(monkeypatch):
    damper, clock = make_damper()
    applied = 0.0
    for _ in range(1, 7):
        applied = damper.arm('batch_projection')
        assert applied <= storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS
    # Six exhaustions saturate the ladder: the cap binds from the fifth
    # rung and the zero jitter draw halves every applied window.
    assert applied == pytest.approx(storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS / 2)


def test_identity_projection_wave_rung_ladder_is_capped_and_halved_by_jitter(monkeypatch):
    damper, clock = make_damper(jitter=0.0)
    rungs = [damper.wave_rung_wait(attempt) for attempt in (1, 2, 3, 4, 5, 6, 7)]
    assert rungs == [
        pytest.approx(0.125),
        pytest.approx(0.25),
        pytest.approx(0.5),
        pytest.approx(1.0),
        pytest.approx(2.0),
        pytest.approx(2.0),
        pytest.approx(2.0),
    ]
    assert max(rungs) <= storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS


def test_identity_projection_label_uses_the_wave_engagement_threshold(monkeypatch):
    assert storage.FirestoreStore.WAVE_ENGAGEMENT_ATTEMPT == 3


def test_identity_equal_jitter_engine_ladder_stays_the_projection_gate_baseline(monkeypatch):
    delays = [equal_jitter_delay(attempt, lambda: 0.0) for attempt in (1, 2, 3, 4, 5)]
    assert delays == [
        pytest.approx(0.1),
        pytest.approx(0.2),
        pytest.approx(0.4),
        pytest.approx(0.8),
        pytest.approx(1.6),
    ]


# --------------------------------------------------------------------------
# Label grammar
# --------------------------------------------------------------------------


def test_identity_projection_label_resolves_through_the_static_grammar(monkeypatch):
    assert require_operation_label('batch_projection') == 'batch_projection'


def test_identity_unlabeled_runs_stay_refused(monkeypatch):
    with pytest.raises(ValueError):
        require_operation_label(None)


def test_identity_interpolated_labels_stay_refused(monkeypatch):
    with pytest.raises(ValueError):
        require_operation_label('batch_projection; drop table')
    with pytest.raises(ValueError):
        require_operation_label('batch_projection\n')


# --------------------------------------------------------------------------
# Accessor resolution
# --------------------------------------------------------------------------


def test_identity_accessor_returns_the_namespace_damper(monkeypatch):
    damper, clock = make_damper()
    monkeypatch.setattr(storage, 'contention_retry_enabled', lambda: True)
    monkeypatch.setattr(storage, 'contention_storm_damper_enabled', lambda: True)
    store = build_store(monkeypatch, damper)
    assert store.contention_storm_damper is damper


def test_identity_accessor_is_none_while_the_storm_damper_switch_is_off(monkeypatch):
    damper, clock = make_damper()
    monkeypatch.setattr(storage, 'contention_retry_enabled', lambda: True)
    monkeypatch.setattr(storage, 'contention_storm_damper_enabled', lambda: False)
    store = build_store(monkeypatch, damper)
    assert store.contention_storm_damper is None


def test_identity_accessor_is_none_while_contention_retry_is_off(monkeypatch):
    damper, clock = make_damper()
    monkeypatch.setattr(storage, 'contention_retry_enabled', lambda: False)
    monkeypatch.setattr(storage, 'contention_storm_damper_enabled', lambda: True)
    store = build_store(monkeypatch, damper)
    assert store.contention_storm_damper is None


def test_identity_accessor_resolution_tracks_the_switches_per_call(monkeypatch):
    damper, clock = make_damper()
    enabled = {'damper': True, 'retry': True}
    monkeypatch.setattr(storage, 'contention_retry_enabled', lambda: enabled['retry'])
    monkeypatch.setattr(storage, 'contention_storm_damper_enabled', lambda: enabled['damper'])
    store = build_store(monkeypatch, damper)
    assert store.contention_storm_damper is damper
    enabled['damper'] = False
    assert store.contention_storm_damper is None
    enabled['damper'] = True
    enabled['retry'] = False
    assert store.contention_storm_damper is None


def test_identity_projection_lane_reads_the_accessor_from_a_real_store(monkeypatch):
    damper, clock = make_damper()
    monkeypatch.setattr(storage, 'contention_retry_enabled', lambda: True)
    monkeypatch.setattr(storage, 'contention_storm_damper_enabled', lambda: True)
    inner = build_store(monkeypatch, damper)
    store = projection_module.ProjectionStore(inner)
    assert store.store.contention_storm_damper is damper
    assert inner.contention_storm_damper is damper


def test_identity_simulated_primary_has_no_damper_contract(monkeypatch):
    primary = SimpleNamespace(client=Mock(), namespace='batch_pipeline_dev')
    store = projection_module.ProjectionStore(primary)
    assert not hasattr(primary, 'contention_storm_damper')


# --------------------------------------------------------------------------
# Hostile-damper fail-open
# --------------------------------------------------------------------------


def test_identity_hostile_peek_collapses_to_the_bare_schedule(monkeypatch):
    damper, clock = make_damper()
    monkeypatch.setattr(storage, 'contention_retry_enabled', lambda: True)
    monkeypatch.setattr(storage, 'contention_storm_damper_enabled', lambda: True)
    original_peek = damper.peek
    peek_calls = []

    def hostile_peek(label, *, client=None):
        peek_calls.append(label)
        original_peek(label, client=client)
        raise RuntimeError('hostile peek')

    damper.peek = hostile_peek
    client = Mock()
    aborts = {'left': 1}

    def body(transaction):
        if aborts['left']:
            aborts['left'] -= 1
            raise Aborted('synthetic read contention')
        return 'projected'

    inner = build_store(monkeypatch, damper, client=client)
    store = projection_module.ProjectionStore(inner)
    result = store.run(body, policy=SimpleNamespace(projection_contention=True))
    assert result == 'projected'
    # The engine swallowed the hostile answer: the chain kept its retry
    # schedule and no damper window was consumed.
    assert peek_calls == ['batch_projection']
    assert aborts['left'] == 0


def test_identity_hostile_arm_window_stays_finite(monkeypatch):
    damper, clock = make_damper(jitter=0.0)
    applied = 0.0
    for _ in range(6):
        applied = damper.arm('batch_projection')
        assert 0.0 < applied <= storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS
    assert applied == pytest.approx(storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS / 2)


# --------------------------------------------------------------------------
# Docs parity
# --------------------------------------------------------------------------


def test_identity_docs_page_names_the_lane_and_the_label(monkeypatch):
    text = (BACKEND / 'docs' / 'batch-projection-storm-gate.md').read_text()
    assert 'ProjectionStore.run' in text
    assert 'batch_projection' in text
    assert 'inter_attempt_gate' in text


def test_identity_docs_page_keeps_the_failure_class_trailer(monkeypatch):
    text = (BACKEND / 'docs' / 'batch-projection-storm-gate.md').read_text()
    assert 'Failure-Class: FC-projection-contention-chain-collides-inside-armed-storm-window' in text


def test_identity_production_gate_carries_the_failure_class_trailer(monkeypatch):
    text = (BACKEND / 'database' / 'batch_pipeline_projection.py').read_text()
    assert 'FC-projection-contention-chain-collides-inside-armed-storm-window' in text


def test_identity_docs_page_documents_both_kill_switches(monkeypatch):
    text = (BACKEND / 'docs' / 'batch-projection-storm-gate.md').read_text()
    assert 'BATCH_PIPELINE_CONTENTION_RETRY_ENABLED' in text
    assert 'SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED' in text


def test_identity_docs_page_documents_the_first_attempt_guarantee(monkeypatch):
    text = (BACKEND / 'docs' / 'batch-projection-storm-gate.md').read_text()
    assert 'never gated' in text
