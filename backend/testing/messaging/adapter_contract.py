"""Reusable adapter contract. Subclass and supply adapter + signed_message fixtures.

Adapters additionally run provider-specific parsing/signature fixtures. These tests
exercise the common gateway, so a live network or bot credential is never required.
"""

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from utils.messaging.contracts import Artifact
from utils.messaging.gateway import Gateway
from utils.messaging.outbound import ChannelReplySink, authorize_send
from testing.messaging.store import MemoryStore


class AdapterContract:
    def test_signature_rejection(self, adapter, signed_message):
        body, headers = signed_message()
        gateway = Gateway(adapter, store=MemoryStore())
        with pytest.raises(PermissionError):
            # Telegram authenticates a shared header rather than signing bytes.
            # Body-tampering rejection belongs in HMAC-provider fixture tests.
            asyncio.run(gateway.webhook(body, {name: 'invalid' for name in headers}))

    def test_dedup_and_fast_ack(self, adapter, signed_message):
        store = MemoryStore()
        gateway = Gateway(adapter, store=store, turn=lambda *a, **k: pytest.fail('turn before acknowledgement'))
        body, headers = signed_message()

        async def run():
            first = await asyncio.wait_for(gateway.webhook(body, headers), 1)
            second = await gateway.webhook(body, headers)
            assert len(first['jobs']) == 1 and not second['jobs']
            assert not adapter.sent
            assert len(store.jobs) == 1

        asyncio.run(run())

    def test_unlinked_sender(self, adapter, signed_message):
        gateway = Gateway(adapter, store=MemoryStore(), turn=lambda *a, **k: pytest.fail('Unlinked turn'))

        async def run():
            reply = await gateway.webhook(*signed_message())
            await gateway.process(reply['jobs'][0])
            assert [s['text'] for s in adapter.sent] == list(adapter.render('Link your account in Omi to chat here.'))

        asyncio.run(run())

    @pytest.mark.parametrize('kind', ['token', 'code'])
    def test_linking_proofs_are_one_time_and_audience_bound(self, adapter, signed_message, kind):
        store = MemoryStore()
        proof = store.mint('user', adapter.channel, adapter.provider, kind)['proof']
        message = adapter.parse(signed_message()[0])[0]
        with pytest.raises(PermissionError):
            store.consume(proof, replace(message, provider='other'))
        assert store.consume(proof, message)['uid'] == 'user'
        with pytest.raises(PermissionError):
            store.consume(proof, message)
        expired = store.mint(
            'user', adapter.channel, adapter.provider, kind, now=datetime.now(timezone.utc) - timedelta(hours=1)
        )['proof']
        with pytest.raises(PermissionError):
            store.consume(expired, message)

    @pytest.mark.parametrize('streaming', ['draft', 'edit', 'none'])
    def test_streamed_buffered_artifact_sinks(self, adapter, signed_message, streaming):
        adapter.capabilities = replace(adapter.capabilities, streaming=streaming, media_out=('text/plain',))
        message = adapter.parse(signed_message()[0])[0]
        artifact = Artifact('files/owned-artifact', 'text/plain', 3, 'hello.txt')

        async def run():
            sink = ChannelReplySink(adapter, message)
            await sink.text('hello')
            assert bool(adapter.sent) == (streaming != 'none')
            await sink.finish('hello')
            await sink.artifact(artifact)
            assert adapter.sent[-1]['artifact'] == artifact
            assert any(s['text'] == 'hello' and not s['draft'] for s in adapter.sent)

        asyncio.run(run())

    def test_outbound_classes_and_windows(self, adapter):
        now = datetime.now(timezone.utc)
        caps = replace(adapter.capabilities, free_reply_window=timedelta(hours=24))
        for kind in ('reply', 'deferred_reply'):
            authorize_send(caps, kind, now, now=now)
            with pytest.raises(PermissionError):
                authorize_send(caps, kind, now - timedelta(days=2), now=now)
        with pytest.raises(PermissionError):
            authorize_send(caps, 'omi_initiated', now)
        with pytest.raises(PermissionError):
            authorize_send(caps, 'reply', None)
        with pytest.raises(PermissionError):
            authorize_send(replace(caps, outbound_template_required=True), 'reply', now)
