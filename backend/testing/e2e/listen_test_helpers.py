"""Shared helpers for hermetic listen websocket e2e tests."""

import json
import time

from anyio import ClosedResourceError, EndOfStream, WouldBlock

from fakes.firestore import get_mock_firestore


def seed_listen_user(uid: str, *, uses_custom_stt: bool = True, single_language_mode: bool = False):
    """Seed the live-route preference fields explicitly for provider-routing tests."""

    get_mock_firestore().collection("users").document(uid).set(
        {
            "id": uid,
            "language": "en",
            "private_cloud_sync_enabled": False,
            "transcription_preferences": {
                "uses_custom_stt": uses_custom_stt,
                "single_language_mode": single_language_mode,
            },
        }
    )


def receive_message(websocket, *, timeout: float = 1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return websocket._send_rx.receive_nowait()
        except WouldBlock:
            time.sleep(0.01)
        except (ClosedResourceError, EndOfStream) as e:
            raise AssertionError("websocket receive stream closed before expected message") from e
    raise TimeoutError("timed out waiting for websocket message")


def receive_until(websocket, predicate, *, limit=20, timeout: float = 3.0):
    deadline = time.monotonic() + timeout
    for _ in range(limit):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            message = receive_message(websocket, timeout=min(0.5, remaining))
        except TimeoutError:
            continue
        if message.get("type") == "websocket.close":
            raise AssertionError(f"websocket closed before expected message: {message}")
        text = message.get("text")
        if not text or text == "ping":
            continue
        payload = json.loads(text)
        if predicate(payload):
            return payload
    raise AssertionError("expected websocket payload was not received")


def is_ready_event(payload):
    return isinstance(payload, dict) and payload.get("type") == "service_status" and payload.get("status") == "ready"


def is_conversation_session_event(payload):
    return isinstance(payload, dict) and payload.get("type") == "conversation_session"


def is_segment_batch(payload):
    return isinstance(payload, list) and payload and payload[0].get("id") == "seg-custom-stt-1"


def is_streaming_segment_batch(payload):
    return isinstance(payload, list) and payload and payload[0].get("id") == "seg-streaming-stt-1"
