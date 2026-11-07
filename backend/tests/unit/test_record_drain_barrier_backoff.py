"""Barrier-blocked record_pending rows back off by age instead of re-reading every 60 s."""

import asyncio
import logging
from unittest.mock import Mock

import pytest

from tests.unit.test_batch_pipeline_scheduler import MemoryStore


@pytest.mark.parametrize('age,delay', [(0, 60), (599, 60), (600, 900), (86399, 900), (86400, 3600), (9e6, 3600)])
def test_barrier_retry_delay_steps(age, delay):
    from config.record_drain import barrier_retry_delay

    assert barrier_retry_delay(age) == delay


@pytest.fixture
def drained(monkeypatch):
    from utils.batch_pipeline import live

    monkeypatch.setenv('RECORD_DRAIN_CONCURRENCY', '1')
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'false')
    monkeypatch.setattr(live.time, 'time', lambda: 100000.0)

    def run(enqueued_at, error, env='on'):
        monkeypatch.setenv('RECORD_DRAIN_BARRIER_BACKOFF', env)
        store = MemoryStore()
        store.rows['jobs', 's'] = {
            'owner_id': 'synthetic-owner',
            'segment_id': 's',
            'state': 'record_pending',
            'available_at': 0,
            'enqueued_at': enqueued_at,
            'record_content_id': 'c0ffee' * 4,
        }

        async def admission(store, pending):
            raise error

        monkeypatch.setattr(live, 'admit_recording', admission)
        asyncio.run(live.drain_recordings(store))
        return store.rows['jobs', 's']['available_at'] - 100000.0

    return run, live


@pytest.mark.parametrize('enqueued_ago,delay', [(30, 60), (3600, 900), (2 * 86400, 3600)])
def test_open_barrier_backs_off_by_age(drained, enqueued_ago, delay):
    run, live = drained
    assert run(100000.0 - enqueued_ago, ValueError(live.BARRIER_NOT_CLOSED)) == delay


def test_other_admission_errors_keep_the_flat_retry(drained):
    run, _ = drained
    assert run(100000.0 - 2 * 86400, ValueError('invalid retained audio size')) == 60
    assert run(100000.0 - 2 * 86400, RuntimeError('store contention')) == 60


def test_kill_switch_restores_the_flat_retry(drained):
    run, live = drained
    assert run(100000.0 - 2 * 86400, ValueError(live.BARRIER_NOT_CLOSED), env='off') == 60
    assert run(100000.0 - 2 * 86400, ValueError(live.BARRIER_NOT_CLOSED)) == 3600


@pytest.mark.parametrize(
    'enqueued_at', [None, True, False, float('nan'), float('inf'), -float('inf'), 'bad', {}, 100001.0]
)
def test_unknown_or_future_enqueued_at_is_treated_as_young(drained, monkeypatch, enqueued_at):
    run, live = drained
    retry = Mock(wraps=live.barrier_retry_delay)
    monkeypatch.setattr(live, 'barrier_retry_delay', retry)
    assert run(enqueued_at, ValueError(live.BARRIER_NOT_CLOSED)) == 60
    retry.assert_called_once_with(0.0)


def test_barrier_text_matches_the_raise_site():
    from config.record_audio import BARRIER_NOT_CLOSED as shared_barrier, require_record_audio_barrier
    from utils.batch_pipeline.live import BARRIER_NOT_CLOSED

    with pytest.raises(ValueError) as raised:
        require_record_audio_barrier({'status': 'in_progress'})
    assert str(raised.value) == BARRIER_NOT_CLOSED == shared_barrier


def test_retry_line_carries_the_record_key_without_owner(drained, caplog):
    run, live = drained
    with caplog.at_level(logging.WARNING, logger=live.__name__):
        run(100000.0 - 30, ValueError(live.BARRIER_NOT_CLOSED))
    line = next(r.getMessage() for r in caplog.records if 'event=batch_live_admission outcome=retry' in r.getMessage())
    # The record content prefix is the same key the sync pending line logs.
    assert line.endswith(' record=' + ('c0ffee' * 4)[:16])
    assert 'synthetic-owner' not in line
