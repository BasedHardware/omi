"""All adapter sends pass through the same policy, including drafts and artifacts."""

from datetime import datetime, timezone
import time
import logging

from utils.observability.fallback import record_fallback
from utils.messaging.delivery_context import send_reply_target, send_first_chunk

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
    def __init__(self, adapter, message, *, kind: SendClass = 'reply', guard=None, reply_target=None):
        self.adapter, self.message, self.guard = adapter, message, guard
        self.reply_target = reply_target
        self.kind: SendClass = kind
        self.buffer = ''
        self.sequence = 0
        self.last_draft = 0
        self.finished = False
        self.delivered_ids = []
        # A draft preview is visible to the user even though it is not a delivered message.
        self.drafted = False

    def response(self, stream, *, media_type):
        return stream

    async def _send(self, *, text=None, artifact=None, draft=False, link=None):
        authorize_send(self.adapter.capabilities, self.kind, self.message.received_at)
        if text is not None and len(text) > self.adapter.capabilities.max_text_len:
            raise ValueError('Adapter renderer exceeded max_text_len')
        if self.guard is not None:
            await self.guard()  # link revocation, account deletion, future rate/ratio admission
        from utils.messaging.delivery_context import send_sequence, send_guard

        token = send_sequence.set(self.sequence)
        guard_token = send_guard.set(self.guard)
        reply_token = send_reply_target.set(self.reply_target)
        try:
            provider_id = await self.adapter.send(
                self.message, text=text, artifact=artifact, draft=draft, **({'link': link} if link is not None else {})
            )
        finally:
            send_reply_target.reset(reply_token)
            send_guard.reset(guard_token)
            send_sequence.reset(token)
        if draft:
            self.drafted = True
        else:
            self.sequence += 1
            if provider_id:
                self.delivered_ids.append(str(provider_id))
        return provider_id

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
        # Stopping an existing indicator conveys no content and must still work
        # after revocation, entitlement loss, or expiry of the reply window.
        if not active:
            if self.adapter.capabilities.typing and hasattr(self.adapter, 'typing'):
                await self.adapter.typing(self.message, False)
            return
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
        if self.adapter.capabilities.streaming != 'none' and not getattr(self, 'drafts_disabled', False):
            if time.monotonic() - self.last_draft < 1:
                return
            # A temporary preview is one message, never a sequence of drafts
            # overwriting each other while a long answer is streaming.
            parts = self.adapter.render(self.buffer)
            if parts:
                try:
                    await self._send(text=parts[-1], draft=True)
                except PermissionError:
                    raise
                except Exception as error:
                    record_fallback(
                        component='other',
                        from_mode='channel_draft',
                        to_mode='final_reply',
                        reason='other',
                        outcome='degraded',
                    )
                    logging.getLogger(__name__).warning('Messaging draft skipped error_type=%s', type(error).__name__)
                    self.drafts_disabled = True
                self.last_draft = time.monotonic()

    async def artifact(self, artifact: Artifact):
        if artifact.mime_type not in self.adapter.capabilities.media_out:
            raise PermissionError('Unsupported outbound media')
        await self._send(artifact=artifact)

    async def finish(self, text):
        from utils.messaging.delivery_context import send_markup

        parts = self.adapter.render(text)
        markup = send_markup.get()
        token = send_markup.set(markup)
        chunk_token = send_first_chunk.set(True)
        try:
            for index, part in enumerate(parts):
                send_first_chunk.set(index == 0)
                send_markup.set(markup if index == len(parts) - 1 else None)
                await self._send(text=part)
        finally:
            send_first_chunk.reset(chunk_token)
            send_markup.reset(token)
        self.finished = True

    async def receipt(self, receipt):
        from utils.messaging.delivery_context import send_markup

        markup = self.adapter.receipt_buttons(receipt) if hasattr(self.adapter, 'receipt_buttons') else None
        token = send_markup.set(markup)
        chunk_token = send_first_chunk.set(True)
        try:
            parts = self.adapter.render(receipt.text)
            provider_id = None
            for index, part in enumerate(parts):
                send_first_chunk.set(index == 0)
                # Only the final part owns the button when a receipt must split.
                send_markup.set(markup if index == len(parts) - 1 else None)
                provider_id = await self._send(text=part)
            return provider_id
        finally:
            send_first_chunk.reset(chunk_token)
            send_markup.reset(token)

    async def edit_receipt(self, result):
        authorize_send(self.adapter.capabilities, self.kind, self.message.received_at)
        if self.guard is not None:
            await self.guard()
        if hasattr(self.adapter, 'edit_receipt'):
            from utils.messaging.delivery_context import send_guard

            token = send_guard.set(self.guard)
            try:
                await self.adapter.edit_receipt(self.message, result)
            finally:
                send_guard.reset(token)

    async def finish_payload(self, response):
        from utils.messaging.adapters.rendering import source_phrases, linked_items
        from utils.messaging.delivery_context import send_markup

        # Follow-up suggestions are not rendered on channels: a one-line provider
        # button truncates the question, and typing the next message is just as fast.
        markup = None
        items = linked_items(response)
        text = source_phrases(response['text'])
        card = None
        if hasattr(self.adapter, 'item_presentation'):
            text, card = await self.adapter.item_presentation(self.message, text, items)
        elif items:
            if hasattr(self.adapter, 'item_buttons'):
                markup = self.adapter.item_buttons(items)
            else:
                text += '\n' + '\n'.join(item['title'] + ': ' + item['url'] for item in items[:5])
        token = send_markup.set(markup)
        try:
            await self.finish(text)
            if card:
                chunk_token = send_first_chunk.set(False)
                try:
                    await self._send(link=card)
                except Exception as error:
                    # The accepted text remains the answer; previews are optional.
                    record_fallback(
                        component='other',
                        from_mode='imessage_link_card',
                        to_mode='text',
                        reason='other',
                        outcome='degraded',
                    )
                    logging.getLogger(__name__).warning(
                        'Messaging link card skipped error_type=%s', type(error).__name__
                    )
                finally:
                    send_first_chunk.reset(chunk_token)
        finally:
            send_markup.reset(token)
