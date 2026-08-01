"""Projection failures must not abort unrelated work in the shared hourly job."""

import pytest

from utils.other import jobs


@pytest.mark.asyncio
async def test_projection_exception_does_not_skip_x_sync(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(jobs, 'should_run_daily_notification_job', lambda: False)
    monkeypatch.setattr(jobs, 'should_run_projection_job', lambda: True)
    monkeypatch.setattr(jobs, 'should_run_x_sync_job', lambda: True)

    async def fail_projection():
        calls.append('projection')
        raise RuntimeError('projection unavailable')

    async def run_x_sync():
        calls.append('x_sync')

    monkeypatch.setattr(jobs, 'start_cron_projection_job', fail_projection)
    monkeypatch.setattr(jobs, 'run_x_sync_job', run_x_sync)

    await jobs.start_job()

    assert calls == ['projection', 'x_sync']


@pytest.mark.asyncio
async def test_projection_base_exception_is_not_swallowed(monkeypatch):
    class FatalProjectionSignal(BaseException):
        pass

    monkeypatch.setattr(jobs, 'should_run_daily_notification_job', lambda: False)
    monkeypatch.setattr(jobs, 'should_run_projection_job', lambda: True)
    monkeypatch.setattr(jobs, 'should_run_x_sync_job', lambda: True)
    run_x_sync = pytest.fail

    async def fail_projection():
        raise FatalProjectionSignal('stop')

    monkeypatch.setattr(jobs, 'start_cron_projection_job', fail_projection)
    monkeypatch.setattr(jobs, 'run_x_sync_job', run_x_sync)

    with pytest.raises(FatalProjectionSignal, match='stop'):
        await jobs.start_job()
