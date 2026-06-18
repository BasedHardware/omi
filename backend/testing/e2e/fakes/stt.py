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

# TODO: Implement Deepgram WebSocket fake for full /v4/listen and pusher scenarios.
# The Deepgram WS protocol sends JSON metadata followed by binary audio, then
# streams back transcript results. That remains broader v2 coverage; custom-STT
# tests below are explicitly scoped to the backend's suggested-transcript seam.


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
