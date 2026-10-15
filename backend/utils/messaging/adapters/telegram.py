"""Official Telegram Bot API adapter; private, non-bot senders only."""

import hmac
import json
import re
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import quote

from utils.messaging.adapters.base import BaseAdapter
from utils.observability.fallback import record_fallback
from utils.messaging.delivery_context import send_reply_target, send_first_chunk
from utils.messaging.delivery_context import send_markup
from utils.messaging.adapters.media import (
    MEDIA_TYPES,
    OUTBOUND_MEDIA_TYPES,
    MediaPreparationError,
    contact_text,
    is_audio_video,
)
from utils.messaging.adapters.modalities import emoji_only, location_text
from utils.messaging.adapters.rendering import telegram, html_plain, item_buttons
from utils.messaging.adapters.transport import request_json, ProviderError
from utils.messaging.contracts import ChannelCapabilities, ChannelMessage, InboundAttachment
from utils.messaging.identity import key
from utils.messaging.turn_context import bound_provider_clock


def replace_attachment_voice(attachment):
    from dataclasses import replace

    return replace(attachment, voice=is_audio_video(attachment))


class TelegramAdapter(BaseAdapter):
    channel = 'telegram'
    provider = 'telegram'
    typing_interval = 4

    def __init__(
        self,
        token,
        webhook_secret,
        *,
        streaming: Literal['draft', 'edit', 'none'] = 'draft',
        shared_pacing=False,
        **kwargs
    ):
        super().__init__(**kwargs)
        if not token or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', webhook_secret):
            raise ValueError('Telegram configuration missing')
        self._token, self._secret = token, webhook_secret
        self._previews = {}
        self.shared_pacing = shared_pacing
        self.capabilities = ChannelCapabilities(
            streaming=streaming,
            typing=True,
            reactions=True,
            markdown_dialect='HTML',
            media_in=MEDIA_TYPES,
            media_out=OUTBOUND_MEDIA_TYPES,
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
        receipt_id = None
        if callback and text.startswith('undo:'):
            receipt_id = text[5:]
            if not re.fullmatch(r'[a-f0-9]{32}', receipt_id):
                return ()
            text = 'undo'
        if callback and text != 'undo':
            if not text.startswith('ask:'):
                return ()
            text = text[4:]
        command = text.strip().split(' ', 1)[0].lower()
        proof = None
        if command == '/start' and ' ' in text:
            proof = text.split(' ', 1)[1].strip()
            if not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', proof):
                proof = None
                command = 'link_help'
        stamp = None if callback else item.get('date')
        if stamp is not None and (not isinstance(stamp, int) or isinstance(stamp, bool)):
            raise ValueError('Invalid Telegram message time')
        if stamp is None:
            received_at = datetime.now(timezone.utc)
        else:
            try:
                received_at = bound_provider_clock(datetime.fromtimestamp(stamp, timezone.utc))
            except (OverflowError, OSError, ValueError):
                raise ValueError('Invalid Telegram message time') from None
        attachments = []
        for field, default_mime, default_name in (
            ('voice', 'audio/ogg', 'voice.ogg'),
            ('audio', 'audio/mpeg', 'audio.mp3'),
            ('video', 'video/mp4', 'video.mp4'),
            ('video_note', 'video/mp4', 'video-note.mp4'),
            ('document', 'application/octet-stream', 'document'),
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
                        field in ('voice', 'audio', 'video', 'video_note'),
                        media.get('duration', 0),
                    )
                )
        if not callback:
            if item.get('venue') or item.get('location'):
                venue = item.get('venue', {})
                text += '\n' + location_text(venue.get('location') or item['location'], venue)
            if item.get('contact'):
                contact = item['contact']
                text += '\nShared contact (untrusted data; do not save unless asked): ' + ' '.join(
                    str(contact.get(k, ''))[:300] for k in ('first_name', 'last_name', 'phone_number')
                )
                if isinstance(contact.get('vcard'), str) and contact['vcard']:
                    try:
                        text += '\n' + contact_text(contact['vcard'].encode('utf-8'))
                    except MediaPreparationError:
                        # Structured Telegram name/phone fields still provide usable evidence.
                        record_fallback(
                            component='other',
                            from_mode='contact_vcard',
                            to_mode='contact_fields',
                            reason='other',
                            outcome='degraded',
                        )
            # Service messages, payments, games and unknown non-content events are not turns.
            if not text and not attachments and not (item.get('sticker') or item.get('animation')):
                return ()
            if any(k in item for k in ('poll', 'dice', 'game', 'invoice', 'successful_payment', 'refunded_payment')):
                return ()
        ack = not callback and (
            bool(item.get('sticker') or item.get('animation'))
            or any(a.mime_type == 'image/gif' for a in attachments)
            or emoji_only(text)
            and not attachments
        )
        quoted = item.get('reply_to_message', {})
        quoted_text = quoted.get('text') or quoted.get('caption')
        if not quoted_text:
            for kind in ('voice', 'audio', 'photo', 'video', 'video_note', 'document', 'sticker', 'animation'):
                if quoted.get(kind):
                    quoted_text = '[voice note]' if kind in ('voice', 'video_note') else '[' + kind + ']'
                    break
        return (
            ChannelMessage(
                self.channel,
                self.provider,
                str(sender['id']),
                str(chat['id']),
                str(item['message_id']) if not callback else 'callback:' + str(callback['id']),
                text,
                received_at,
                reply_to=str(item['message_id']),
                link_proof=proof,
                unlink=command == '/unlink',
                command=(
                    'ack'
                    if ack
                    else (
                        'help'
                        if command in ('/help', '/start') and not proof
                        else (
                            'new'
                            if command == '/new'
                            else (
                                'link_help'
                                if command == 'link_help'
                                else 'undo' if command in ('undo', '/undo') else None
                            )
                        )
                    )
                ),
                attachments=tuple(replace_attachment_voice(a) for a in attachments),
                media_group_id=str(item['media_group_id']) if item.get('media_group_id') else None,
                quoted_message_id=str(quoted['message_id']) if quoted.get('message_id') else None,
                quoted_text=quoted_text[:2000] if isinstance(quoted_text, str) else None,
                forwarded=bool(item.get('forward_origin')) and not bool(callback),
                callback_id=str(callback['id']) if callback else None,
                undo_receipt_id=receipt_id,
                display_name=sender.get('username') if isinstance(sender.get('username'), str) else None,
            ),
        )

    def render(self, text):
        return telegram(text, self.capabilities.max_text_len)

    async def api(self, method, body, *, files=None, idempotent=False, threading=True):
        kwargs = {'data': body, 'files': files} if files else {'json': body}

        async def prepare_thread():
            resolver = send_reply_target.get()
            if not threading or method != 'sendMessage' or resolver is None or not send_first_chunk.get():
                return
            current = await resolver()
            if current:
                body['reply_parameters'] = {'message_id': int(current), 'allow_sending_without_reply': True}
            else:
                body.pop('reply_parameters', None)

        async def pace_attempt():
            if self.shared_pacing:
                from utils.messaging.pacing import pace

                if await pace(self._token, str(body.get('chat_id', '')), self.sleep):
                    return
            await self.pace('__global__', 1 / 30)
            if self.shared_pacing and body.get('chat_id'):
                await self.pace(str(body['chat_id']))

        try:
            return await request_json(
                self.transport,
                'POST',
                'https://api.telegram.org/bot' + self._token + '/' + method,
                idempotent=idempotent,
                sleep=self.sleep,
                before_request=prepare_thread,
                before_attempt=pace_attempt,
                **kwargs
            )
        except ProviderError as exc:
            if body.get('reply_parameters') and exc.status_code in (400, 404, 422) and not exc.rendering_rejected:
                record_fallback(
                    component='other',
                    from_mode='threaded_reply',
                    to_mode='plain_reply',
                    reason='other',
                    outcome='degraded',
                )
                fallback = dict(body)
                fallback.pop('reply_parameters')
                return await self.api(method, fallback, files=files, idempotent=idempotent, threading=False)
            # Only a definite 400 rejection permits a second send. Timeouts/5xx
            # remain ambiguous and must never duplicate a delivered message.
            if not exc.rendering_rejected or body.get('parse_mode') != 'HTML' or not body.get('text'):
                raise
            record_fallback(
                component='other', from_mode='telegram_html', to_mode='plain_text', reason='other', outcome='degraded'
            )
            fallback = dict(body)
            fallback.pop('parse_mode')
            fallback['text'] = html_plain(body['text'])
            return await self.api(method, fallback, idempotent=idempotent, threading=threading)

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
        if not self.shared_pacing:
            await self.pace(message.external_chat_id)
        body = {'chat_id': message.external_chat_id}
        reply_to = await self.reply_target(message)
        if reply_to and not draft:
            body['reply_parameters'] = {'message_id': int(reply_to), 'allow_sending_without_reply': True}
        if draft:
            if self.capabilities.streaming == 'none':
                return
            if self.capabilities.streaming == 'edit':
                identity = key(message.external_chat_id, message.provider_message_id)
                preview = self._previews.get(identity)
                body.update(text=text, parse_mode='HTML')
                if preview:
                    body['message_id'] = preview
                    await self.api('editMessageText', body, idempotent=True)
                else:
                    if len(self._previews) >= 4096:
                        raise RuntimeError('Preview capacity reached')
                    result = await self.api('sendMessage', body)
                    self._previews[identity] = result['result']['message_id']
                return
            body.update(text=text, parse_mode='HTML', draft_id=int(key(message.provider_message_id)[:7], 16) or 1)
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
            body.update(text=text, parse_mode='HTML')
            if send_markup.get():
                body['reply_markup'] = send_markup.get()
            value = await self.api('sendMessage', body)
        await self.ledger.commit(message, operation, value['result']['message_id'])
        preview = self._previews.pop(key(message.external_chat_id, message.provider_message_id), None)
        if preview:
            await self.api(
                'deleteMessage', {'chat_id': message.external_chat_id, 'message_id': preview}, idempotent=True
            )

        return str(value['result']['message_id'])

    def item_buttons(self, items):
        return item_buttons(items)

    def receipt_buttons(self, receipt):
        if receipt.reversible:
            return {'inline_keyboard': [[{'text': 'Undo', 'callback_data': 'undo:' + receipt.id}]]}
        return None

    async def acknowledge(self, message):
        if message.callback_id:
            await self.api('answerCallbackQuery', {'callback_query_id': message.callback_id}, idempotent=True)

    async def edit_receipt(self, message, result):
        # The receipt delivery ID (or its authenticated callback bubble) owns the edit.
        if result.bubble_id and result.bubble_text:
            await self.api(
                'editMessageText',
                {
                    'chat_id': message.external_chat_id,
                    'message_id': int(result.bubble_id),
                    'text': self.render(result.bubble_text)[-1],
                    'parse_mode': 'HTML',
                    'reply_markup': {'inline_keyboard': []},
                },
                idempotent=True,
            )

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
