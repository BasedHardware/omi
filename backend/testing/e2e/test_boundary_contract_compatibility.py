"""Boundary contract e2e coverage for mobile/client-facing validation.

These tests exercise the real FastAPI routes through the hermetic harness. Unit
coverage owns the pure validation helpers; this file pins the integration seams:
FastAPI parameter binding, auth, multipart parsing, fake storage side effects,
sync upload filename handling, and listen WebSocket close behavior.
"""

import json
import shutil
from pathlib import Path

from fakes.storage import list_storage_files
from listen_test_helpers import is_ready_event, receive_until, seed_listen_user


def _fake_png_file():
    return {"file": ("logo.png", b"not-a-real-png-but-validation-runs-first", "image/png")}


def test_malformed_app_form_json_is_rejected_before_storage_write(client, auth_headers):
    response = client.post(
        "/v1/apps",
        data={"app_data": "not-json"},
        files=_fake_png_file(),
        headers=auth_headers,
    )

    assert response.status_code == 422, response.text
    assert "app_data" in response.json()["detail"]
    assert list_storage_files("plugins-logos") == []
    assert list_storage_files("app-thumbnails") == []


def test_persona_form_json_must_be_an_object(client, auth_headers):
    response = client.post(
        "/v1/personas",
        data={"persona_data": "[]"},
        files=_fake_png_file(),
        headers=auth_headers,
    )

    assert response.status_code == 422, response.text
    assert "persona_data" in response.json()["detail"]
    assert list_storage_files("plugins-logos") == []


def test_real_routes_reject_invalid_boundary_query_values_without_500(client, auth_headers):
    cases = [
        ("/v1/conversations?limit=0", 422),
        ("/v1/conversations?offset=-1", 422),
        ("/v1/calendar/meetings?limit=101", 422),
        ("/v1/goals/goal-123/history?days=0", 422),
        ("/v1/goals/goal-123/history?days=366", 422),
        ("/v1/scores?date=2024-02-30", 422),
        ("/v1/daily-score?date=2024-02-30", 422),
        ("/v1/focus-sessions?date=2024-02-30", 422),
    ]

    for path, expected_status in cases:
        response = client.get(path, headers=auth_headers)

        assert response.status_code == expected_status, f"{path}: {response.text}"
        assert response.status_code < 500
        assert "detail" in response.json()


def test_v2_sync_rejects_invalid_upload_timestamps_before_creating_job(client, auth_headers):
    sync_dir = Path("syncing/123")
    for filename in [
        "audio_0.bin",
        "audio_999999999999999999999999.bin",
        "audio_not-a-timestamp.bin",
    ]:
        shutil.rmtree(sync_dir, ignore_errors=True)

        response = client.post(
            "/v2/sync-local-files",
            files=[("files", (filename, b"invalid-opus-data", "application/octet-stream"))],
            headers=auth_headers,
        )

        assert response.status_code == 400, f"{filename}: {response.text}"
        assert "invalid timestamp" in response.json()["detail"]
        assert list_storage_files("sync-temporal") == []
        assert [path for path in sync_dir.glob("**/*") if path.is_file()] == []
    shutil.rmtree(sync_dir, ignore_errors=True)


def test_invalid_listen_image_chunk_closes_websocket_with_policy_violation(client, test_uid):
    seed_listen_user(test_uid)

    with client.websocket_connect(
        "/v4/web/listen?custom_stt=enabled&sample_rate=8000&codec=pcm8&channels=2&source=phone_call"
    ) as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": "dev-token"}))
        assert websocket.receive_json() == {"type": "auth_response", "success": True}
        receive_until(websocket, is_ready_event)

        websocket.send_text(json.dumps({"type": "image_chunk", "id": "img-1", "index": 2, "total": 2, "data": "abc"}))
        close_message = websocket.receive()

    assert close_message["type"] == "websocket.close"
    assert close_message["code"] == 1008
