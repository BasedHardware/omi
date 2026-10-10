"""All adapter sends pass through the same policy, including drafts and artifacts."""

from datetime import datetime, timezone
import time

from utils.messaging.contracts import Artifact, ChannelCapabilities, SendClass


def authorize_send(capabilities: ChannelCapabilities, kind: SendClass, last_inbound, *, now=None, template=False):
    now = now or datetime.now(timezone.utc)
    if kind not in ('reply', 'deferred_reply'):
        raise PermissionError('Omi-initiated delivery is disabled')
    if capabilities.user_must_initiate and last_inbound is None:
        raise PermissionError('User must initiate')
    if capabilities.free_reply_window is not None:
        if last_inbound is None or now - last_inbound > capabilities.free_reply_window:
            raise PermissionError('Reply window expired')
    if capabilities.outbound_template_required and not template:
        raise PermissionError('Outbound template required')


class ChannelReplySink:
    def __init__(self, adapter, message, *, kind: SendClass = 'reply', guard=None):
        self.adapter, self.message, self.guard = adapter, message, guard
        self.kind: SendClass = kind
        self.buffer = ''
        self.sequence = 0
        self.last_draft = 0

    def response(self, stream, *, media_type):
        return stream

    async def _send(self, *, text=None, artifact=None, draft=False):
        authorize_send(self.adapter.capabilities, self.kind, self.message.received_at)
        if text is not None and len(text) > self.adapter.capabilities.max_text_len:
            raise ValueError('Adapter renderer exceeded max_text_len')
        if self.guard is not None:
            await self.guard()  # link revocation, account deletion, future rate/ratio admission
        from utils.messaging.delivery_context import send_sequence, send_guard

        token = send_sequence.set(self.sequence)
        guard_token = send_guard.set(self.guard)
        try:
            await self.adapter.send(self.message, text=text, artifact=artifact, draft=draft)
        finally:
            send_guard.reset(guard_token)
            send_sequence.reset(token)
        if not draft:
            self.sequence += 1

    async def action(self, action, value):
        authorize_send(self.adapter.capabilities, self.kind, self.message.received_at)
        if self.guard is None:
            raise PermissionError('Surface actions require a linked turn')
        await self.guard()
        from utils.messaging.delivery_context import send_sequence, send_guard

        token = send_sequence.set(self.sequence)
        guard_token = send_guard.set(self.guard)
        try:
            await self.adapter.action(self.message, action, value)
        finally:
            send_guard.reset(guard_token)
            send_sequence.reset(token)
        self.sequence += 1

    async def typing(self, active=True):
        authorize_send(self.adapter.capabilities, self.kind, self.message.received_at)
        if self.guard is not None:
            await self.guard()
        if self.adapter.capabilities.typing and hasattr(self.adapter, 'typing'):
            from utils.messaging.delivery_context import send_guard

            token = send_guard.set(self.guard)
            try:
                await self.adapter.typing(self.message, active)
            finally:
                send_guard.reset(token)

    async def text(self, delta):
        self.buffer += delta
        if self.adapter.capabilities.streaming != 'none':
            if time.monotonic() - self.last_draft < 1:
                return
            # A temporary preview is one message, never a sequence of drafts
            # overwriting each other while a long answer is streaming.
            parts = self.adapter.render(self.buffer)
            if parts:
                await self._send(text=parts[-1], draft=True)
                self.last_draft = time.monotonic()

    async def artifact(self, artifact: Artifact):
        if artifact.mime_type not in self.adapter.capabilities.media_out:
            raise PermissionError('Unsupported outbound media')
        await self._send(artifact=artifact)

    async def finish(self, text):
        for part in self.adapter.render(text):
            await self._send(text=part)

    async def finish_payload(self, response):
        from utils.messaging.adapters.rendering import source_phrases
        from utils.messaging.delivery_context import send_markup

        markup = None
        if hasattr(self.adapter, 'buttons'):
            suggestions = response.get('follow_up_suggestions', ())
            if not suggestions:
                suggestions = [
                    block.get('text', '')
                    for block in response.get('content_blocks', ())
                    if block.get('type') == 'followUp'
                ]
            markup = self.adapter.buttons(suggestions)
        token = send_markup.set(markup)
        try:
            await self.finish(
                source_phrases(response['text'], response.get('conversations', response.get('memories', ())))
            )
        finally:
            send_markup.reset(token)
