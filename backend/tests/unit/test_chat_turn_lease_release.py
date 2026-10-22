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
