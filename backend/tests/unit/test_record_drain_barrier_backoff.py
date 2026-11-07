"""Barrier-blocked record_pending rows back off by age instead of re-reading every 60 s."""

import asyncio

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
    monkeypatch.setattr(live.time, 'time', lambda: 100000.0)

    def run(enqueued_at, error, env=None):
        if env is not None:
            monkeypatch.setenv('RECORD_DRAIN_BARRIER_BACKOFF', env)
        store = MemoryStore()
        store.rows['jobs', 's'] = {
            'owner_id': 'synthetic-owner',
            'segment_id': 's',
            'state': 'record_pending',
            'available_at': 0,
            'enqueued_at': enqueued_at,
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


def test_missing_enqueued_at_is_treated_as_young(drained):
    run, live = drained
    assert run(None, ValueError(live.BARRIER_NOT_CLOSED)) == 60


def test_barrier_text_matches_the_raise_site():
    from config.record_audio import require_record_audio_barrier
    from utils.batch_pipeline.live import BARRIER_NOT_CLOSED

    with pytest.raises(ValueError) as raised:
        require_record_audio_barrier({'status': 'in_progress'})
    assert str(raised.value) == BARRIER_NOT_CLOSED


def test_retry_line_groups_by_segment_prefix_without_owner(drained, caplog):
    import logging

    run, live = drained
    with caplog.at_level(logging.WARNING, logger=live.__name__):
        run(100000.0 - 30, ValueError(live.BARRIER_NOT_CLOSED))
    line = next(r.getMessage() for r in caplog.records if 'event=batch_live_admission outcome=retry' in r.getMessage())
    # Segment ids are content hashes: the prefix lets a log read count retries per recording.
    assert line.endswith(' segment=s')
    assert 'synthetic-owner' not in line
