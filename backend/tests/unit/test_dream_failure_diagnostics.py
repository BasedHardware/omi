"""Unknown pass failures expose class/stage, never exception payloads or owners."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from database import dream_turns
from tests.unit.test_dream_harness_runtime import runtime, store, UID, scripted
from utils import dream_agent, dream_capacity, dream_harness_transport


@pytest.mark.parametrize('boundary', ['reserve', 'settle'])
def test_other_failure_logs_class_and_turn_stage_without_payload(runtime, monkeypatch, caplog, boundary):
    def fail(*args, **kwargs):
        raise KeyError('synthetic private content ' + UID)

    monkeypatch.setattr(dream_turns, boundary, fail)
    report = asyncio.run(dream_agent.run_pass(UID, turn=scripted([True, True])))
    assert report['status'] == 'failed' and report['error_type'] == 'KeyError'
    assert report['turns'] == (0 if boundary == 'reserve' else 1)
    assert f'stage=turn_{boundary} exception_type=KeyError' in caplog.text
    assert 'error_type=other' not in caplog.text  # INFO metrics are below the default capture level.
    assert UID not in caplog.text and 'synthetic private content' not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize('after_wait', [False, True])
def test_drain_records_and_logs_failure_before_session(runtime, monkeypatch, caplog, after_wait):
    monkeypatch.setattr(dream_agent, 'concurrency', lambda: 1)
    monkeypatch.setattr(dream_capacity, 'available_model', AsyncMock(return_value='synthetic-model'))
    monkeypatch.setattr(dream_agent.dream_scheduler, 'candidates', lambda **kwargs: [UID])
    monkeypatch.setattr(dream_agent.asyncio, 'sleep', AsyncMock())
    outcomes = ([{'status': 'waiting'}] if after_wait else []) + [KeyError('private ' + UID)]
    monkeypatch.setattr(dream_agent, 'run_pass', AsyncMock(side_effect=outcomes))
    with caplog.at_level('INFO'):
        reports = asyncio.run(dream_agent.drain())
    assert reports[-1]['error_type'] == 'KeyError'
    assert 'stage=pass exception_type=KeyError' in caplog.text
    assert 'Dream status=failed' in caplog.text and 'error_type=other' in caplog.text
    assert UID not in caplog.text and 'private' not in caplog.text


def test_capacity_wait_is_not_logged_as_failure(runtime, monkeypatch, caplog):
    monkeypatch.setattr(
        dream_turns, 'reserve', lambda *a, **k: (_ for _ in ()).throw(dream_harness_transport.CapacityWait())
    )
    report = asyncio.run(dream_agent.run_pass(UID, turn=scripted([True, True])))
    assert report['status'] == 'waiting'
    assert 'Dream pass failure' not in caplog.text
