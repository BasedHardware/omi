"""Held re-drive telemetry counts committed transitions without per-unit flag logs."""

import logging
from unittest.mock import Mock

import pytest

from config import backlog_state_machine as sm
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from tests.unit.test_backlog_state_machine import defaults, transitions  # noqa: F401
from utils.batch_pipeline import held_dead_letter as sweep


@pytest.mark.parametrize('switch', ['true', 'false'])
def test_counter_flag_read_does_not_log_per_unit(monkeypatch, caplog, switch):
    monkeypatch.setenv(sm.HELD_REDRIVE_COUNTER_SWITCH, switch)
    with caplog.at_level(logging.INFO):
        for _ in range(3):
            assert sm.held_redrive_counter_enabled() is (switch == 'true')
    assert not any(sm.HELD_REDRIVE_COUNTER_SWITCH in record.message for record in caplog.records)


@pytest.mark.parametrize('expired_at', [None, True, float('nan'), 86400, 1])
@pytest.mark.parametrize('failure', [None, BatchPrivacyBlocked, ProjectionBlocked, RuntimeError])
def test_nightly_skipped_or_failed_candidates_never_emit(monkeypatch, expired_at, failure):
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'true')
    store = Mock()
    store.run.side_effect = lambda fn: fn(Mock(get=Mock(return_value={})))
    runner = sweep.HeldDeadLetter(store)
    candidate = {'held_expired_at': expired_at, 'held_redrives': sm.MAX_HELD_REDRIVES}
    monkeypatch.setattr(sweep, 'held_candidates', lambda *a, **k: [])
    monkeypatch.setattr(sweep, 'dead_held_candidates', lambda *a, **k: [('bad', candidate)])
    requeue = Mock(return_value=False, side_effect=failure)
    monkeypatch.setattr(runner.recovery, 'requeue_quarantined', requeue)
    before = transitions('held_redrive_budget_spent')
    assert runner.tick(86400)['requeued'] == 0
    assert transitions('held_redrive_budget_spent') == before
    assert requeue.call_count == (1 if expired_at == 1 and expired_at is not True else 0)
