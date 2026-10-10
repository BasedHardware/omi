"""Official Telegram Bot API adapter; private, non-bot senders only."""

import hmac
import json
import re
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import quote

from utils.messaging.adapters.base import BaseAdapter
from utils.messaging.delivery_context import send_markup
from utils.messaging.adapters.media import MEDIA_TYPES
from utils.messaging.adapters.rendering import telegram
from utils.messaging.adapters.transport import request_json
from utils.messaging.contracts import ChannelCapabilities, ChannelMessage, InboundAttachment
from utils.messaging.identity import key


class TelegramAdapter(BaseAdapter):
    channel = 'telegram'
    provider = 'telegram'
    typing_interval = 4

    def __init__(self, token, webhook_secret, *, streaming: Literal['draft', 'edit', 'none'] = 'draft', **kwargs):
        super().__init__(**kwargs)
        if not token or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', webhook_secret):
            raise ValueError('Telegram configuration missing')
        self._token, self._secret = token, webhook_secret
        self._previews = {}
        self.capabilities = ChannelCapabilities(
            streaming=streaming,
            typing=True,
            reactions=True,
            markdown_dialect='MarkdownV2',
            media_in=MEDIA_TYPES,
            media_out=MEDIA_TYPES,
            rate_limits={'chat_per_second': 1, 'global_per_second': 30},
        )

    def verify_webhook(self, body, headers):
        headers = {k.lower(): v for k, v in headers.items()}
        value = headers.get('x-telegram-bot-api-secret-token', '')
        return isinstance(value, str) and hmac.compare_digest(value.encode(), self._secret.encode())

    def parse(self, body):
        update = json.loads(body)
        if 'edited_message' in update:
            # An edit cannot replay writes from a previously completed turn.
            return ()
        callback = update.get('callback_query')
        item = callback.get('message', {}) if callback else update.get('message', {})
        sender = callback.get('from', {}) if callback else item.get('from', {})
        chat = item.get('chat', {})
        if chat.get('type') != 'private' or sender.get('is_bot') or str(sender.get('id')) != str(chat.get('id')):
            return ()
        if not sender.get('id') or not item.get('message_id') or 'update_id' not in update:
            raise ValueError('Incomplete Telegram update')
        text = callback.get('data', '') if callback else item.get('text', item.get('caption', ''))
        if callback and text != 'undo':
            if not text.startswith('ask:'):
                return ()
            text = text[4:]
        command = text.strip().split(' ', 1)[0].lower()
        proof = None
        if command == '/start' and ' ' in text:
            proof = text.split(' ', 1)[1].strip()
            if not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', proof):
                raise ValueError('Invalid link token')
        attachments = []
        for field, default_mime, default_name in (
            ('voice', 'audio/ogg', 'voice.ogg'),
            ('document', 'application/octet-stream', 'document.txt'),
            ('photo', 'image/jpeg', 'photo.jpg'),
        ):
            media = item.get(field)
            if isinstance(media, list):
                media = media[-1] if media else None
            if media:
                attachments.append(
                    InboundAttachment(
                        media['file_id'],
                        media.get('file_name', default_name),
                        media.get('mime_type', default_mime),
                        media.get('file_size', 0),
                        field == 'voice',
                    )
                )
        return (
            ChannelMessage(
                self.channel,
                self.provider,
                str(sender['id']),
                str(chat['id']),
                str(item['message_id']) if not callback else 'callback:' + str(callback['id']),
                text,
                datetime.now(timezone.utc),
                reply_to=str(item['message_id']),
                link_proof=proof,
                unlink=command == '/unlink',
                command=(
                    'help'
                    if command in ('/help', '/start') and not proof
                    else ('undo' if command in ('undo', '/undo') else None)
                ),
                attachments=tuple(attachments),
                display_name=sender.get('username') if isinstance(sender.get('username'), str) else None,
            ),
        )

    def render(self, text):
        return telegram(text, self.capabilities.max_text_len)

    async def api(self, method, body, *, files=None, idempotent=False):
        kwargs = {'data': body, 'files': files} if files else {'json': body}
        return await request_json(
            self.transport,
            'POST',
            'https://api.telegram.org/bot' + self._token + '/' + method,
            idempotent=idempotent,
            sleep=self.sleep,
            **kwargs
        )

    async def typing(self, message, active=True):
        if active:
            await self.api('sendChatAction', {'chat_id': message.external_chat_id, 'action': 'typing'}, idempotent=True)

    async def download(self, attachment):
        value = await self.api('getFile', {'file_id': attachment.reference}, idempotent=True)
        path = value['result']['file_path']
        if path.startswith('/') or '..' in path.split('/'):
            raise ValueError('Invalid provider file path')
        return await self.transport.download(
            'https://api.telegram.org/file/bot' + self._token + '/' + quote(path, safe='/'),
            allowed_hosts={'api.telegram.org'},
        )

    async def send(self, message, *, text=None, artifact=None, draft=False):
        await self.pace(message.external_chat_id)
        await self.pace('__global__', 1 / 30)
        body = {'chat_id': message.external_chat_id}
        if draft:
            if self.capabilities.streaming == 'none':
                return
            if self.capabilities.streaming == 'edit':
                identity = key(message.external_chat_id, message.provider_message_id)
                preview = self._previews.get(identity)
                body.update(text=text, parse_mode='MarkdownV2')
                if preview:
                    body['message_id'] = preview
                    await self.api('editMessageText', body, idempotent=True)
                else:
                    if len(self._previews) >= 4096:
                        raise RuntimeError('Preview capacity reached')
                    result = await self.api('sendMessage', body)
                    self._previews[identity] = result['result']['message_id']
                return
            body.update(text=text, parse_mode='MarkdownV2', draft_id=int(key(message.provider_message_id)[:7], 16) or 1)
            await self.api('sendMessageDraft', body, idempotent=True)
            return
        label = 'artifact:' + artifact.file_store_ref if artifact else 'text:' + (text or '')
        operation = self.operation(message, label)
        if not await self.ledger.begin(message, operation):
            return
        if artifact:
            data = await self.owned_bytes(artifact)
            field = (
                'photo'
                if artifact.mime_type.startswith('image/')
                else ('voice' if artifact.mime_type.startswith('audio/') else 'document')
            )
            value = await self.api(
                'send' + field.title(), body, files={field: (artifact.name, data, artifact.mime_type)}
            )
        else:
            body.update(text=text, parse_mode='MarkdownV2')
            if send_markup.get():
                body['reply_markup'] = send_markup.get()
            value = await self.api('sendMessage', body)
        await self.ledger.commit(message, operation, value['result']['message_id'])
        preview = self._previews.pop(key(message.external_chat_id, message.provider_message_id), None)
        if preview:
            await self.api(
                'deleteMessage', {'chat_id': message.external_chat_id, 'message_id': preview}, idempotent=True
            )

    def buttons(self, suggestions):
        rows = []
        for suggestion in suggestions[:3]:
            if isinstance(suggestion, str) and len(('ask:' + suggestion).encode()) <= 64:
                rows.append([{'text': suggestion, 'callback_data': 'ask:' + suggestion}])
        rows.append([{'text': 'Undo last write', 'callback_data': 'undo'}])
        return {'inline_keyboard': rows}

    async def action(self, message, action, value):
        if action != 'react' or len(value) > 16:
            raise ValueError('Unsupported reaction')
        await self.pace(message.external_chat_id)
        await self.api(
            'setMessageReaction',
            {
                'chat_id': message.external_chat_id,
                'message_id': int(message.reply_to),
                'reaction': [{'type': 'emoji', 'emoji': value}],
            },
            idempotent=True,
        )
