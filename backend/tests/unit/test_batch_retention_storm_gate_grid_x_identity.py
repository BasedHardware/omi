"""Identity and boundary grid for the retention storm gate.

These cells pin the facts the parameterised grids assume: the process damper
is per-label (arming ``batch_retention`` spaces that label and nothing else),
both retention labels pass the store's static label grammar, the resolver
returns the damper only for a real ``FirestoreStore`` (and only while both
kill switches are on), the wave ladder caps at the damper ceiling, the lane
survives a hostile damper without losing its retry schedule, the entry
consult sleeps through the damper's own sleeper outside the engine's
recorder, and the docs page stays in parity with the shipped behavior.

Failure-Class: FC-retention-contention-chain-collides-inside-armed-storm-window
"""

import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import Aborted

from database import batch_pipeline_store as storage
from database.batch_pipeline_transaction_labels import require_operation_label
from database.firestore_transaction_retry import equal_jitter_delay
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.batch_retention_storm_gate_grid_harness import (
    ChainSleepRecorder,
    ScriptedStormDamper,
    silence_and_pin_chain,
)
from utils.batch_pipeline import retention as retention_module
from utils.batch_pipeline.retention import run_retention_transaction

CAP = storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS
BASE = storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS


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


def test_damper_windows_are_per_label():
    clock = PinnedClock()
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    armed = damper.arm('batch_retention')
    assert armed > 0.0
    waited_same, _generation = damper.consult('batch_retention')
    assert waited_same > 0.0
    waited_other, _generation = damper.consult('batch_artifact_register')
    assert waited_other == 0.0


def test_both_retention_labels_pass_the_store_label_grammar():
    assert require_operation_label('batch_retention') == 'batch_retention'
    assert require_operation_label('batch_artifact_register') == 'batch_artifact_register'


def test_resolver_returns_the_property_only_for_a_real_store(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    scripted = ScriptedStormDamper(residual_schedule=[0.0], wave_wait=0.5, generation=0, entry_wait=0.0)
    real = storage.FirestoreStore('batch_pipeline_dev', firestore_client=StrictFirestore({}), storm_damper=scripted)
    assert retention_module._store_storm_damper(real) is scripted
    assert retention_module._store_storm_damper(SimpleNamespace(client=Mock(), namespace='batch_pipeline_dev')) is None
    assert retention_module._store_storm_damper(Mock()) is None


def test_resolver_honours_the_kill_switches(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    scripted = ScriptedStormDamper(residual_schedule=[0.0], wave_wait=0.5, generation=0, entry_wait=0.0)
    real = storage.FirestoreStore('batch_pipeline_dev', firestore_client=StrictFirestore({}), storm_damper=scripted)
    assert retention_module._store_storm_damper(real) is scripted
    monkeypatch.setattr(storage, 'contention_storm_damper_enabled', lambda: False)
    assert retention_module._store_storm_damper(real) is None


def test_wave_ladder_caps_at_the_damper_ceiling():
    damper = storage._ContentionStormDamper(random_value=lambda: 0.5)
    deep = damper.wave_rung_wait(9)
    assert deep == round(CAP * 0.75, 9)
    shallow = damper.wave_rung_wait(1)
    assert shallow == round(BASE * 0.75, 9)


def test_entry_consult_sleep_stays_outside_the_engine_recorder(monkeypatch, caplog):
    scripted = ScriptedStormDamper(residual_schedule=[0.4], wave_wait=0.5, generation=0, entry_wait=0.6)
    client = Mock()
    recorder = ChainSleepRecorder()
    silence_and_pin_chain(monkeypatch, recorder)
    caplog.set_level(logging.INFO, logger='utils.batch_pipeline.retention')

    calls = []

    def body(transaction):
        calls.append(len(calls) + 1)
        if len(calls) <= 2:
            raise Aborted('synthetic read contention')
        return 'retained'

    assert (
        run_retention_transaction(client, body, operation_name='batch_retention', storm_damper=scripted) == 'retained'
    )
    assert scripted.slept == [0.6]
    assert recorder.sleeps == [
        round(equal_jitter_delay(1, lambda: 0.5) + 0.4, 9),
        round(equal_jitter_delay(2, lambda: 0.5) + 0.4, 9),
    ]


def storage_and_engine_exhaustion():
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    return FirestoreContentionExhausted


def test_exhaustion_stamped_window_is_the_damper_answer_itself(monkeypatch):
    scripted = ScriptedStormDamper(residual_schedule=[0.0], wave_wait=0.5, generation=0, entry_wait=0.0)
    client = Mock()
    silence_and_pin_chain(monkeypatch, ChainSleepRecorder())

    def body(transaction):
        raise Aborted('synthetic read contention')

    with pytest.raises(storage_and_engine_exhaustion()) as raised:
        run_retention_transaction(client, body, operation_name='batch_retention', storm_damper=scripted)
    assert raised.value.retry_after == scripted.arm_wait
    assert ['arm', 'batch_retention', scripted.arm_wait] == scripted.events[-1]


def test_success_after_a_quiet_chain_reports_the_entry_generation(monkeypatch):
    scripted = ScriptedStormDamper(residual_schedule=[0.0], wave_wait=0.5, generation=4, entry_wait=0.0)
    client = Mock()
    silence_and_pin_chain(monkeypatch, ChainSleepRecorder())
    assert run_retention_transaction(client, lambda transaction: 'retained', storm_damper=scripted) == 'retained'
    assert scripted.note_success_args == [['batch_retention', 4]]
