"""Listen/STT websocket seam coverage."""

import json
import uuid

from fakes.firestore import get_mock_firestore, read_conversation
from fakes.stt import fake_suggested_transcript_event, install_streaming_stt_fake
from listen_test_helpers import (
    is_conversation_session_event,
    is_ready_event,
    is_segment_batch,
    is_streaming_segment_batch,
    receive_message,
    receive_until,
    seed_listen_user,
)


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
        client_conversation_id=None,
        client_device_context=None,
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
                "client_conversation_id": client_conversation_id,
                "client_device_id": getattr(client_device_context, "client_device_id", None),
                "client_platform": getattr(client_device_context, "platform", None),
            }
        )
        await websocket.send_json({"type": "fake_stt_ready", "uid": uid, "custom_stt": captured["custom_stt_mode"]})

    import routers.transcribe as transcribe_router

    monkeypatch.setattr(transcribe_router, "_stream_handler", fake_stream_handler)

    with client.websocket_connect(
        "/v4/web/listen?custom_stt=enabled&sample_rate=8000&codec=pcm8&conversation_timeout=1&source=e2e"
    ) as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": "dev-token", "device_id_hash": "a1b2c3d4"}))
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
    assert captured["client_device_id"] == "web_a1b2c3d4"
    assert captured["client_platform"] == "web"


def test_web_listen_custom_stt_suggested_transcript_is_emitted_and_persisted(client, auth_headers, test_uid):
    """Custom-STT suggested transcript exercises real listen handling after auth.

    This is still a named seam: the app/client side STT event is deterministic and
    Deepgram is not contacted, but the real route, websocket loop, transcript
    normalization, client emission, and fake-Firestore persistence all run.
    """
    seed_listen_user(test_uid)

    with client.websocket_connect(
        "/v4/web/listen?custom_stt=enabled&sample_rate=8000&codec=pcm8&source=desktop"
    ) as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": "dev-token"}))
        auth_response = websocket.receive_json()
        assert auth_response == {"type": "auth_response", "success": True}
        session_event = receive_until(websocket, is_conversation_session_event)
        uuid.UUID(session_event["conversation_id"])
        assert session_event["status"] == "in_progress"
        receive_until(websocket, is_ready_event)

        websocket.send_bytes(b"\x80" * 320)
        websocket.send_text(json.dumps(fake_suggested_transcript_event()))

        emitted_segments = receive_until(websocket, is_segment_batch)

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
    assert conversations[0].id == session_event["conversation_id"]
    assert getattr(conversation["source"], "value", conversation["source"]) == "desktop"
    assert getattr(conversation["status"], "value", conversation["status"]) == "in_progress"
    assert isinstance(conversation["transcript_segments"], str)

    persisted = client.get(f"/v1/conversations/{conversations[0].id}", headers=auth_headers)
    assert persisted.status_code == 200, persisted.text
    persisted_conversation = persisted.json()
    assert persisted_conversation["source"] == "desktop"
    assert persisted_conversation["status"] == "in_progress"
    assert persisted_conversation["transcript_segments"] == emitted_segments


def test_web_listen_reconnect_emits_existing_conversation_session_id(client, test_uid):
    """A fast reconnect should expose the same active conversation id instead of making clients infer it."""
    seed_listen_user(test_uid)

    with client.websocket_connect(
        "/v4/web/listen?custom_stt=enabled&sample_rate=8000&codec=pcm8&conversation_timeout=120&source=desktop"
    ) as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": "dev-token"}))
        assert websocket.receive_json() == {"type": "auth_response", "success": True}
        first_event = receive_until(websocket, is_conversation_session_event)
        uuid.UUID(first_event["conversation_id"])
        receive_until(websocket, is_ready_event)

    with client.websocket_connect(
        "/v4/web/listen?custom_stt=enabled&sample_rate=8000&codec=pcm8&conversation_timeout=120&source=desktop"
    ) as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": "dev-token"}))
        assert websocket.receive_json() == {"type": "auth_response", "success": True}
        second_event = receive_until(websocket, is_conversation_session_event)
        receive_until(websocket, is_ready_event)

    assert second_event["conversation_id"] == first_event["conversation_id"]
    conversations = list(
        get_mock_firestore().collection("users").document(test_uid).collection("conversations").stream()
    )
    assert [conversation.id for conversation in conversations] == [first_event["conversation_id"]]


def test_listen_client_conversation_id_creates_requested_conversation(client, test_uid):
    seed_listen_user(test_uid)
    client_conversation_id = str(uuid.uuid4())

    with client.websocket_connect(
        "/v4/web/listen?"
        f"custom_stt=enabled&sample_rate=8000&codec=pcm8&conversation_timeout=120"
        f"&source=desktop&client_conversation_id={client_conversation_id}"
    ) as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": "dev-token"}))
        assert websocket.receive_json() == {"type": "auth_response", "success": True}
        session_event = receive_until(websocket, is_conversation_session_event)
        receive_until(websocket, is_ready_event)

    assert session_event["conversation_id"] == client_conversation_id
    assert session_event["recording_session_id"] == client_conversation_id
    conversation = read_conversation(test_uid, client_conversation_id)
    assert conversation is not None
    assert conversation["id"] == client_conversation_id
    assert getattr(conversation["source"], "value", conversation["source"]) == "desktop"
    assert getattr(conversation["status"], "value", conversation["status"]) == "in_progress"


def test_listen_client_conversation_id_never_resumes_global_conversation(client, test_uid, monkeypatch):
    """An identified desktop recording must not inherit a stale user-global pointer."""
    seed_listen_user(test_uid)
    client_conversation_id = str(uuid.uuid4())
    stale_conversation = {
        "id": str(uuid.uuid4()),
        "finished_at": None,
        "status": "in_progress",
    }

    import routers.transcribe as transcribe_router

    def stale_global_lookup(_uid):
        raise AssertionError(f"identified listen must not resume stale global conversation {stale_conversation['id']}")

    monkeypatch.setattr(transcribe_router, "retrieve_in_progress_conversation", stale_global_lookup)

    with client.websocket_connect(
        "/v4/web/listen?"
        f"custom_stt=enabled&sample_rate=8000&codec=pcm8&conversation_timeout=120"
        f"&source=desktop&client_conversation_id={client_conversation_id}"
    ) as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": "dev-token"}))
        assert websocket.receive_json() == {"type": "auth_response", "success": True}
        session_event = receive_until(websocket, is_conversation_session_event)
        receive_until(websocket, is_ready_event)

    assert session_event["conversation_id"] == client_conversation_id
    assert session_event["recording_session_id"] == client_conversation_id


def test_listen_client_conversation_id_reconnects_same_session(client, test_uid):
    seed_listen_user(test_uid)
    client_conversation_id = str(uuid.uuid4())

    for _ in range(2):
        with client.websocket_connect(
            "/v4/web/listen?"
            f"custom_stt=enabled&sample_rate=8000&codec=pcm8&conversation_timeout=120"
            f"&source=desktop&client_conversation_id={client_conversation_id}"
        ) as websocket:
            websocket.send_text(json.dumps({"type": "auth", "token": "dev-token"}))
            assert websocket.receive_json() == {"type": "auth_response", "success": True}
            session_event = receive_until(websocket, is_conversation_session_event)
            receive_until(websocket, is_ready_event)
            assert session_event["conversation_id"] == client_conversation_id

    conversations = list(
        get_mock_firestore().collection("users").document(test_uid).collection("conversations").stream()
    )
    assert [conversation.id for conversation in conversations] == [client_conversation_id]


def test_web_listen_streaming_stt_happy_path_persists_segments(client, auth_headers, test_uid, monkeypatch):
    seed_listen_user(test_uid, uses_custom_stt=False)
    sockets = install_streaming_stt_fake(monkeypatch)

    with client.websocket_connect("/v4/web/listen?sample_rate=8000&codec=pcm8&source=desktop") as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": "dev-token"}))
        assert websocket.receive_json() == {"type": "auth_response", "success": True}
        session_event = receive_until(websocket, is_conversation_session_event)
        uuid.UUID(session_event["conversation_id"])
        receive_until(websocket, is_ready_event)

        websocket.send_bytes(b"\x80" * 320)
        emitted_segments = receive_until(websocket, is_streaming_segment_batch)

    assert len(sockets) == 1
    assert sockets[0].sent_chunks
    assert sockets[0].drain_calls == 1
    assert sockets[0].finish_calls == 1

    expected_segment = {
        "id": "seg-streaming-stt-1",
        "text": "Hermetic streaming STT transcript from the fake socket.",
        "speaker": "SPEAKER_00",
        "speaker_id": 0,
        "is_user": True,
        "person_id": None,
        "translations": [],
        "speech_profile_processed": True,
        "stt_provider": "e2e-streaming-stt",
    }
    assert len(emitted_segments) == 1
    assert {k: emitted_segments[0][k] for k in expected_segment} == expected_segment

    persisted = client.get(f"/v1/conversations/{session_event['conversation_id']}", headers=auth_headers)
    assert persisted.status_code == 200, persisted.text
    body = persisted.json()
    assert body["source"] == "desktop"
    assert body["status"] == "in_progress"
    assert body["transcript_segments"] == emitted_segments


def test_web_listen_streaming_stt_send_failure_emits_terminal_status_then_closes(
    client,
    test_uid,
    monkeypatch,
):
    """A provider death is explicit and terminal instead of leaving a green socket."""

    seed_listen_user(test_uid, uses_custom_stt=False)
    sockets = install_streaming_stt_fake(monkeypatch, die_on_first_send=True)

    with client.websocket_connect("/v4/web/listen?sample_rate=8000&codec=pcm8&source=desktop") as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": "dev-token"}))
        assert websocket.receive_json() == {"type": "auth_response", "success": True}
        receive_until(websocket, is_conversation_session_event)
        receive_until(websocket, is_ready_event)

        websocket.send_bytes(b"\x80" * 320)

        payloads = []
        close_message = None
        for _ in range(20):
            message = receive_message(websocket, timeout=1.0)
            if message.get("type") == "websocket.close":
                close_message = message
                break
            text = message.get("text")
            if text and text != "ping":
                payloads.append(json.loads(text))

    terminal_statuses = [
        payload
        for payload in payloads
        if isinstance(payload, dict)
        and payload.get("type") == "service_status"
        and payload.get("status") == "stt_failed"
    ]
    assert terminal_statuses == [
        {
            "type": "service_status",
            "status": "stt_failed",
            "status_text": "The transcription provider could not complete the request.",
            "outcome": "upstream_error",
            "provider": "deepgram",
            "retryable": True,
            "reason": "send_failed",
        }
    ]
    assert not any(isinstance(payload, list) for payload in payloads)
    assert close_message == {
        "type": "websocket.close",
        "code": 1011,
        "reason": "transcription_service_unavailable",
    }
    assert len(sockets) == 1
    assert len(sockets[0].sent_chunks) == 1


def test_web_listen_reconnect_reuses_active_conversation_id(client, test_uid, monkeypatch):
    seed_listen_user(test_uid, uses_custom_stt=False)
    sockets = install_streaming_stt_fake(monkeypatch)

    with client.websocket_connect(
        "/v4/web/listen?sample_rate=8000&codec=pcm8&conversation_timeout=120&source=desktop"
    ) as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": "dev-token"}))
        assert websocket.receive_json() == {"type": "auth_response", "success": True}
        first_event = receive_until(websocket, is_conversation_session_event)
        uuid.UUID(first_event["conversation_id"])
        receive_until(websocket, is_ready_event)

    with client.websocket_connect(
        "/v4/web/listen?sample_rate=8000&codec=pcm8&conversation_timeout=120&source=desktop"
    ) as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": "dev-token"}))
        assert websocket.receive_json() == {"type": "auth_response", "success": True}
        second_event = receive_until(websocket, is_conversation_session_event)
        receive_until(websocket, is_ready_event)

    assert second_event["conversation_id"] == first_event["conversation_id"]
    assert len(sockets) == 2
    conversations = list(
        get_mock_firestore().collection("users").document(test_uid).collection("conversations").stream()
    )
    assert [conversation.id for conversation in conversations] == [first_event["conversation_id"]]


def test_web_listen_teardown_drains_and_finishes_stt_socket(client, test_uid, monkeypatch):
    seed_listen_user(test_uid, uses_custom_stt=False)
    sockets = install_streaming_stt_fake(monkeypatch)

    with client.websocket_connect("/v4/web/listen?sample_rate=8000&codec=pcm8&source=desktop") as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": "dev-token"}))
        assert websocket.receive_json() == {"type": "auth_response", "success": True}
        receive_until(websocket, is_conversation_session_event)
        receive_until(websocket, is_ready_event)
        websocket.send_bytes(b"\x80" * 320)
        receive_until(websocket, is_streaming_segment_batch)

    assert len(sockets) == 1
    assert sockets[0].sent_chunks
    assert sockets[0].drain_calls == 1
    assert sockets[0].finish_calls == 1
