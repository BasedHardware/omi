"""Regression tests for the proactive push loop.

The bug these exist for: `_push_loop` fetched a small window of action items and
trusted the server's ordering. `GET /v1/action-items` does **not** return
newest-first -- against the live account a freshly created task appeared at index
20 of 100, so a `limit=20` poll watched only the twenty *oldest* tasks. The loop
was a silent no-op: it never raised, never logged, and could never fire.

That failure mode is invisible to any test that stubs the endpoint as
newest-first, so these tests deliberately return items in an adversarial order.
"""

from __future__ import annotations

import asyncio

import pytest

import server


class _FakeOmi:
    """Serves action items in a hostile order, like the real endpoint does."""

    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.requested_limits: list[int] = []

    async def action_items(self, limit: int = 20) -> list[dict]:
        self.requested_limits.append(limit)
        return list(self.rows[:limit])


def _item(item_id: str, created_at: str, description: str = 'task', completed: bool = False) -> dict:
    return {
        'id': item_id,
        'created_at': created_at,
        'description': description,
        'completed': completed,
    }


@pytest.fixture
def collected(monkeypatch):
    """Capture everything broadcast to connected glasses apps."""
    sent: list[dict] = []

    async def fake_broadcast(payload: dict) -> None:
        sent.append(payload)

    monkeypatch.setattr(server, 'broadcast', fake_broadcast)
    # A non-empty client set, since the loop skips polling when nobody is connected.
    monkeypatch.setattr(server, '_clients', {object()})
    return sent


async def _run_push_loop(cycles: int, interval: float = 0.01) -> None:
    """Run the real loop for a bounded number of polls, then cancel it."""
    task = asyncio.create_task(server._push_loop())
    # Each cycle is one sleep + one poll; give it room without being flaky.
    await asyncio.sleep(interval * cycles * 6 + 0.15)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_new_task_outside_the_default_window_is_still_detected(monkeypatch, collected):
    """The exact live failure: the new task is not near the front of the response.

    Twenty-five old tasks are returned before the new one. With a `limit=20` fetch
    and no client-side sort, the new task is never even seen.
    """
    old = [_item(f'old-{i}', f'2026-07-0{i % 9 + 1}T00:00:00', f'old task {i}') for i in range(25)]
    fake = _FakeOmi(old)

    monkeypatch.setattr(server, 'omi', fake)
    monkeypatch.setenv('OMI_EVEN_PUSH_INTERVAL', '0.01')
    monkeypatch.setenv('OMI_EVEN_PUSH_WINDOW', '100')

    async def scenario() -> None:
        task = asyncio.create_task(server._push_loop())
        await asyncio.sleep(0.08)  # let the first pass seed the baseline
        # Arrives buried mid-list, exactly as the real endpoint delivered it.
        fake.rows.insert(20, _item('brand-new', '2026-07-27T12:00:00', 'Push regression check'))
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    await scenario()

    pushed = [p for p in collected if p.get('type') == 'push']
    assert pushed, 'a task created after startup must push even when buried in the response'
    assert 'Push regression check' in pushed[0]['text']
    # And the window must be large enough to have contained it.
    assert max(fake.requested_limits) >= 100


@pytest.mark.asyncio
async def test_preexisting_tasks_never_push(monkeypatch, collected):
    """Startup must not dump every existing task onto the display."""
    fake = _FakeOmi([_item(f'existing-{i}', f'2026-07-1{i}T00:00:00') for i in range(5)])
    monkeypatch.setattr(server, 'omi', fake)
    monkeypatch.setenv('OMI_EVEN_PUSH_INTERVAL', '0.01')

    await _run_push_loop(cycles=3)

    assert not [p for p in collected if p.get('type') == 'push']


@pytest.mark.asyncio
async def test_completed_tasks_do_not_push_but_are_still_marked_seen(monkeypatch, collected):
    """A task created already-completed is noise, and must not push twice later."""
    fake = _FakeOmi([_item('a', '2026-07-01T00:00:00')])
    monkeypatch.setattr(server, 'omi', fake)
    monkeypatch.setenv('OMI_EVEN_PUSH_INTERVAL', '0.01')

    async def scenario() -> None:
        task = asyncio.create_task(server._push_loop())
        await asyncio.sleep(0.08)
        fake.rows.append(_item('done-task', '2026-07-27T12:00:00', 'already done', completed=True))
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    await scenario()

    assert not [p for p in collected if p.get('type') == 'push']


@pytest.mark.asyncio
async def test_a_task_pushes_exactly_once(monkeypatch, collected):
    """Polling repeatedly must not re-announce the same task."""
    fake = _FakeOmi([_item('a', '2026-07-01T00:00:00')])
    monkeypatch.setattr(server, 'omi', fake)
    monkeypatch.setenv('OMI_EVEN_PUSH_INTERVAL', '0.01')

    async def scenario() -> None:
        task = asyncio.create_task(server._push_loop())
        await asyncio.sleep(0.08)
        fake.rows.append(_item('new', '2026-07-27T12:00:00', 'only once'))
        await asyncio.sleep(0.4)  # many further polls
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    await scenario()

    pushed = [p for p in collected if p.get('type') == 'push']
    assert len(pushed) == 1, f'expected exactly one push, got {len(pushed)}'


@pytest.mark.asyncio
async def test_poll_failure_does_not_kill_the_loop(monkeypatch, collected):
    """One bad poll must not silently end proactive push for the session."""
    calls = {'n': 0}
    rows = [_item('a', '2026-07-01T00:00:00')]

    class Flaky:
        async def action_items(self, limit: int = 20) -> list[dict]:
            calls['n'] += 1
            if calls['n'] == 2:
                raise RuntimeError('transient upstream failure')
            return list(rows)

    monkeypatch.setattr(server, 'omi', Flaky())
    monkeypatch.setenv('OMI_EVEN_PUSH_INTERVAL', '0.01')

    async def scenario() -> None:
        task = asyncio.create_task(server._push_loop())
        await asyncio.sleep(0.1)  # seed, then hit the failing poll
        rows.append(_item('after-failure', '2026-07-27T12:00:00', 'still alive'))
        await asyncio.sleep(0.25)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    await scenario()

    assert calls['n'] > 2, 'the loop stopped polling after a failure'
    pushed = [p for p in collected if p.get('type') == 'push']
    assert pushed and 'still alive' in pushed[0]['text']


def test_created_at_sort_key_tolerates_missing_values():
    """Rows without a timestamp must sort rather than raise."""
    rows = [{'id': 'a'}, {'id': 'b', 'created_at': '2026-07-27T00:00:00'}]
    rows.sort(key=server._created_at, reverse=True)
    assert rows[0]['id'] == 'b'  # dated item is newest; undated sorts oldest
