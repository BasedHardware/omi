"""Reference adapter and scripted provider for every Stage B adapter's contract suite."""

import hashlib
import hmac
import json
from datetime import datetime, timezone

from utils.llm.shaped_agent import Turn
from utils.messaging.contracts import ChannelCapabilities, ChannelMessage


class LoopbackAdapter:
    channel = 'loopback'
    provider = 'fake'

    def __init__(self, *, capabilities=None, secret=b'contract-test-only'):
        self.capabilities = capabilities or ChannelCapabilities(media_out=('text/plain',))
        self.secret = secret
        self.sent = []
        self.surface_tools = ()

    def signed(self, **message):
        message.setdefault('external_user_id', 'external-user')
        message.setdefault('external_chat_id', 'chat')
        message.setdefault('provider_message_id', 'message')
        message.setdefault('text', 'hello')
        message.setdefault('received_at', datetime.now(timezone.utc).isoformat())
        body = json.dumps(message).encode()
        return body, {'signature': hmac.new(self.secret, body, hashlib.sha256).hexdigest()}

    def verify_webhook(self, body, headers):
        expected = hmac.new(self.secret, body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(headers.get('signature', ''), expected)

    def parse(self, body):
        value = json.loads(body)
        value['received_at'] = datetime.fromisoformat(value['received_at'])
        return (ChannelMessage(channel=self.channel, provider=self.provider, **value),)

    def render(self, text):
        size = self.capabilities.max_text_len
        return tuple(text[index : index + size] for index in range(0, len(text), size))

    def tools(self, sink):
        return self.surface_tools

    async def send(self, message, *, text=None, artifact=None, draft=False):
        self.sent.append({'message': message, 'text': text, 'artifact': artifact, 'draft': draft})


class ScriptedProvider:
    """One provider turn per script item; run_loop remains the only agent loop."""

    def __init__(self, *turns: Turn):
        self.turns = iter(turns)
        self.histories = []

    async def __call__(self, mount, history):
        self.histories.append(json.dumps(history, sort_keys=True).encode())
        return next(self.turns)
