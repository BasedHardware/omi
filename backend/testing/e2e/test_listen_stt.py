"""Listen/STT websocket seam coverage."""

import json

from fakes.firestore import get_mock_firestore, read_conversation
from fakes.stt import fake_suggested_transcript_event


def _seed_listen_user(uid: str):
    get_mock_firestore().collection("users").document(uid).set(
        {
            "id": uid,
            "language": "en",
            "private_cloud_sync_enabled": False,
            "transcription_preferences": {"uses_custom_stt": True},
        }
    )


def _receive_until(websocket, predicate, *, limit=20):
    for _ in range(limit):
        message = websocket.receive()
        if message.get("type") == "websocket.close":
            raise AssertionError(f"websocket closed before expected message: {message}")
        text = message.get("text")
        if not text or text == "ping":
            continue
        payload = json.loads(text)
        if predicate(payload):
            return payload
    raise AssertionError("expected websocket payload was not received")


def _is_ready_event(payload):
    return isinstance(payload, dict) and payload.get("type") == "service_status" and payload.get("status") == "ready"


def _is_segment_batch(payload):
    return isinstance(payload, list) and payload and payload[0].get("id") == "seg-custom-stt-1"


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


def test_web_listen_custom_stt_suggested_transcript_is_emitted_and_persisted(client, auth_headers, test_uid):
    """Custom-STT suggested transcript exercises real listen handling after auth.

    This is still a named seam: the app/client side STT event is deterministic and
    Deepgram is not contacted, but the real route, websocket loop, transcript
    normalization, client emission, and fake-Firestore persistence all run.
    """
    _seed_listen_user(test_uid)

    with client.websocket_connect(
        "/v4/web/listen?custom_stt=enabled&sample_rate=8000&codec=pcm8&source=desktop"
    ) as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": "dev-token"}))
        auth_response = websocket.receive_json()
        assert auth_response == {"type": "auth_response", "success": True}
        _receive_until(websocket, _is_ready_event)

        websocket.send_bytes(b"\x80" * 320)
        websocket.send_text(json.dumps(fake_suggested_transcript_event()))

        emitted_segments = _receive_until(websocket, _is_segment_batch)

    expected_segment = {
        "id": "seg-custom-stt-1",
        "text": "Hermetic custom STT transcript from the listen harness.",
        "speaker": "SPEAKER_00",
        "speaker_id": 0,
        "is_user": True,
        "person_id": None,
        "translations": [],
        "speech_profile_processed": True,
        "stt_provider": "e2e-custom-stt",
    }
    assert len(emitted_segments) == 1
    emitted_segment = emitted_segments[0]
    assert {k: emitted_segment[k] for k in expected_segment} == expected_segment
    assert abs(emitted_segment["start"]) < 0.01
    assert abs((emitted_segment["end"] - emitted_segment["start"]) - 1.25) < 0.000001

    conversations = list(
        get_mock_firestore().collection("users").document(test_uid).collection("conversations").stream()
    )
    assert len(conversations) == 1
    conversation = read_conversation(test_uid, conversations[0].id)
    assert conversation is not None
    assert getattr(conversation["source"], "value", conversation["source"]) == "desktop"
    assert getattr(conversation["status"], "value", conversation["status"]) == "in_progress"
    assert isinstance(conversation["transcript_segments"], str)

    persisted = client.get(f"/v1/conversations/{conversations[0].id}", headers=auth_headers)
    assert persisted.status_code == 200, persisted.text
    persisted_conversation = persisted.json()
    assert persisted_conversation["source"] == "desktop"
    assert persisted_conversation["status"] == "in_progress"
    assert persisted_conversation["transcript_segments"] == emitted_segments
