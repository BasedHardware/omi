"""Core hermetic E2E coverage for high-churn backend flows."""

from testing.e2e.sync_helpers import patch_fresh_sync_lane
import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fakes.firestore import read_conversation, seed_conversation
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


def test_sync_v2_job_runs_pipeline_and_polls_completed_result(client, auth_headers, monkeypatch):
    """The v2 sync API should create, run, and expose a completed job against hermetic fakes."""
    patch_fresh_sync_lane(monkeypatch)
    scheduled = []
    sync_conversation_id = "sync-core-flow-conversation"

    def capture_background_task(coro, *, name):
        scheduled.append((name, coro))
        return None

    def fake_decode_files_to_wav(raw_paths):
        assert raw_paths
        wav_paths = []
        for raw_path in raw_paths:
            wav_path = str(Path(raw_path).with_suffix(".wav"))
            Path(wav_path).write_bytes(b"fake wav bytes")
            wav_paths.append(wav_path)
        return wav_paths

    def fake_retrieve_vad_segments(path, segmented_paths, errors=None):
        from utils.sync.files import get_timestamp_from_path

        segment_path = f"{Path(path).parent}/{int(get_timestamp_from_path(path))}.wav"
        Path(segment_path).write_bytes(b"fake wav bytes")
        segmented_paths.add(segment_path)

    def fake_process_segment(
        path,
        uid,
        response,
        lock,
        errors,
        source,
        is_locked,
        transcription_prefs,
        person_embeddings_cache,
        target_conversation_id,
        turnstile,
        **kwargs,
    ):
        if turnstile:
            turnstile.complete(path)
        seed_conversation(
            uid,
            _completed_conversation_payload(sync_conversation_id, source=getattr(source, "value", source)),
        )
        with lock:
            response["new_memories"].add(sync_conversation_id)
        return True

    sync_router = sys.modules["routers.sync"]
    sync_pipeline = sys.modules["utils.sync.pipeline"]
    monkeypatch.setattr(sync_router, "start_background_task", capture_background_task)
    monkeypatch.setattr(sync_pipeline, "decode_files_to_wav", fake_decode_files_to_wav)
    monkeypatch.setattr(sync_pipeline, "retrieve_vad_segments", fake_retrieve_vad_segments)
    monkeypatch.setattr(sync_pipeline, "get_wav_duration", lambda path: 2.0)
    monkeypatch.setattr(sync_pipeline, "process_segment", fake_process_segment)
    monkeypatch.setattr(sync_pipeline, "_reprocess_merged_conversations", lambda uid, response: None)
    monkeypatch.setattr(sync_pipeline, "build_person_embeddings_cache", lambda uid: {})
    monkeypatch.setattr(sync_router, "get_hard_restriction_status", lambda uid: (False, None))
    monkeypatch.setattr(sync_router, "has_transcription_credits", lambda uid: True)
    monkeypatch.setattr(sync_router, "is_cloud_tasks_dispatch_enabled", lambda: False)
    monkeypatch.setattr(sync_router, "has_byok_keys", lambda: False)
    monkeypatch.setattr(sync_pipeline, "FAIR_USE_ENABLED", False)

    response = client.post(
        "/v2/sync-local-files",
        headers=auth_headers,
        files={
            "files": (
                "audio_omi_pcm16_16000_1_1760000000.bin",
                b"fake-pcm-frame",
                "application/octet-stream",
            )
        },
    )
    assert response.status_code == 202, response.text
    created_job = response.json()
    assert created_job["status"] == "queued"
    assert created_job["total_files"] == 1
    assert len(scheduled) == 1
    assert scheduled[0][0].startswith("sync_pipeline:")

    asyncio.run(scheduled[0][1])

    status = client.get(f"/v2/sync-local-files/{created_job['job_id']}", headers=auth_headers)
    assert status.status_code == 200, status.text
    status_body = status.json()
    assert status_body["status"] == "completed"
    assert status_body["successful_segments"] == 1
    assert status_body["result"]["new_memories"] == [sync_conversation_id]

    conversation = read_conversation("123", sync_conversation_id)
    assert conversation is not None
    assert conversation["status"] == "completed"
