"""Cross-identity: the lane runner and the purge runner are one doctrine.

The purge chain (run 338) and the four joined batch lanes (this change) ride
the same ``run_batch_pipeline_transaction`` doctrine. Each test drives the
same cell through ``database.batch_pipeline_purge.run_purge_transaction``
and ``database.batch_pipeline_store.run_batch_pipeline_transaction`` with
independent scripted dampers and freezes that the observables agree exactly:
same rung waits, same damper conversation, same exhaustion stamp, same
log lines (up to each lane's own logger) and the same bare schedule while a
damper is dormant. A drift between the two entries would mean the purge
chain and the joined lanes space storms differently — one lane re-striking
inside the window the other armed.

Failure-Class: FC-bare-batch-pipeline-lanes-collide-inside-armed-storm-window
"""

import logging

import database.batch_pipeline_purge as purge
import database.batch_pipeline_store as storage
from tests.unit import batch_lane_storm_gate_grid_harness as lane_harness
from tests.unit import batch_purge_storm_gate_grid_harness as purge_harness


def _paired_drive(monkeypatch, caplog, **params):
    """Drive one cell through both runners; return the two outcome freezes."""
    caplog.set_level(logging.INFO, logger=lane_harness.LANE_LOGGER)
    lane = lane_harness.drive_cell(monkeypatch, caplog, **params)
    caplog.clear()
    caplog.set_level(logging.INFO, logger=purge_harness.PURGE_LOGGER)
    book = purge_harness.drive_cell(monkeypatch, caplog, **params)
    return lane, book


def _same_schedule(lane, book):
    """Every shared observable except the body's own return token."""
    lane_rest = {key: value for key, value in lane.items() if key != 'result'}
    book_rest = {key: value for key, value in book.items() if key != 'result'}
    return lane_rest == book_rest


def test_identity_live_ladder_same_rungs_and_damper_conversation(monkeypatch, caplog):
    lane, book = _paired_drive(
        monkeypatch,
        caplog,
        label='batch_privacy_generation_advance',
        aborts=2,
        entry_wait=0.4,
        residual_schedule=(0.3, 0.0, 0.6),
        wave_wait=1.25,
        generation=4,
    )
    assert lane['result'] == 'joined'
    assert book['result'] == 'erased'
    assert _same_schedule(lane, book)


def test_identity_dormant_damper_is_the_bare_ladder_for_both(monkeypatch, caplog):
    lane, book = _paired_drive(
        monkeypatch,
        caplog,
        label='batch_voice_evidence_receipt_read',
        aborts=1,
        damper_mode='dormant_none',
    )
    assert lane['result'] == 'joined'
    assert book['result'] == 'erased'
    assert _same_schedule(lane, book)


def test_identity_exhaustion_stamps_the_same_window(monkeypatch, caplog):
    lane, book = _paired_drive(
        monkeypatch,
        caplog,
        label='batch_recovery_fenced_revoke',
        aborts=5,
        residual_schedule=(0.6,),
        wave_wait=0.5,
        arm_window=1.25,
    )
    assert lane['raised'] == book['raised'] == 'attempts_exhausted'
    assert lane['retry_after'] == book['retry_after'] == 1.25
    assert _same_schedule(lane, book)


def test_identity_arm_window_zero_stamps_zero(monkeypatch, caplog):
    lane, book = _paired_drive(
        monkeypatch,
        caplog,
        label='batch_quarantine_recovery_cancel',
        aborts=5,
        arm_window=0.0,
    )
    assert lane['retry_after'] == book['retry_after'] == 0.0
    assert _same_schedule(lane, book)


def test_identity_hostile_peek_collapses_to_the_bare_rungs(monkeypatch, caplog):
    lane, book = _paired_drive(
        monkeypatch,
        caplog,
        label='batch_privacy_purge_finish',
        aborts=3,
        residual_schedule=(0.9, 0.6, 0.2),
        wave_wait=2.5,
        hostile_peek=True,
    )
    assert _same_schedule(lane, book)


def test_identity_backoff_lines_agree_word_for_word(monkeypatch, caplog):
    lane, book = _paired_drive(
        monkeypatch,
        caplog,
        label='batch_purge_result_erase',
        aborts=4,
        entry_wait=1.5,
        residual_schedule=(0.9, 0.6, 0.2, 0.0),
        wave_wait=1.25,
    )
    assert lane['records'] and lane['records'] == book['records']


def test_identity_shares_the_engine_shape_constants():
    assert lane_harness.WAVE_ENGAGEMENT_ATTEMPT == purge_harness.WAVE_ENGAGEMENT_ATTEMPT
    assert lane_harness.STORM_DAMPER_CAP_SECONDS == purge_harness.STORM_DAMPER_CAP_SECONDS
    assert lane_harness.STORM_DAMPER_BASE_SECONDS == purge_harness.STORM_DAMPER_BASE_SECONDS
    assert lane_harness.PINNED_JITTER_DRAW == purge_harness.PINNED_JITTER_DRAW


def test_identity_purge_entry_is_the_shared_runner():
    import inspect

    purge_body = inspect.getsource(purge.run_purge_transaction)
    assert 'run_batch_pipeline_transaction' in purge_body
    assert storage.run_batch_pipeline_transaction is not purge.run_purge_transaction
    assert 'FC-privacy-purge-chain-collides-inside-armed-storm-window' in purge.run_purge_transaction.__doc__
