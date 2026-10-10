"""All adapter sends pass through the same policy, including drafts and artifacts."""

from datetime import datetime, timezone

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
        self.adapter, self.message, self.kind, self.guard = adapter, message, kind, guard
        self.buffer = ''

    def response(self, stream, *, media_type):
        return stream

    async def _send(self, *, text=None, artifact=None, draft=False):
        authorize_send(self.adapter.capabilities, self.kind, self.message.received_at)
        if text is not None and len(text) > self.adapter.capabilities.max_text_len:
            raise ValueError('Adapter renderer exceeded max_text_len')
        if self.guard is not None:
            await self.guard()  # link revocation, account deletion, future rate/ratio admission
        await self.adapter.send(self.message, text=text, artifact=artifact, draft=draft)

    async def text(self, delta):
        self.buffer += delta
        if self.adapter.capabilities.streaming != 'none':
            for part in self.adapter.render(self.buffer):
                await self._send(text=part, draft=True)

    async def artifact(self, artifact: Artifact):
        if artifact.mime_type not in self.adapter.capabilities.media_out:
            raise PermissionError('Unsupported outbound media')
        await self._send(artifact=artifact)

    async def finish(self, text):
        for part in self.adapter.render(text):
            await self._send(text=part)
