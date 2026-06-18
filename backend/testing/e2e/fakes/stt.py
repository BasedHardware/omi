"""
Fake STT (Speech-to-Text) Deepgram streaming WebSocket.

For v1, STT fakes are simplified — the listen pipeline requires a
full WebSocket negotiation that is complex to replicate. Tests that
need STT should be marked as skipped with a TODO for future implementation.

If Deepgram HTTP pre-recorded transcription is used instead, we can
fake that endpoint.
"""

# TODO: Implement Deepgram WebSocket fake for full listen pipeline tests.
# The Deepgram WS protocol sends JSON metadata followed by binary audio,
# then streams back transcript results. This requires an async WS handler
# that buffers audio and returns deterministic transcripts.
#
# For now, conversation processing tests seed transcripts directly into
# Firestore (simulating post-STT state), bypassing the need for STT fakes.


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
