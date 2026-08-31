"""run_x_sync_job must not run its synchronous store read (list_sync_user_ids) on the event loop.

The periodic X sync coroutine offloads every storage call to db_executor via run_blocking; the
user-listing read had been left as a direct, blocking call on the loop, stalling other async work
while the query ran. This asserts the listing is dispatched through run_blocking(db_executor, ...).
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from utils import x_connector  # noqa: E402


@pytest.mark.anyio
async def test_run_x_sync_job_offloads_user_listing_to_db_executor(monkeypatch):
    calls = []

    async def fake_run_blocking(executor, func, *args, **kwargs):
        calls.append((executor, func))
        return func(*args, **kwargs)

    monkeypatch.setattr(x_connector, 'run_blocking', fake_run_blocking)
    monkeypatch.setattr(x_connector.x_sync_registry, 'list_sync_user_ids', lambda: [])

    result = await x_connector.run_x_sync_job()

    assert result == {'users': 0, 'synced': 0, 'new_posts': 0}
    assert calls, 'the user listing must be offloaded through run_blocking, not run on the event loop'
    executor, func = calls[0]
    assert func is x_connector.x_sync_registry.list_sync_user_ids
    assert executor is x_connector.db_executor
