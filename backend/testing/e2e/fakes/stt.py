"""
Fake STT (Speech-to-Text) helpers.

The listen harness deliberately does not emulate Deepgram's full streaming
WebSocket protocol yet. For custom-STT mode, the app/client is the STT
boundary: it sends ``suggested_transcript`` events into the real listen
websocket after audio bytes establish the session clock. Those deterministic
events exercise backend transcript handling and persistence without allowing
Deepgram/network access.

If Deepgram HTTP pre-recorded transcription is used instead, we can fake that
endpoint.
"""


class FakeStreamingSTTSocket:
    """Minimal STT socket surface used by routers.transcribe._stream_handler."""

    def __init__(self, callback, *, die_on_first_send=False):
        self.callback = callback
        self.die_on_first_send = die_on_first_send
        self.sent_chunks = []
        self.finish_calls = 0
        self.drain_calls = 0
        self._dead = False
        self._death_reason = None
        self._emitted = False

    @property
    def is_connection_dead(self) -> bool:
        return self._dead

    @property
    def death_reason(self):
        return self._death_reason

    def send(self, data: bytes) -> bool:
        self.sent_chunks.append(data)
        if self.die_on_first_send:
            self._dead = True
            self._death_reason = "synthetic provider disconnected"
            return False
        if self._emitted:
            return True
        self._emitted = True
        self.callback(
            [
                {
                    "id": "seg-streaming-stt-1",
                    "text": "Hermetic streaming STT transcript from the fake socket.",
                    "speaker": "SPEAKER_00",
                    "is_user": True,
                    "person_id": None,
                    "start": 0.0,
                    "end": 1.25,
                    "stt_provider": "e2e-streaming-stt",
                }
            ]
        )
        return True

    async def drain_and_close(self):
        self.drain_calls += 1
        # Production drain_and_close finalizes the socket (Parakeet sets
        # _closed, Deepgram queues EOS); mirror that so teardown observability
        # (finish_calls) stays consistent between real and fake sockets.
        self.finish()

    def finish(self) -> None:
        self.finish_calls += 1


def install_streaming_stt_fake(monkeypatch, *, die_on_first_send=False):
    """Patch the listen receiver provider boundary and return fake sockets.

    Deepgram is retired from serving, so the fake now patches the enabled
    provider entry points (Parakeet/Modulate) and returns an enabled service.
    """
    from routers.listen import receiver as listen_receiver
    from routers.listen import runtime as listen_runtime
    from utils.stt.streaming import STTService

    sockets = []

    async def fake_process_audio_parakeet(callback, *args, **kwargs):
        socket = FakeStreamingSTTSocket(callback, die_on_first_send=die_on_first_send)
        sockets.append(socket)
        return socket

    async def fake_process_audio_modulate(callback, *args, **kwargs):
        socket = FakeStreamingSTTSocket(callback, die_on_first_send=die_on_first_send)
        sockets.append(socket)
        return socket

    # The receiver dispatches on stt_service; patch both enabled providers so
    # the fake is reached regardless of which one the runtime selects.
    monkeypatch.setattr(listen_receiver, "process_audio_parakeet", fake_process_audio_parakeet)
    monkeypatch.setattr(listen_receiver, "process_audio_modulate", fake_process_audio_modulate)
    monkeypatch.setattr(
        listen_runtime,
        "get_stt_service_for_language",
        lambda *_args, **_kwargs: (STTService.parakeet, "en", "parakeet"),
    )
    monkeypatch.setattr(listen_receiver, "is_gate_enabled", lambda: False)
    monkeypatch.setattr(listen_runtime, "record_usage", lambda *args, **kwargs: None)
    return sockets


def fake_suggested_transcript_event():
    """Return a deterministic custom-STT event accepted by routers.transcribe."""
    return {
        "type": "suggested_transcript",
        "stt_provider": "e2e-custom-stt",
        "segments": [
            {
                "id": "seg-custom-stt-1",
                "text": "Hermetic custom STT transcript from the listen harness.",
                "speaker": "SPEAKER_00",
                "is_user": True,
                "start": 0.0,
                "end": 1.25,
            }
        ],
    }


def configure_stt_fake(httpserver):
    """
    Configure a fake Deepgram HTTP pre-recorded transcription endpoint.

    This handles the case where pre-recorded audio is transcribed via
    Deepgram's HTTP API (not streaming WS).
    """
    fake_response = {
        "results": {
            "channels": [
                {
                    "alternatives": [
                        {
                            "transcript": "Hello this is a test transcript for the e2e harness.",
                            "confidence": 0.99,
                        }
                    ]
                }
            ]
        },
        "metadata": {"request_id": "fake-e2e-test", "model_uuid": "fake-model"},
    }

    httpserver.expect_request("/v1/listen").respond_with_json(
        fake_response, status=200, content_type="application/json"
    )


def configure_stt_timeout(httpserver):
    """Configure STT to timeout — used by failure-mode tests."""
    import time

    def _slow_response_handler(_request):
        time.sleep(30)
        return {"error": "timeout"}, 504, {}

    # Note: pytest-httpserver doesn't easily support slow responses.
    # For timeout tests, we skip and mark as TODO.
    pass
