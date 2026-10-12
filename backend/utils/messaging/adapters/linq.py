"""Linq implementation behind a replaceable iMessage provider interface."""

import base64
import hashlib
import hmac
import json
import re
import time
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import quote, urlparse

from utils.messaging.adapters.base import BaseAdapter
from utils.messaging.adapters.media import MEDIA_TYPES
from utils.messaging.adapters.rendering import plain, split_text, inline_item_links
from utils.observability.fallback import record_fallback
from utils.messaging.delivery_context import send_reply_target, send_first_chunk
from utils.messaging.adapters.transport import request_json, ProviderError
from utils.messaging.contracts import ChannelCapabilities, ChannelMessage, InboundAttachment
from utils.messaging.turn_context import bound_provider_clock, parse_provider_instant

_LINK_CODE = re.compile(r'(?<![A-Fa-f0-9])([A-Fa-f0-9]{32})(?![A-Fa-f0-9])')


def _message_clock(data, *, now=None):
    now = now or datetime.now(timezone.utc)
    nested = data.get('message') if isinstance(data.get('message'), dict) else None
    values = []
    if nested is not None:
        values.extend((nested.get('sent_at'), nested.get('created_at')))
    values.extend((data.get('sent_at'), data.get('received_at')))
    for value in values:
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            return bound_provider_clock(parse_provider_instant(value), now=now)
        except ValueError:
            continue
    return now


def _link_code(text: str) -> str | None:
    """One 32-hex code anywhere in the text. Extra codes are not a link."""
    found = _LINK_CODE.findall(text or '')
    if len(found) != 1:
        return None
    return found[0].upper()


class IMessageProvider(Protocol):
    name: str

    def verify(self, body, headers) -> bool: ...
    def parse(self, body) -> tuple[ChannelMessage, ...]: ...
    async def send(self, chat, parts, operation, *, reply_to=None) -> dict[str, Any]: ...
    async def typing(self, chat, active) -> None: ...
    async def react(self, message_id, reaction) -> dict[str, Any]: ...
    async def upload(self, artifact, data) -> str: ...
    async def download(self, attachment) -> bytes: ...
    async def contact(self, chat) -> dict[str, Any]: ...


class LinqProvider:
    name = 'linq'
    base_url = 'https://api.linqapp.com/api/partner/v3'

    def __init__(self, api_key, webhook_secret, *, transport, sleep, clock=time.time, upload_hosts=()):
        if not api_key or not webhook_secret.startswith('whsec_'):
            raise ValueError('Linq configuration missing')
        try:
            self._secret = base64.b64decode(webhook_secret[6:], validate=True)
        except ValueError:
            raise ValueError('Invalid Linq signing secret') from None
        if len(self._secret) < 16:
            raise ValueError('Linq signing secret too short')
        self._key = api_key
        self.transport, self.sleep, self.clock = transport, sleep, clock
        self.upload_hosts = set(upload_hosts)

    def verify(self, body, headers):
        headers = {k.lower(): v for k, v in headers.items()}
        try:
            stamp = headers['webhook-timestamp']
            webhook_id = headers['webhook-id']
            if not webhook_id or abs(self.clock() - int(stamp)) > 300:
                return False
            content = webhook_id.encode() + b'.' + stamp.encode() + b'.' + body
            expected = base64.b64encode(hmac.new(self._secret, content, hashlib.sha256).digest()).decode()
            return any(
                hmac.compare_digest(expected.encode(), sig[3:].encode())
                for sig in headers['webhook-signature'].split()
                if sig.startswith('v1,')
            )
        except (KeyError, ValueError, TypeError, AttributeError):
            return False

    def parse(self, body):
        event = json.loads(body)
        if event.get('event_type') != 'message.received':
            return ()
        data = event['data']
        version = event.get('webhook_version')
        if version == '2026-02-03':
            chat, sender = data['chat'], data['sender_handle']
            if chat.get('is_group') is not False or data.get('direction') != 'inbound' or sender.get('is_me'):
                return ()
            chat_id, external_id, message_id = chat['id'], sender['handle'], data['id']
            parts = data['parts']
        elif version == '2025-01-01':
            if data.get('is_group') is not False or data.get('is_from_me') is not False:
                return ()
            chat_id, external_id, message_id = data['chat_id'], data['from'], data['message']['id']
            parts = data['message']['parts']
        else:
            raise ValueError('Unsupported Linq webhook version')
        text = '\n'.join(str(p['value']) for p in parts if p['type'] in ('text', 'link'))
        command = text.strip().lower()
        proof = _link_code(text)
        attachments = tuple(
            InboundAttachment(
                p['url'],
                p.get('filename', 'attachment'),
                p.get('mime_type', 'application/octet-stream'),
                p.get('size_bytes', 0),
                p['type'] == 'voice_memo',
            )
            for p in parts
            if p['type'] in ('media', 'voice_memo')
        )
        # Message ID, not delivery/event ID: two received events for one message
        # must not buy duplicate ratio credit or re-execute a write.
        # sent_at is the user's send time. Webhook created_at and local now() are
        # delivery/processing clocks and must not anchor a relative reminder.
        return (
            ChannelMessage(
                'imessage',
                self.name,
                external_id,
                chat_id,
                message_id,
                text,
                _message_clock(data),
                reply_to=message_id,
                link_proof=proof,
                unlink=command in ('unlink', '/unlink', 'stop', 'unsubscribe'),
                command='help' if command in ('help', '/help') else ('undo' if command == 'undo' else None),
                attachments=attachments,
            ),
        )

    async def api(self, method, path, *, body=None, idempotent=False, before_request=None):
        return await request_json(
            self.transport,
            method,
            self.base_url + path,
            headers={'Authorization': 'Bearer ' + self._key},
            json=body,
            idempotent=idempotent,
            sleep=self.sleep,
            before_request=before_request,
        )

    async def send(self, chat, parts, operation, *, reply_to=None):
        message = {'parts': parts, 'idempotency_key': operation, 'preferred_service': 'iMessage'}
        if reply_to:
            message['reply_to'] = {'message_id': reply_to}
        path = '/chats/' + quote(chat, safe='') + '/messages'

        async def prepare_thread():
            resolver = send_reply_target.get()
            if resolver is None or not send_first_chunk.get():
                return
            current = await resolver()
            if current:
                message['reply_to'] = {'message_id': current}
            else:
                message.pop('reply_to', None)

        try:
            return await self.api(
                'POST', path, body={'message': message}, idempotent=True, before_request=prepare_thread
            )
        except ProviderError as error:
            if not message.get('reply_to') or error.status_code not in (400, 404, 422):
                raise  # ambiguous delivery must not change the request or replay
            record_fallback(
                component='other', from_mode='threaded_reply', to_mode='plain_reply', reason='other', outcome='degraded'
            )
            message.pop('reply_to')
            message['idempotency_key'] = operation + ':unthreaded'
            return await self.api('POST', path, body={'message': message}, idempotent=True)

    async def typing(self, chat, active):
        await self.api('POST' if active else 'DELETE', '/chats/' + quote(chat, safe='') + '/typing', idempotent=True)

    async def react(self, message_id, reaction):
        if reaction not in ('love', 'like', 'dislike', 'laugh', 'emphasize', 'question'):
            raise ValueError('Unsupported tapback')
        return await self.api(
            'POST',
            '/messages/' + quote(message_id, safe='') + '/reactions',
            body={'operation': 'add', 'type': reaction},
        )

    async def contact(self, chat):
        return await self.api('POST', '/chats/' + quote(chat, safe='') + '/share_contact_card')

    async def download(self, attachment):
        return await self.transport.download(attachment.reference, allowed_hosts={'cdn.linqapp.com'})

    async def upload(self, artifact, data):
        result = await self.api(
            'POST',
            '/attachments',
            body={'filename': artifact.name, 'content_type': artifact.mime_type, 'size_bytes': len(data)},
        )
        parsed = urlparse(result['upload_url'])
        if parsed.scheme != 'https' or parsed.hostname not in self.upload_hosts or parsed.username or parsed.port:
            raise PermissionError('Upload host must be explicitly configured')
        from utils.messaging.delivery_context import send_guard

        if send_guard.get() is not None:
            await send_guard.get()()
        response = await self.transport.request(
            'PUT', result['upload_url'], content=data, headers=result['required_headers']
        )
        if response.status_code >= 300:
            raise ProviderError('Attachment upload failed')
        return result['attachment_id']


class IMessageAdapter(BaseAdapter):
    channel = 'imessage'

    def __init__(self, provider: IMessageProvider, *, max_ratio=3, contact_card=False, **kwargs):
        super().__init__(**kwargs)
        if not 1 <= max_ratio <= 5:
            raise ValueError('Invalid send/receive ratio')
        self.client, self.provider = provider, provider.name
        self.max_ratio, self.contact_card = max_ratio, contact_card
        self.capabilities = ChannelCapabilities(
            typing=True,
            reactions=True,
            max_text_len=1200,
            media_in=MEDIA_TYPES,
            media_out=tuple(m for m in MEDIA_TYPES if m != 'audio/ogg'),
            rate_limits={'chat_per_minute': 30, 'max_send_receive_ratio': max_ratio},
        )

    def verify_webhook(self, body, headers):
        return self.client.verify(body, headers)

    def parse(self, body):
        return self.client.parse(body)

    def render(self, text):
        return split_text(
            re.sub(r'https://h\.omi\.me/?(?=[\s).,!?#]|$)', 'Omi', plain(text)), self.capabilities.max_text_len
        )

    async def item_presentation(self, message, text, items):
        if len(items) > 1:
            return inline_item_links(text, items), None
        card = items[0]['url'] if items and await self.ledger.has_outbound(message) else None
        return text, card

    async def typing(self, message, active=True):
        await self.client.typing(message.external_chat_id, active)

    async def download(self, attachment):
        return await self.client.download(attachment)

    async def send(self, message, *, text=None, artifact=None, draft=False, link=None):
        if draft:
            return
        await self.pace(message.external_chat_id, 2.05)
        operation = self.operation(
            message,
            (
                ('link:' + link)
                if link
                else ('artifact:' + artifact.file_store_ref if artifact else 'text:' + (text or ''))
            ),
        )
        if not await self.ledger.begin(message, operation, ratio=self.max_ratio, retry_reserved=True):
            return
        if link:
            if not re.fullmatch(r'https://h\.omi\.me/(?:task|memory|conversation)/[^\s]+', link):
                raise ValueError('Item link required')
            parts = [{'type': 'link', 'value': link}]
        elif artifact:
            data = await self.owned_bytes(artifact)
            attachment_id = await self.client.upload(artifact, data)
            parts = [{'type': 'media', 'attachment_id': attachment_id}]
        else:
            parts = [{'type': 'text', 'value': text}]
        reply_to = await self.reply_target(message)
        result = await self.client.send(message.external_chat_id, parts, operation, reply_to=reply_to)
        provider_id = result.get('id') or result.get('message', {}).get('id')
        if not provider_id:
            raise ProviderError('Missing provider delivery receipt')
        await self.ledger.commit(message, operation, provider_id, message_sent=True)

    async def action(self, message, action, value):
        if action == 'contact' and not self.contact_card:
            raise PermissionError('Contact card not configured')
        if action not in ('react', 'contact'):
            raise ValueError('Unsupported iMessage action')
        await self.pace(message.external_chat_id, 2.05)
        operation = self.operation(message, action + ':' + value)
        if not await self.ledger.begin(message, operation, ratio=self.max_ratio):
            return
        if action == 'react':
            await self.client.react(message.reply_to, value)
        else:
            await self.client.contact(message.external_chat_id)
        await self.ledger.commit(message, operation, message.reply_to)

    def tools(self, sink):
        tools = super().tools(sink)
        if self.contact_card:
            from langchain_core.tools import StructuredTool

            async def share_contact() -> str:
                """Share the configured Omi contact card in the user's current chat."""
                await sink.action('contact', '')
                return 'Contact card shared.'

            tools += (StructuredTool.from_function(name='imessage_share_contact', coroutine=share_contact),)
        return tools
