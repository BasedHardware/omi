"""Exercise the SDK with the installed websockets API, without network I/O."""

import asyncio
import json
import urllib.request

from omi.stt.deepgram import DeepgramTranscriber


def test_deepgram_authorization_is_a_handshake_header(monkeypatch):
    async def scenario():
        received = asyncio.Event()
        headers = []
        transcripts = []

        class Connection:
            async def handshake(self, additional_headers, user_agent_header):
                headers.append(dict(additional_headers))

            def start_keepalive(self):
                pass

            async def close(self):
                pass

            async def send(self, message):
                raise AssertionError("the empty input queue must not send audio")

            async def messages(self):
                yield json.dumps({"channel": {"alternatives": [{"transcript": "test transcript"}]}})
                await asyncio.Future()

            def __aiter__(self):
                return self.messages()

        # Deliberately keep asyncio's TCP argument boundary: HTTP handshake
        # headers must be consumed by websockets, never forwarded to this call.
        async def connect_tcp(protocol_factory, host=None, port=None, *, ssl=None, server_hostname=None):
            assert host == "api.deepgram.com"
            assert port == 443
            assert ssl is True
            assert server_hostname == "api.deepgram.com"
            return object(), Connection()

        def on_transcript(text):
            transcripts.append(text)
            received.set()

        loop = asyncio.get_running_loop()
        monkeypatch.setattr(urllib.request, "getproxies", lambda: {})
        monkeypatch.setattr(loop, "create_connection", connect_tcp)
        worker = asyncio.create_task(DeepgramTranscriber("test-key").run(asyncio.Queue(), on_transcript))
        try:
            await asyncio.wait_for(received.wait(), timeout=1)
        finally:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)

        assert headers == [{"Authorization": "Token test-key"}]
        assert transcripts == ["test transcript"]

    asyncio.run(scenario())
