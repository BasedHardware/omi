"""Tests for capture surviving all-day wear.

Capture is meant to run for a whole day on a head-worn device, so a dropped
socket is routine, not exceptional: Wi-Fi roams between APs, the laptop sleeps,
and the server itself closes an idle socket with 1001 after 90s. Originally any
of those ended capture permanently and near-silently -- the session went inactive
and audio was accepted into a queue nobody was draining.

The reconnect logic distinguishes two failures that look identical at the socket
layer but are not:

* **Never connected** -- a bad URL or a revoked token. Retrying forever hides a
  configuration error, so this gives up quickly and records why.
* **Connected, then dropped** -- a network blip. This retries with backoff for as
  long as capture is wanted.

These tests pin that distinction, because collapsing the two is the natural
refactor and it breaks all-day wear.
"""

from __future__ import annotations

import asyncio

import pytest

import capture
from capture import CaptureSession


class _FakeAuth:
    def __init__(self) -> None:
        self.header_calls = 0

    async def auth_header(self) -> dict[str, str]:
        self.header_calls += 1
        # A distinct token per call, so a reconnect that reuses a stale header
        # is detectable.
        return {'Authorization': f'Bearer token-{self.header_calls}'}


class _FakeSocket:
    """A socket that yields nothing and then dies, or blocks until cancelled."""

    def __init__(self, die_after: float | None) -> None:
        self.die_after = die_after
        self.sent: list = []
        self.headers_seen: dict | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def send(self, payload):
        self.sent.append(payload)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.die_after is not None:
            await asyncio.sleep(self.die_after)
            raise ConnectionResetError('socket closed by peer')
        await asyncio.sleep(3600)
        raise StopAsyncIteration


def _install_connect(monkeypatch, sockets: list, record: list) -> None:
    """Hand out `sockets` in order; raise once the list is exhausted."""
    index = {'n': 0}

    def connect(url, additional_headers=None, **kwargs):
        record.append(additional_headers)
        i = index['n']
        index['n'] += 1
        if i >= len(sockets):
            raise ConnectionRefusedError('no more sockets')
        result = sockets[i]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(capture.websockets, 'connect', connect)


def _session(auth=None) -> CaptureSession:
    return CaptureSession(auth or _FakeAuth(), 'https://api.omi.me')


@pytest.mark.asyncio
async def test_a_drop_after_a_successful_connect_reconnects(monkeypatch):
    """The all-day case: one good connection, a blip, then keep going."""
    headers_seen: list = []
    _install_connect(
        monkeypatch,
        [_FakeSocket(die_after=0.05), _FakeSocket(die_after=None)],
        headers_seen,
    )
    monkeypatch.setattr(capture, '_MAX_RECONNECT_DELAY', 0.01)

    session = _session()
    await session.start()
    await asyncio.sleep(0.5)

    assert session.active is True, 'capture must survive a transient drop'
    assert session.stats.reconnects >= 1
    assert len(headers_seen) >= 2

    session.active = False
    session._task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await session._task


@pytest.mark.asyncio
async def test_reconnect_mints_a_fresh_auth_header(monkeypatch):
    """An ID token lasts an hour; an all-day session outlives it.

    Reusing the header captured at start would make every reconnect after the
    first hour fail with 401 forever.
    """
    headers_seen: list = []
    auth = _FakeAuth()
    _install_connect(
        monkeypatch,
        [_FakeSocket(die_after=0.05), _FakeSocket(die_after=None)],
        headers_seen,
    )
    monkeypatch.setattr(capture, '_MAX_RECONNECT_DELAY', 0.01)

    session = _session(auth)
    await session.start()
    await asyncio.sleep(0.5)

    assert len(headers_seen) >= 2
    assert headers_seen[0] != headers_seen[1], 'reconnect reused a stale token'

    session.active = False
    session._task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await session._task


@pytest.mark.asyncio
async def test_a_socket_that_never_connects_gives_up(monkeypatch):
    """A bad URL or revoked token must surface, not retry silently forever."""
    _install_connect(monkeypatch, [], [])
    monkeypatch.setattr(capture, '_INITIAL_CONNECT_DELAY', 0.01)

    session = _session()
    await session.start()
    await asyncio.wait_for(session._task, timeout=3)

    assert session.active is False
    assert session.stats.last_error is not None
    assert 'ConnectionRefusedError' in session.stats.last_error
    # Bounded: it must not have burned through a long retry schedule.
    assert session.stats.reconnects < capture._INITIAL_CONNECT_ATTEMPTS


@pytest.mark.asyncio
async def test_stop_during_a_reconnect_backoff_ends_promptly(monkeypatch):
    """Turning capture off while it is waiting to retry must not hang."""
    _install_connect(monkeypatch, [_FakeSocket(die_after=0.05)], [])
    monkeypatch.setattr(capture, '_MAX_RECONNECT_DELAY', 0.05)
    monkeypatch.setattr(capture, '_FLUSH_SILENCE_FRAMES', 1)
    monkeypatch.setattr(capture, '_FLUSH_SETTLE_SECONDS', 0.01)

    session = _session()
    await session.start()
    await asyncio.sleep(0.2)  # let it drop and enter backoff

    await asyncio.wait_for(session.stop(finalize=False), timeout=5)
    assert session.active is False


@pytest.mark.asyncio
async def test_a_cancelled_inner_task_is_not_mistaken_for_a_crash(monkeypatch):
    """`Task.exception()` re-raises on a cancelled task.

    Reading it during teardown made a routine cancellation look like the session
    itself being cancelled, which propagated out of the reconnect loop.
    """
    _install_connect(
        monkeypatch,
        [_FakeSocket(die_after=0.05), _FakeSocket(die_after=None)],
        [],
    )
    monkeypatch.setattr(capture, '_MAX_RECONNECT_DELAY', 0.01)

    session = _session()
    await session.start()
    await asyncio.sleep(0.4)

    # Survived the first socket's teardown rather than dying with it.
    assert session.active is True

    session.active = False
    session._task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await session._task
