"""Shared adapter mechanics; all tool sends are bound to the current reply sink."""

import asyncio
import time
from collections import OrderedDict

from langchain_core.tools import StructuredTool
from utils.executors import storage_executor, run_blocking
from utils.messaging.adapters.delivery import DeliveryLedger
from utils.messaging.adapters.media import ChatMediaStore, prepare_media
from utils.messaging.adapters.transport import Transport
from utils.messaging.delivery_context import send_sequence
from utils.messaging.identity import key
from utils.messaging.projection import surface_runtime


class BaseAdapter:
    channel: str

    def __init__(self, *, transport=None, ledger=None, media=None, sleep=asyncio.sleep):
        self.transport = transport or Transport()
        self.ledger = ledger or DeliveryLedger()
        self.media = media or ChatMediaStore()
        self.sleep = sleep
        self._rates = OrderedDict()

    async def admitted(self, message):
        await self.ledger.receive(message)

    async def prepare(self, message, uid, session, guard):
        if message.attachments or message.media:
            return await prepare_media(self, message, uid, session, guard)
        return message

    async def pace(self, chat, interval=1.05):
        # Local smooth pacing; provider 429 remains the cross-worker authority.
        now = time.monotonic()
        deadline = max(now, self._rates.get(chat, 0))
        self._rates[chat] = deadline + interval
        self._rates.move_to_end(chat)
        while len(self._rates) > 4096:
            self._rates.popitem(last=False)
        if deadline > now:
            await self.sleep(deadline - now)

    def operation(self, message, label):
        return key(message.provider_message_id, str(send_sequence.get()), label)

    def tools(self, sink):
        async def send_file(file_id: str) -> str:
            """Send an owned chat file to the user's currently linked chat."""
            runtime = surface_runtime.get()
            if runtime is None:
                raise PermissionError('No linked turn')
            artifact = await run_blocking(storage_executor, self.media.artifact, runtime.principal.uid, file_id)
            await sink.artifact(artifact)
            return 'File sent to your linked chat.'

        async def send_photo(file_id: str) -> str:
            """Send an owned photo to the user's currently linked chat."""
            runtime = surface_runtime.get()
            if runtime is None:
                raise PermissionError('No linked turn')
            artifact = await run_blocking(storage_executor, self.media.artifact, runtime.principal.uid, file_id)
            if not artifact.mime_type.startswith('image/'):
                raise ValueError('Photo required')
            await sink.artifact(artifact)
            return 'Photo sent to your linked chat.'

        async def send_voice(file_id: str) -> str:
            """Send an owned audio file to the user's currently linked chat."""
            runtime = surface_runtime.get()
            if runtime is None:
                raise PermissionError('No linked turn')
            artifact = await run_blocking(storage_executor, self.media.artifact, runtime.principal.uid, file_id)
            if not artifact.mime_type.startswith('audio/'):
                raise ValueError('Audio required')
            await sink.artifact(artifact)
            return 'Voice sent to your linked chat.'

        async def react(emoji: str) -> str:
            """React only to the user's message in the currently linked chat."""
            await sink.action('react', emoji)
            return 'Reaction sent.'

        funcs = [('send_file', send_file), ('send_photo', send_photo), ('send_voice', send_voice), ('react', react)]
        return tuple(StructuredTool.from_function(name=self.channel + '_' + name, coroutine=fn) for name, fn in funcs)

    async def owned_bytes(self, artifact):
        runtime = surface_runtime.get()
        if runtime is None:
            raise PermissionError('Artifact requires an admitted linked turn')
        runtime.principal.authorize(runtime.principal.uid)
        return await run_blocking(storage_executor, self.media.resolve, runtime.principal.uid, artifact)
