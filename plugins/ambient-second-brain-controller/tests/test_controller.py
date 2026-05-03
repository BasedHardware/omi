import base64
import json
import struct
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import security
import storage
import audio_spool
import task_extraction
from main import app


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    storage.DATABASE_URL = str(tmp_path / "test.sqlite3")
    audio_spool.AUDIO_DIR = tmp_path / "audio_spool_uploads"
    monkeypatch.setenv("WEBHOOK_BASE_URL", "http://testserver")
    monkeypatch.setenv("AMBIENT_PLUGIN_ID", "ambient_second_brain_controller")
    storage.init_db()


@pytest.fixture
def client():
    return TestClient(app)


def register(client):
    response = client.post(
        "/device/register",
        json={
            "omi_user_id": "user-1",
            "device_id": "device-1",
            "device_label": "Pixel",
            "app_install_id": "install-1",
        },
    )
    assert response.status_code == 200
    return response.json()


def policy_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "X-Omi-User-Id": "user-1",
        "X-Omi-Device-Id": "device-1",
        "X-Omi-App-Id": "ambient_second_brain_controller",
    }


def test_policy_signing_and_verification_fixture(client):
    registration = register(client)
    client.post(
        "/settings", json={"omi_user_id": "user-1", "advanced_capture_enabled": True, "default_capture_mode": "normal"}
    )

    response = client.get("/capture/policy/current", headers=policy_headers(registration["device_token"]))

    assert response.status_code == 200
    body = response.json()
    decision = security.validate_signed_policy(body["payload"], body["signature"], body["public_key"])
    assert decision["accepted"] is True
    assert decision["payload"]["plugin_id"] == "ambient_second_brain_controller"
    assert body["structured_payload"]["capture_mode"] == "normal"


def test_policy_requires_valid_device_token(client):
    registration = register(client)

    missing = client.get(
        "/capture/policy/current",
        headers={k: v for k, v in policy_headers(registration["device_token"]).items() if k != "Authorization"},
    )
    invalid = client.get("/capture/policy/current", headers=policy_headers("wrong-token"))
    valid = client.get("/capture/policy/current", headers=policy_headers(registration["device_token"]))

    assert missing.status_code == 401
    assert missing.json()["detail"] == "missing_device_token"
    assert invalid.status_code == 401
    assert invalid.json()["detail"] == "invalid_device_token"
    assert valid.status_code == 200


def test_expired_policy_and_replayed_sequence_rejected(client):
    registration = register(client)
    response = client.get("/capture/policy/current", headers=policy_headers(registration["device_token"]))
    body = response.json()
    payload = json.loads(body["payload"])
    payload["valid_until"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    payload_json, signature = security.sign_payload(payload)

    expired = security.validate_signed_policy(payload_json, signature, body["public_key"])
    replayed = security.validate_signed_policy(body["payload"], body["signature"], body["public_key"], last_sequence=1)

    assert expired["reason"] == "expired"
    assert replayed["reason"] == "replayed_sequence"


def test_revoked_device_cannot_receive_policy(client):
    registration = register(client)
    revoke = client.post("/device/revoke", json={"omi_user_id": "user-1", "device_id": "device-1"})
    assert revoke.status_code == 200

    response = client.get("/capture/policy/current", headers=policy_headers(registration["device_token"]))

    assert response.status_code == 403


def test_telemetry_storage_and_unsafe_rejection(client):
    registration = register(client)
    ok = client.post(
        "/capture/telemetry",
        headers=policy_headers(registration["device_token"]),
        json={
            "omi_user_id": "user-1",
            "device_id": "device-1",
            "event_type": "audio_ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "capture_state": "running",
            "health_state": "AUDIO_OK",
            "metadata": {"wal_depth": 0},
        },
    )
    bad = client.post(
        "/capture/telemetry",
        headers=policy_headers(registration["device_token"]),
        json={
            "omi_user_id": "user-1",
            "device_id": "device-1",
            "event_type": "bad",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": {"transcript": "nope"},
        },
    )

    assert ok.status_code == 200
    assert bad.status_code == 422


def test_fallback_segment_storage_and_dedupe(client):
    registration = register(client)
    payload = {
        "omi_user_id": "user-1",
        "device_id": "device-1",
        "session_id": "session-1",
        "segments": [
            {
                "text": "caption text",
                "source": "accessibility_caption",
                "start": datetime.now(timezone.utc).isoformat(),
                "end": (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(),
                "confidence": 0.82,
                "health_state": "AUDIO_SILENCED_BY_SYSTEM",
                "raw_audio_available": False,
            }
        ],
    }

    first = client.post(
        "/capture/fallback-segments", headers=policy_headers(registration["device_token"]), json=payload
    )
    second = client.post(
        "/capture/fallback-segments", headers=policy_headers(registration["device_token"]), json=payload
    )

    assert first.json()["inserted"] == 1
    assert second.json()["inserted"] == 0
    assert second.json()["skipped"] == 1


def test_capture_endpoints_require_device_token(client):
    register(client)
    event = {
        "omi_user_id": "user-1",
        "device_id": "device-1",
        "event_type": "audio_ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metadata": {},
    }

    response = client.post("/capture/telemetry", json=event)

    assert response.status_code == 401
    assert response.json()["detail"] == "missing_device_token"


def test_audio_spool_storage_and_dedupe(client):
    registration = register(client)
    pcm = b"\x01\x00" * 320
    audio = struct.pack("<I", len(pcm)) + pcm
    payload = {
        "omi_user_id": "user-1",
        "device_id": "device-1",
        "session_id": "session-audio-1",
        "filename": "ambient_android_pcm16_16000_1_1715000000000_1.bin",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "duration_estimate": 0.04,
        "sample_rate": 16000,
        "channels": 1,
        "codec": "pcm16",
        "format": "length_prefixed_pcm",
        "audio_base64": base64.b64encode(audio).decode("ascii"),
    }

    first = client.post("/capture/audio-spool", headers=policy_headers(registration["device_token"]), json=payload)
    second = client.post("/capture/audio-spool", headers=policy_headers(registration["device_token"]), json=payload)

    assert first.status_code == 200
    assert first.json()["inserted"] is True
    assert first.json()["imported"] is False
    assert first.json()["frames"] == 1
    assert second.status_code == 200
    assert second.json()["inserted"] is False


def test_task_extraction_confidence_levels():
    high = task_extraction.extract_tasks_from_text("Remind me to send the proposal tomorrow.")
    medium = task_extraction.extract_tasks_from_text("We should check in with Sam.")
    low = task_extraction.extract_tasks_from_text("Maybe build a dashboard someday.")

    assert high[0].confidence >= 0.8
    assert medium[0].confidence >= 0.6
    assert low[0].confidence < 0.5


def test_chat_tools_manifest_schema(client):
    response = client.get("/.well-known/omi-tools.json")

    assert response.status_code == 200
    manifest = response.json()
    names = {tool["name"] for tool in manifest["tools"]}
    assert "get_capture_status" in names
    assert "create_accountability_rule" in names


def test_health_and_ready_endpoints(client):
    health = client.get("/healthz")
    ready = client.get("/readyz")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert ready.status_code == 200
    body = ready.json()
    assert body["status"] == "ready"
    assert body["base_url"] == "http://testserver"
    assert body["key_id"]
    assert body["key_fingerprint"]


def test_controller_manifests_include_secure_registration_data(client):
    controller = client.get("/.well-known/ambient-controller.json")
    registration = client.get("/.well-known/omi-app-registration.json")

    assert controller.status_code == 200
    assert registration.status_code == 200
    controller_body = controller.json()
    registration_body = registration.json()
    assert controller_body["policy_url"] == "http://testserver/capture/policy/current"
    assert controller_body["public_key"]
    assert registration_body["external_integration"]["capture_controller_public_key"] == controller_body["public_key"]
    assert registration_body["external_integration"]["capture_controller_key_id"] == controller_body["key_id"]
    assert "ambient_capture_controller" in registration_body["capabilities"]


def test_device_registration_creates_enabled_default_settings(client):
    register(client)
    settings = storage.get_settings("user-1")

    assert settings.advanced_capture_enabled is True
    assert settings.default_capture_mode == "normal"
    assert settings.allow_accessibility_mode is True
    assert settings.allow_caption_fallback is True
    assert settings.allow_audio_upload is True


def test_settings_persistence(client):
    response = client.post(
        "/settings",
        json={"omi_user_id": "user-1", "advanced_capture_enabled": True, "default_capture_mode": "meeting"},
    )
    loaded = client.get("/settings", params={"omi_user_id": "user-1"})

    assert response.status_code == 200
    assert loaded.json()["default_capture_mode"] == "meeting"
