"""Keiki external-harness adapter: Keiki owns the line, Omi runs the turn.

Keiki pushes one signed ``keiki.turn`` per debounced batch of contact messages and keeps
that turn open until Omi settles it. Every reply goes through the turn-scoped API under a
short-lived ``kts1`` credential signed with the agent's signing secret, so no turn token is
stored. The agent runs with ``midTurnStrategy: queue``: a newer message waits for the open
turn to settle, which keeps the inbox's per-chat FIFO the only ordering authority.
"""

import base64
import hashlib
import hmac
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from utils.messaging.adapters.base import BaseAdapter
from utils.messaging.adapters.linq import IMessageAdapter, link_code
from utils.messaging.adapters.modalities import emoji_only
from utils.messaging.adapters.rendering import valid_item_link
from utils.messaging.adapters.transport import ProviderError, request_json
from utils.messaging.contracts import ChannelCapabilities, ChannelMessage
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

API_BASE = 'https://onkeiki.com/api/v1'
SIGNATURE_TOLERANCE_SECONDS = 300
# The service name each Omi channel accepts from the turn's channel envelope. Keiki labels
# turns on its phone lines `sms` even when they arrive over iMessage (seen in prod 2026-10-31);
# an unknown service is logged by name and never answered.
CHANNEL_SERVICES = {
    'imessage': frozenset({'imessage', 'sms', 'photon', 'linq'}),
    'whatsapp': frozenset({'whatsapp'}),
}
FILES_UNAVAILABLE = 'I can’t send files in this chat yet. Open Omi to see it.'
TAPBACKS = {'love': '❤️', 'like': '👍', 'dislike': '👎', 'laugh': '😂', 'emphasize': '‼️', 'question': '❓'}
_ATTACHMENT = re.compile(r'attachment_id=')


def turn_auth(signing_secret, agent_id, turn_id, *, now=None):
    """The documented ``kts1`` bearer: HMAC of the compact JSON payload, valid five minutes."""
    payload = json.dumps(
        {'a': agent_id, 't': turn_id, 'ts': int(time.time() if now is None else now)}, separators=(',', ':')
    )
    encoded = base64.urlsafe_b64encode(payload.encode()).rstrip(b'=').decode()
    digest = hmac.new(signing_secret.encode(), ('keiki-turn-auth.v1.' + encoded).encode(), hashlib.sha256)
    return 'kts1.' + encoded + '.' + digest.hexdigest()


def _signatures(value):
    stamp, signatures = None, []
    for part in (value or '').split(','):
        name, sep, field = part.partition('=')
        if not sep:
            return None, ()
        name, field = name.strip(), field.strip()
        if name == 't':
            if stamp is not None:
                return None, ()
            stamp = field
        elif name == 'v1':
            signatures.append(field)
    if stamp is None or not stamp.isdigit() or not signatures:
        return None, ()
    if any(not re.fullmatch(r'[0-9a-fA-F]{64}', s) for s in signatures):
        return None, ()
    return stamp, tuple(signatures)


class KeikiClient:
    name = 'keiki'

    def __init__(self, agent_id, signing_secret, *, transport, sleep, clock=time.time, api_base=API_BASE):
        if not agent_id or not signing_secret or len(signing_secret) < 16:
            raise ValueError('Keiki configuration missing')
        if not api_base.startswith('https://'):
            raise ValueError('Keiki API base must be https')
        self.agent_id, self._secret = agent_id, signing_secret
        self.transport, self.sleep, self.clock = transport, sleep, clock
        self.api_base = api_base.rstrip('/')

    def verify(self, body, headers):
        headers = {k.lower(): v for k, v in headers.items()}
        stamp, signatures = _signatures(headers.get('keiki-signature'))
        if stamp is None or abs(self.clock() - int(stamp)) > SIGNATURE_TOLERANCE_SECONDS:
            return False
        expected = hmac.new(self._secret.encode(), stamp.encode() + b'.' + body, hashlib.sha256).hexdigest()
        return any(hmac.compare_digest(expected, s.lower()) for s in signatures)

    def turn_url(self, turn_id):
        return self.api_base + '/turns/' + quote(turn_id, safe='')

    async def call(self, turn_id, path, body=None, *, idempotent=False):
        return await request_json(
            self.transport,
            'POST',
            self.turn_url(turn_id) + path,
            headers={'Authorization': 'Bearer ' + turn_auth(self._secret, self.agent_id, turn_id, now=self.clock())},
            json=body or {},
            idempotent=idempotent,
            sleep=self.sleep,
        )

    async def complete(self, turn_id, ok):
        try:
            await self.call(turn_id, '/complete', {'status': 'completed' if ok else 'failed'}, idempotent=True)
        except ProviderError as error:
            if error.status_code != 409:  # turn_closed: Keiki already settled it (deadline or cancel)
                raise


class KeikiAdapter(BaseAdapter):
    """One Omi channel served by one Keiki agent in external push mode."""

    render = IMessageAdapter.render
    item_presentation = IMessageAdapter.item_presentation

    def __init__(self, channel, client: KeikiClient, *, max_ratio=3, **kwargs):
        super().__init__(**kwargs)
        if channel not in CHANNEL_SERVICES:
            raise ValueError('Unsupported Keiki channel')
        if not 1 <= max_ratio <= 5:
            raise ValueError('Invalid send/receive ratio')
        self.channel, self.client, self.provider = channel, client, client.name
        self.max_ratio = max_ratio
        self.capabilities = ChannelCapabilities(
            typing=True,
            reactions=True,
            max_text_len=1200 if channel == 'imessage' else 4000,
            # Keiki's turn API sends files only from its own sandbox paths; Omi files stay in Omi.
            media_in=(),
            media_out=(),
            free_reply_window=timedelta(hours=24) if channel == 'whatsapp' else None,
            rate_limits={'chat_per_minute': 30, 'max_send_receive_ratio': max_ratio},
        )

    def verify_webhook(self, body, headers):
        return self.client.verify(body, headers)

    def _turn(self, body):
        """A verified turn addressed to this agent, or None for any other event."""
        event = json.loads(body)
        if not isinstance(event, dict):
            raise ValueError('Invalid Keiki event')
        if event.get('agentId') != self.client.agent_id:
            raise PermissionError('Keiki event for another agent')
        if event.get('type') != 'keiki.turn':
            return None
        if event.get('version') != 1 or not isinstance(event.get('turnId'), str) or not event['turnId']:
            raise ValueError('Unsupported Keiki turn')
        return event

    def _answerable(self, turn):
        envelope = turn.get('channel')
        if not isinstance(envelope, dict):
            envelope = {}
        service = str(envelope.get('channel', '')).lower()
        if service not in CHANNEL_SERVICES[self.channel]:
            logger.info('Messaging ignored provider=keiki reason=channel_mismatch service=%s', service[:24])
            return False
        if turn.get('heldBack') or turn.get('silent') or turn.get('quietLoop'):
            return False
        if envelope.get('isGroup') is True or envelope.get('isDm') is False:
            return False
        return isinstance(turn.get('conversationId'), str) and bool(turn['conversationId'])

    def parse(self, body):
        turn = self._turn(body)
        if turn is None or not self._answerable(turn):
            return ()
        spoken = [m for m in turn.get('messages', ()) if isinstance(m, dict) and not m.get('silent')]
        if not spoken:
            return ()
        text = '\n'.join(str(m.get('text') or '') for m in spoken).strip()
        content = '\n'.join(str(m.get('content') or '') for m in spoken)
        attachments = bool(_ATTACHMENT.search(content))
        if not text and not attachments:
            return ()
        command = text.lower()
        last = spoken[-1]
        message_id = last.get('messageId') if isinstance(last.get('messageId'), str) else None
        quoted = last.get('replyTo')
        if not isinstance(quoted, dict):
            quoted = {}
        quoted_text = quoted.get('text')
        return (
            ChannelMessage(
                self.channel,
                self.provider,
                turn['conversationId'],
                turn['conversationId'],
                # One Keiki turn is one inbox row: dispatch retries dedupe, and the reply
                # path derives the turn URL from it.
                turn['turnId'],
                text,
                datetime.now(timezone.utc),
                reply_to=message_id,
                link_proof=link_code(text),
                unlink=command in ('unlink', '/unlink'),
                command=(
                    'unsupported'
                    if attachments
                    else (
                        'ack'
                        if emoji_only(text)
                        else (
                            'help'
                            if command in ('help', '/help')
                            else ('new' if command == 'new chat' else 'undo' if command == 'undo' else None)
                        )
                    )
                ),
                quoted_text=quoted_text[:2000] if isinstance(quoted_text, str) else None,
                quoted_message_id=str(quoted['messageId'])[:200] if quoted.get('messageId') else None,
            ),
        )

    async def unhandled(self, body):
        # A turn Omi will not answer still holds Keiki's conversation slot until it settles.
        turn = self._turn(body)
        if turn is not None:
            await self.client.complete(turn['turnId'], True)

    async def settled(self, message, ok):
        await self.client.complete(message.provider_message_id, ok)

    async def typing(self, message, active=True):
        if active:  # Keiki's indicator clears on the next send; there is no stop call.
            await self.client.call(message.provider_message_id, '/typing', idempotent=True)

    async def send(self, message, *, text=None, artifact=None, draft=False, link=None):
        if draft:
            return
        if artifact:
            # Unreachable while media_out is empty (the sink refuses files first); kept so a
            # capability change degrades to a notice rather than a failed turn.
            record_fallback(
                component='other', from_mode='channel_file', to_mode='text_notice', reason='other', outcome='degraded'
            )
            text = FILES_UNAVAILABLE
        if link:
            if not valid_item_link(link):
                raise ValueError('Item link required')
            text = link
        operation = self.operation(message, ('link:' + link) if link else 'text:' + (text or ''))
        if not await self.ledger.begin(message, operation, ratio=self.max_ratio, retry_reserved=True):
            return
        body = {'text': text, 'idempotencyKey': operation}
        reply_to = await self.reply_target(message)
        if reply_to:
            body['replyToMessageId'] = reply_to
        try:
            result = await self.client.call(message.provider_message_id, '/messages', body)
        except ProviderError as error:
            # Keiki refuses an unsupported thread before sending (400); the key may be reused.
            if not reply_to or error.status_code != 400:
                raise
            body.pop('replyToMessageId')
            result = await self.client.call(message.provider_message_id, '/messages', body)
        # A 2xx is Keiki's delivery acknowledgement (a duplicate key answers 2xx without an ID).
        # Failing here would apologise for a reply the contact already has.
        data = result.get('data')
        if not isinstance(data, dict):
            data = {}
        provider_id = result.get('messageId') or data.get('messageId') or result.get('id')
        await self.ledger.commit(message, operation, str(provider_id or operation), message_sent=True)

    async def action(self, message, action, value):
        if action != 'react' or value not in TAPBACKS:
            raise ValueError('Unsupported Keiki action')
        if not message.reply_to:
            raise ValueError('No message to react to')
        operation = self.operation(message, 'react:' + value)
        if not await self.ledger.begin(message, operation, ratio=self.max_ratio):
            return
        await self.client.call(
            message.provider_message_id,
            '/actions',
            {'action': 'react', 'messageId': message.reply_to, 'emoji': TAPBACKS[value], 'idempotencyKey': operation},
        )
        await self.ledger.commit(message, operation, message.reply_to)

    def tools(self, sink):
        from langchain_core.tools import StructuredTool

        async def react(reaction: str) -> str:
            """React to the user's current message: love, like, dislike, laugh, emphasize or question."""
            await sink.action('react', reaction)
            return 'Reaction sent.'

        return (StructuredTool.from_function(name=self.channel + '_react', coroutine=react),)
