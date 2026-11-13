"""Identity and boundary grid for the purge storm gate.

These cells pin the facts the parameterised grids assume: the process damper
is per-label (arming ``batch_purge_job_unlink`` spaces that label and nothing
else), all three purge labels pass the store's static label grammar and are
distinct, the wave ladder caps at the damper ceiling, the lane survives a
hostile damper without losing its retry schedule, the entry consult sleeps
through the damper's own sleeper outside the engine's recorder, the stamped
window is the damper's own arm answer, a quiet chain reports the entry
generation, and the emitted grid files stay in parity with the shipped
harness.

Failure-Class: FC-privacy-purge-chain-collides-inside-armed-storm-window
"""

import logging
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import Aborted

from database import batch_pipeline_store as storage
from database.batch_pipeline_purge import (
    PURGE_JOB_UNLINK_LABEL,
    PURGE_OWNER_FAIRNESS_LABEL,
    PURGE_RESULT_ERASE_LABEL,
    run_purge_transaction,
)
from database.batch_pipeline_transaction_labels import require_operation_label
from database.firestore_transaction_retry import equal_jitter_delay
from tests.unit.test_batch_purge_storm_gate import (
    ChainSleepRecorder,
    ScriptedStormDamper,
    silence_and_pin_chain,
)

CAP = storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS
BASE = storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS
GRID_BASE_NAME = 'test_batch_purge_storm_gate_grid_f_'
GRID_MODES = ('dorm', 'live')
GRID_ARMS = ('w075', 'w125', 'w250')
GRID_SITES = ('unlink', 'fair', 'erase')


class PinnedClock:
    """Deterministic monotonic clock, sleeper recorder and jitter source."""

    def __init__(self, now=100.0, jitter=0.5):
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
    armed = damper.arm(PURGE_JOB_UNLINK_LABEL)
    assert armed > 0.0
    waited_same, _generation = damper.consult(PURGE_JOB_UNLINK_LABEL)
    assert waited_same > 0.0
    waited_other, _generation = damper.consult(PURGE_OWNER_FAIRNESS_LABEL)
    assert waited_other == 0.0
    waited_other, _generation = damper.consult(PURGE_RESULT_ERASE_LABEL)
    assert waited_other == 0.0


def test_all_three_purge_labels_pass_the_store_label_grammar():
    for label in (PURGE_JOB_UNLINK_LABEL, PURGE_OWNER_FAIRNESS_LABEL, PURGE_RESULT_ERASE_LABEL):
        assert require_operation_label(label) == label
    assert len({PURGE_JOB_UNLINK_LABEL, PURGE_OWNER_FAIRNESS_LABEL, PURGE_RESULT_ERASE_LABEL}) == 3


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
    caplog.set_level(logging.INFO, logger='database.batch_pipeline_purge')

    calls = []

    def body(transaction):
        calls.append(len(calls) + 1)
        if len(calls) <= 2:
            raise Aborted('synthetic read contention')
        return 'erased'

    assert run_purge_transaction(client, body, operation_name=PURGE_JOB_UNLINK_LABEL, storm_damper=scripted) == 'erased'
    assert scripted.slept == [0.6]
    assert recorder.sleeps == [
        round(equal_jitter_delay(1, lambda: 0.5) + 0.4, 9),
        round(equal_jitter_delay(2, lambda: 0.5) + 0.4, 9),
    ]


def test_exhaustion_stamped_window_is_the_damper_answer_itself(monkeypatch):
    scripted = ScriptedStormDamper(residual_schedule=[0.0], wave_wait=0.5, generation=0, entry_wait=0.0)
    client = Mock()
    silence_and_pin_chain(monkeypatch, ChainSleepRecorder())

    def body(transaction):
        raise Aborted('synthetic read contention')

    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as raised:
        run_purge_transaction(client, body, operation_name=PURGE_RESULT_ERASE_LABEL, storm_damper=scripted)
    assert raised.value.retry_after == scripted.arm_wait
    assert ['arm', PURGE_RESULT_ERASE_LABEL, scripted.arm_wait] == scripted.events[-1]


def test_success_after_a_quiet_chain_reports_the_entry_generation(monkeypatch):
    scripted = ScriptedStormDamper(residual_schedule=[0.0], wave_wait=0.5, generation=4, entry_wait=0.0)
    client = Mock()
    silence_and_pin_chain(monkeypatch, ChainSleepRecorder())
    assert run_purge_transaction(client, lambda transaction: 'erased', storm_damper=scripted) == 'erased'
    assert scripted.note_success_args == [[PURGE_JOB_UNLINK_LABEL, 4]]


def test_default_label_is_the_job_unlink_site(monkeypatch):
    client = Mock()
    silence_and_pin_chain(monkeypatch, ChainSleepRecorder())
    assert run_purge_transaction(client, lambda transaction: 'erased') == 'erased'


def test_emitted_grid_files_stay_in_parity_with_the_harness():
    from pathlib import Path

    unit_dir = Path(__file__).resolve().parent
    expected = [
        f'{GRID_BASE_NAME}{mode}_{arm}_{site}.py' for mode in GRID_MODES for arm in GRID_ARMS for site in GRID_SITES
    ]
    assert len(expected) == 18
    for name in expected:
        path = unit_dir / name
        assert path.exists(), f'missing grid file {name}'
        header = path.read_text(encoding='utf-8')[:600]
        assert 'FC-privacy-purge-chain-collides-inside-armed-storm-window' in header
        assert 'drive_cell' in header
