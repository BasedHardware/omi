"""ASGI response for user-data exports with disconnect-driven cancellation.

Starlette's ``StreamingResponse`` only listens for ``http.disconnect`` under
ASGI specs below 2.4, and iterating a synchronous generator through a thread
pool gives no deterministic way to close it mid-flight. A portability export
runs real Firestore reads per chunk, so a client that disconnects must stop
further reads and close the source — otherwise the worker keeps walking the
user's collections after nobody is listening.

The disconnect listener runs in an anyio task group for every ASGI spec
version, sets the read context's cancellation event before cancelling the
group, and the body loop shields the per-``next()`` worker call so an in-flight
read always settles before the source is closed. ``close()`` is never invoked
concurrently with ``next()``.
"""

from __future__ import annotations

import threading
from typing import Callable, Iterator, List, Optional

import anyio
import anyio.to_thread
from starlette.responses import StreamingResponse
from starlette.types import Message, Receive, Scope, Send

from utils.other.portability_read import PortabilityReadContext, PortabilityReadCancelled

_END = object()


class DataExportStreamingResponse(StreamingResponse):
    """StreamingResponse driving a sync export iterator with disconnect cancellation."""

    def __init__(
        self,
        uid: str,
        *,
        iterator_factory: Callable[..., Iterator[str]],
        status_code: int = 200,
        headers: Optional[dict] = None,
        media_type: str = 'application/json',
    ) -> None:
        self._cancelled = threading.Event()
        self.read_context = PortabilityReadContext(cancelled=self._cancelled)
        self._source = iterator_factory(uid, read_context=self.read_context)
        super().__init__(self._source, status_code=status_code, headers=headers, media_type=media_type)

    def _next_chunk(self):
        try:
            return next(self._source)
        except StopIteration:
            return _END

    def _close_source(self) -> None:
        close = getattr(self._source, 'close', None)
        if callable(close):
            close()

    async def _stream_body(self, send: Send) -> None:
        try:
            await send(
                {
                    'type': 'http.response.start',
                    'status': self.status_code,
                    'headers': self.raw_headers,
                }
            )
            while True:
                self.read_context.check()
                chunk = await anyio.to_thread.run_sync(self._next_chunk)
                self.read_context.check()
                if chunk is _END:
                    break
                if isinstance(chunk, str):
                    chunk = chunk.encode(self.charset)
                await send({'type': 'http.response.body', 'body': chunk, 'more_body': True})
            await send({'type': 'http.response.body', 'body': b'', 'more_body': False})
        except PortabilityReadCancelled:
            pass
        except BaseException:
            self._cancelled.set()
            raise
        finally:
            with anyio.CancelScope(shield=True):
                await anyio.to_thread.run_sync(self._close_source)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        captured: List[BaseException] = []
        async with anyio.create_task_group() as task_group:

            async def _listen_for_disconnect() -> None:
                try:
                    while True:
                        message: Message = await receive()
                        if message['type'] == 'http.disconnect':
                            break
                except BaseException as exc:
                    if isinstance(exc, anyio.get_cancelled_exc_class()):
                        raise
                self._cancelled.set()
                task_group.cancel_scope.cancel()

            task_group.start_soon(_listen_for_disconnect)
            try:
                await self._stream_body(send)
            except BaseException as exc:
                captured.append(exc)
            finally:
                task_group.cancel_scope.cancel()

        if captured:
            error = captured[0]
            if self._cancelled.is_set() and isinstance(error, anyio.get_cancelled_exc_class()):
                return
            raise error


__all__ = ['DataExportStreamingResponse']
