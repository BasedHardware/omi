"""Own one staged voice-answer push independently of the SSE iterator lifetime."""

import asyncio
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable

import anyio
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
VOICE_ANSWER_NOTIFICATION_TIMEOUT_SECONDS = 2.0
VOICE_STREAM_CLOSE_TIMEOUT_SECONDS = 2.0
NotificationSend = Callable[[], Awaitable[int]]


class VoiceAnswerDelivery:
    """Register before done; dispatch once after the response send returns or fails."""

    def __init__(self) -> None:
        self._pending: tuple[str, NotificationSend] | None = None
        self._dispatched = False

    def register(self, message_id: str, send: NotificationSend) -> None:
        if self._pending is not None:
            if self._pending[0] != message_id:
                raise RuntimeError('A voice response may stage only one terminal answer')
            return
        self._pending = (message_id, send)

    async def dispatch(self) -> None:
        if self._dispatched or self._pending is None:
            return
        self._dispatched = True
        message_id, send = self._pending
        outcome, error_type = 'no_acceptance', 'none'
        try:
            async with asyncio.timeout(VOICE_ANSWER_NOTIFICATION_TIMEOUT_SECONDS):
                if await send() > 0:
                    outcome = 'accepted'
        except TimeoutError:
            # An executor request may still finish. Do not retry an uncertain send.
            outcome, error_type = 'indeterminate', 'TimeoutError'
        except Exception as error:
            outcome, error_type = 'failed', type(error).__name__[:64]
        logger.info('voice answer notification message_id=%s outcome=%s error_type=%s', message_id, outcome, error_type)
        if outcome in ('indeterminate', 'failed'):
            record_fallback(component='other', from_mode='none', to_mode='none', reason='other', outcome='degraded')


class VoiceAnswerStreamingResponse(StreamingResponse):
    """Finish the response-owned push even when ASGI disconnect skips BackgroundTask."""

    def __init__(self, content: AsyncGenerator[str, None], delivery: VoiceAnswerDelivery) -> None:
        super().__init__(content, media_type='text/event-stream')
        self._content = content
        self._delivery = delivery

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            with anyio.CancelScope(shield=True):
                await self._delivery.dispatch()

    async def stream_response(self, send: Send) -> None:
        try:
            await super().stream_response(send)
        finally:
            # Close in the iteration task: ASGI 2.0–2.3 uses an AnyIO child task,
            # and nested generators may own ContextVar tokens from that task.
            with anyio.CancelScope(shield=True):
                try:
                    async with asyncio.timeout(VOICE_STREAM_CLOSE_TIMEOUT_SECONDS):
                        await self._content.aclose()
                except Exception as error:
                    logger.warning('voice stream close error_type=%s', type(error).__name__[:64])
