"""The app chat turn lease is released when a reply stream ends early.

The mobile app's Stop (or a new message that replaces a running reply) disconnects
the stream. The lease must be freed then, or the next send gets 409 until it goes stale.
"""

import asyncio
import threading

from utils.chat_turn import _LeasedReplySink


class _Delegate:
    def response(self, stream, *, media_type):
        return stream


class _Store:
    def __init__(self):
        self.released = []
        self.event = threading.Event()

    def release(self, uid, surface, token):
        self.released.append((uid, surface, token))
        self.event.set()


async def _frames():
    yield 'data: one'
    yield 'data: two'
    yield 'done: x'


def test_full_stream_releases_the_lease():
    store = _Store()
    body = _LeasedReplySink(_Delegate(), store, 'uid-1', 'tok-1').response(_frames(), media_type='text/event-stream')

    async def consume():
        return [frame async for frame in body]

    assert asyncio.run(consume()) == ['data: one', 'data: two', 'done: x']
    assert store.released == [('uid-1', 'app', 'tok-1')]


def test_stream_closed_early_still_releases_the_lease():
    store = _Store()
    body = _LeasedReplySink(_Delegate(), store, 'uid-1', 'tok-1').response(_frames(), media_type='text/event-stream')

    async def stop_after_first_frame():
        assert await body.__anext__() == 'data: one'
        await body.aclose()  # what Starlette does when the client disconnects

    asyncio.run(stop_after_first_frame())
    assert store.event.wait(timeout=1.0)
    assert store.released == [('uid-1', 'app', 'tok-1')]


def test_cancelled_stream_releases_the_lease():
    store = _Store()

    async def slow():
        yield 'data: one'
        await asyncio.sleep(30)
        yield 'never'

    body = _LeasedReplySink(_Delegate(), store, 'uid-1', 'tok-1').response(slow(), media_type='text/event-stream')

    async def cancel_mid_stream():
        async def drain():
            async for _ in body:
                pass

        task = asyncio.create_task(drain())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(cancel_mid_stream())
    assert store.event.wait(timeout=1.0)
    assert store.released == [('uid-1', 'app', 'tok-1')]


def test_resend_right_after_stop_waits_briefly_for_the_released_lease(monkeypatch):
    from fastapi import HTTPException

    from utils import chat_turn

    calls, sleeps = [], []

    def acquire(uid):
        calls.append(uid)
        if len(calls) < 3:
            raise RuntimeError('App surface already has an active turn')
        return 'store', 'token'

    monkeypatch.setattr(chat_turn.app_awareness, 'acquire', acquire)
    assert chat_turn._acquire_app_turn('uid-1', sleep=sleeps.append) == ('store', 'token')
    assert len(calls) == 3 and sleeps == [chat_turn.APP_TURN_ACQUIRE_WAIT_SECONDS] * 2

    def busy(uid):
        raise RuntimeError('App surface already has an active turn')

    monkeypatch.setattr(chat_turn.app_awareness, 'acquire', busy)
    try:
        chat_turn._acquire_app_turn('uid-1', sleep=lambda _: None)
    except HTTPException as error:
        assert error.status_code == 409
    else:
        raise AssertionError('a turn still running must answer 409')


def test_release_after_stop_tolerates_a_lease_already_taken_over():
    class _TakenOver(_Store):
        def release(self, uid, surface, token):
            raise PermissionError('Lost surface lease')

    sink = _LeasedReplySink(_Delegate(), _TakenOver(), 'uid-1', 'tok-old')
    sink._release_after_stop()  # must not raise into the executor's error log
