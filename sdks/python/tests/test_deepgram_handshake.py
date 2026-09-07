"""Exercise the SDK with the installed websockets API, without network I/O."""

import asyncio
import json
import sys
import urllib.request

from omi.stt.deepgram import DeepgramTranscriber


def test_deepgram_authorization_is_a_handshake_header(monkeypatch):
    async def scenario():
        received = asyncio.Event()
        audio_sent = asyncio.Event()
        headers = []
        sent_audio = []
        transcripts = []
        pcm = b"\x00\x00" * 80

        class Connection:
            async def handshake(self, additional_headers, user_agent_header):
                headers.append(dict(additional_headers))

            def start_keepalive(self):
                pass

            async def close(self):
                pass

            async def send(self, message):
                sent_audio.append(message)
                audio_sent.set()

            async def messages(self):
                await audio_sent.wait()
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

        async def fail_on_retry(_delay):
            # run() calls sleep from its exception handler. Preserve that
            # original error instead of hiding a broken mock behind retries.
            error = sys.exc_info()[1]
            assert error is not None, "retry sleep must have an active exception"
            raise error

        loop = asyncio.get_running_loop()
        monkeypatch.setattr(urllib.request, "getproxies", lambda: {})
        monkeypatch.setattr(loop, "create_connection", connect_tcp)
        monkeypatch.setattr(asyncio, "sleep", fail_on_retry)
        audio_queue = asyncio.Queue()
        audio_queue.put_nowait(pcm)
        worker = asyncio.create_task(DeepgramTranscriber("test-key").run(audio_queue, on_transcript))
        completed = asyncio.create_task(received.wait())
        try:
            done, _ = await asyncio.wait({worker, completed}, timeout=1, return_when=asyncio.FIRST_COMPLETED)
            if worker in done:
                await worker
            assert completed in done, "transcript callback did not complete"
        finally:
            worker.cancel()
            completed.cancel()
            await asyncio.gather(worker, completed, return_exceptions=True)

        assert headers == [{"Authorization": "Token test-key"}]
        assert sent_audio == [pcm]
        assert transcripts == ["test transcript"]

    asyncio.run(scenario())
