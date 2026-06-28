"""Shared helpers for hermetic listen websocket e2e tests."""

import json

from fakes.firestore import get_mock_firestore


def seed_listen_user(uid: str):
    get_mock_firestore().collection("users").document(uid).set(
        {
            "id": uid,
            "language": "en",
            "private_cloud_sync_enabled": False,
            "transcription_preferences": {"uses_custom_stt": True},
        }
    )


def receive_until(websocket, predicate, *, limit=20):
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


def is_ready_event(payload):
    return isinstance(payload, dict) and payload.get("type") == "service_status" and payload.get("status") == "ready"


def is_conversation_session_event(payload):
    return isinstance(payload, dict) and payload.get("type") == "conversation_session"


def is_segment_batch(payload):
    return isinstance(payload, list) and payload and payload[0].get("id") == "seg-custom-stt-1"
