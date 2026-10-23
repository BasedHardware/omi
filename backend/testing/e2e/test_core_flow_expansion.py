"""Core hermetic E2E coverage for high-churn backend flows."""

import json
import sys
import uuid
from datetime import datetime, timezone

from fakes.stt import fake_suggested_transcript_event
from listen_test_helpers import (
    is_conversation_session_event,
    is_ready_event,
    is_segment_batch,
    receive_until,
    seed_listen_user,
)


def _completed_conversation_payload(conversation_id: str, source: str = "omi") -> dict:
    return {
        "id": conversation_id,
        "created_at": "2025-10-09T08:53:20Z",
        "started_at": "2025-10-09T08:53:20Z",
        "finished_at": "2025-10-09T08:53:22Z",
        "source": source,
        "language": "en",
        "structured": {
            "title": "Hermetic core flow",
            "overview": "A deterministic core-flow conversation.",
            "emoji": ":)",
            "category": "work",
            "action_items": [],
            "events": [],
        },
        "transcript_segments": [
            {
                "id": "seg-core-flow",
                "text": "Hermetic core flow transcript.",
                "speaker": "SPEAKER_00",
                "is_user": True,
                "start": 0.0,
                "end": 1.25,
            }
        ],
        "discarded": False,
        "status": "completed",
        "is_locked": False,
        "data_protection_level": "standard",
    }


def test_transcribe_reconnect_then_finalize_conversation_lifecycle(client, auth_headers, monkeypatch, test_uid):
    """Custom-STT listen creates one in-progress conversation, reconnects to it, then finalizes it."""
    seed_listen_user(test_uid)

    with client.websocket_connect(
        "/v4/web/listen?custom_stt=enabled&sample_rate=8000&codec=pcm8&conversation_timeout=120&source=desktop"
    ) as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": "dev-token"}))
        assert websocket.receive_json() == {"type": "auth_response", "success": True}
        first_session = receive_until(websocket, is_conversation_session_event)
        conversation_id = first_session["conversation_id"]
        uuid.UUID(conversation_id)
        receive_until(websocket, is_ready_event)

        websocket.send_bytes(b"\x80" * 320)
        websocket.send_text(json.dumps(fake_suggested_transcript_event()))
        emitted_segments = receive_until(websocket, is_segment_batch)

    with client.websocket_connect(
        "/v4/web/listen?custom_stt=enabled&sample_rate=8000&codec=pcm8&conversation_timeout=120&source=desktop"
    ) as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": "dev-token"}))
        assert websocket.receive_json() == {"type": "auth_response", "success": True}
        reconnect_session = receive_until(websocket, is_conversation_session_event)
        receive_until(websocket, is_ready_event)

    assert reconnect_session["conversation_id"] == conversation_id
    in_progress = client.get(f"/v1/conversations/{conversation_id}", headers=auth_headers)
    assert in_progress.status_code == 200, in_progress.text
    assert in_progress.json()["status"] == "in_progress"
    assert in_progress.json()["transcript_segments"] == emitted_segments

    def fake_process_conversation(uid, language_code, conversation, **kwargs):
        conversations_db = sys.modules["database.conversations"]
        deserialize_conversation = sys.modules["utils.conversations.factory"].deserialize_conversation
        lifecycle = sys.modules["utils.conversations.lifecycle"]
        structured = conversation.structured.model_dump()
        structured.update(
            {
                "title": "Finalized hermetic listen session",
                "overview": "The listen websocket persisted transcript segments and finalized cleanly.",
                "category": "work",
            }
        )
        conversations_db.update_conversation(
            uid,
            conversation.id,
            {"structured": structured, "finished_at": datetime.now(timezone.utc)},
        )
        lifecycle.complete(uid, conversation.id)
        return deserialize_conversation(conversations_db.get_conversation(uid, conversation.id))

    async def fake_trigger_external_integrations(uid, conversation, **kwargs):
        return []

    # The exact-ID finalize route now hands off to the durable Cloud Tasks
    # worker instead of processing inline. Configure dispatch, stub the enqueue
    # (the hermetic harness cannot reach Cloud Tasks), and patch the expensive
    # processing surfaces the worker calls through the shared finalizer.
    monkeypatch.setenv("LISTEN_FINALIZATION_DISPATCH_MODE", "cloud_tasks")
    monkeypatch.setenv("SYNC_TASKS_PROJECT", "test-e2e-project")
    monkeypatch.setenv("SYNC_TASKS_LOCATION", "us-central1")
    monkeypatch.setenv("LISTEN_FINALIZATION_TASKS_QUEUE", "conversation-finalization")
    monkeypatch.setenv("LISTEN_FINALIZATION_TASKS_HANDLER_URL", "https://example.invalid/finalize")
    monkeypatch.setenv("LISTEN_FINALIZATION_TASKS_INVOKER_SA", "worker@example.invalid")

    cloud_tasks_module = sys.modules["utils.cloud_tasks"]
    monkeypatch.setattr(cloud_tasks_module, "enqueue_listen_finalization_job", lambda *a, **k: None)

    conversations_router = sys.modules["routers.conversations"]
    monkeypatch.setattr(conversations_router, "process_conversation", fake_process_conversation)
    monkeypatch.setattr(conversations_router, "trigger_external_integrations", fake_trigger_external_integrations)

    finalization_router = sys.modules["routers.conversation_finalization"]
    finalizer_module = sys.modules["utils.conversations.finalizer"]
    monkeypatch.setattr(finalizer_module, "process_conversation", fake_process_conversation)
    monkeypatch.setattr(finalizer_module, "extract_memories", lambda *a, **k: None)
    monkeypatch.setattr(finalizer_module, "trigger_external_integrations", fake_trigger_external_integrations)

    finalized = client.post(f"/v1/conversations/{conversation_id}/finalize", headers=auth_headers)
    assert finalized.status_code == 200, finalized.text
    finalized_body = finalized.json()["conversation"]
    assert finalized_body["id"] == conversation_id
    # The route returns promptly after durable dispatch; processing completes
    # when the Cloud Tasks worker claims the job lease below.
    assert finalized_body["status"] == "processing"

    # Drive the durable worker the way Cloud Tasks would. The hermetic harness
    # cannot mint a real OIDC token, so bypass the verifier dependency.
    original_overrides = dict(client.app.dependency_overrides)
    client.app.dependency_overrides[finalization_router.verify_listen_finalization_cloud_tasks_oidc] = lambda: 0
    try:
        job = client.get(f"/v1/conversations/{conversation_id}/finalization", headers=auth_headers)
        assert job.status_code == 200, job.text
        worker_response = client.post(
            "/v1/conversation-finalization-jobs/run",
            json={"job_id": job.json()["job_id"], "dispatch_generation": 1},
        )
        assert worker_response.status_code == 200, worker_response.text
        assert worker_response.json()["status"] == "done"
    finally:
        client.app.dependency_overrides.clear()
        client.app.dependency_overrides.update(original_overrides)

    persisted = client.get(f"/v1/conversations/{conversation_id}", headers=auth_headers)
    assert persisted.status_code == 200, persisted.text
    persisted_body = persisted.json()
    assert persisted_body["status"] == "completed"
    assert persisted_body["structured"]["title"] == "Finalized hermetic listen session"
    assert persisted_body["transcript_segments"] == emitted_segments
