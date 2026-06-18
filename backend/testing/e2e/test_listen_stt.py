"""Listen/STT websocket seam coverage."""

import json


def test_web_listen_custom_stt_dispatches_to_stream_handler(client, monkeypatch):
    """The web listen route should auth and dispatch custom-STT sessions without Deepgram.

    The provider-heavy stream handler is replaced with a deterministic fake here; this
    still exercises the real websocket route, first-message auth protocol, query parsing,
    and custom-STT mode wiring.
    """
    captured = {}

    async def fake_stream_handler(
        websocket,
        uid,
        language,
        sample_rate,
        codec,
        channels,
        include_speech_profile,
        stt_service,
        conversation_timeout=120,
        source=None,
        custom_stt_mode=None,
        onboarding_mode=False,
        call_id=None,
    ):
        captured.update(
            {
                "uid": uid,
                "language": language,
                "sample_rate": sample_rate,
                "codec": codec,
                "channels": channels,
                "include_speech_profile": include_speech_profile,
                "stt_service": stt_service,
                "conversation_timeout": conversation_timeout,
                "source": source,
                "custom_stt_mode": getattr(custom_stt_mode, "value", str(custom_stt_mode)),
                "onboarding_mode": onboarding_mode,
                "call_id": call_id,
            }
        )
        await websocket.send_json({"type": "fake_stt_ready", "uid": uid, "custom_stt": captured["custom_stt_mode"]})

    import routers.transcribe as transcribe_router

    monkeypatch.setattr(transcribe_router, "_stream_handler", fake_stream_handler)

    with client.websocket_connect(
        "/v4/web/listen?custom_stt=enabled&sample_rate=8000&codec=pcm8&conversation_timeout=1&source=e2e"
    ) as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": "dev-token"}))
        auth_response = websocket.receive_json()
        assert auth_response == {"type": "auth_response", "success": True}
        ready = websocket.receive_json()
        assert ready == {"type": "fake_stt_ready", "uid": "123", "custom_stt": "enabled"}

    assert captured["uid"] == "123"
    assert captured["language"] == "en"
    assert captured["sample_rate"] == 8000
    assert captured["codec"] == "pcm8"
    assert captured["channels"] == 1
    assert captured["include_speech_profile"] is True
    assert captured["stt_service"] is None
    assert captured["conversation_timeout"] == 1
    assert captured["source"] == "e2e"
    assert captured["custom_stt_mode"] == "enabled"
