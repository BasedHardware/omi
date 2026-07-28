"""Hermetic sync v2 lifecycle coverage."""

from testing.e2e.sync_helpers import patch_fresh_sync_lane

import time
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from fakes.firestore import read_conversation, seed_conversation
from models.conversation import Conversation
from models.conversation_enums import ConversationStatus
from models.transcript_segment import TranscriptSegment

TERMINAL_SYNC_STATUSES = {"completed", "partial_failure", "failed"}


def _sync_filename(offset_seconds: int = 60) -> str:
    timestamp = int(time.time()) - offset_seconds
    return f"audio_{timestamp}.bin"


def _poll_sync_job(client, auth_headers, job_id: str, *, deadline_seconds: float = 5.0):
    deadline = time.monotonic() + deadline_seconds
    last_body = None
    while time.monotonic() < deadline:
        response = client.get(f"/v2/sync-local-files/{job_id}", headers=auth_headers)
        assert response.status_code == 200, response.text
        last_body = response.json()
        if last_body["status"] in TERMINAL_SYNC_STATUSES:
            return last_body
        time.sleep(0.05)
    raise AssertionError(f"sync job {job_id} did not reach a terminal state: {last_body}")


def _drain_background_coroutines(pending_coroutines):
    while pending_coroutines:
        asyncio.run(pending_coroutines.pop(0))


def _patch_sync_pipeline(
    monkeypatch,
    *,
    transcript_text: str,
    reprocessed: list[str],
):
    import routers.sync as sync_router
    import utils.sync.pipeline as sync_pipeline

    pending_coroutines = []

    def capture_background_task(coro, *, name):
        pending_coroutines.append(coro)

    def fake_decode_files_to_wav(raw_paths):
        wav_paths = []
        for raw_path in raw_paths:
            wav_path = str(Path(raw_path).with_suffix(".wav"))
            Path(wav_path).write_bytes(b"fake wav bytes")
            wav_paths.append(wav_path)
        return wav_paths

    def fake_retrieve_vad_segments(path, segmented_paths, vad_errors):
        from utils.sync.files import get_timestamp_from_path

        segment_path = f"{Path(path).parent}/{int(get_timestamp_from_path(path))}.wav"
        Path(segment_path).write_bytes(b"fake wav bytes")
        segmented_paths.add(segment_path)

    def fake_prerecorded(*args, **kwargs):
        return (
            [
                {
                    "word": transcript_text,
                    "start": 0.0,
                    "end": 1.25,
                    "speaker": 0,
                    "speaker_confidence": 0.99,
                    "confidence": 0.99,
                }
            ],
            "en",
        )

    def fake_postprocess_words(words, offset):
        return [
            TranscriptSegment(
                id="seg-sync-e2e",
                text=transcript_text,
                speaker="SPEAKER_00",
                speaker_id=0,
                is_user=True,
                start=0.0,
                end=1.25,
            )
        ]

    def fake_process_conversation(uid, language, conversation, persistence_observer=None):
        import database.conversations as conversations_db
        from models.structured import Structured

        conversation_obj = Conversation(
            id="sync-created-conversation",
            uid=uid,
            created_at=conversation.started_at,
            started_at=conversation.started_at,
            finished_at=conversation.finished_at,
            source=conversation.source,
            language=language,
            structured=Structured(
                title="Hermetic Sync Conversation",
                overview="Sync v2 produced a deterministic conversation.",
                emoji="🧪",
                category="work",
            ),
            transcript_segments=conversation.transcript_segments,
            discarded=False,
            status=ConversationStatus.completed,
            is_locked=conversation.is_locked,
        )
        conversations_db.upsert_conversation_with_lifecycle(uid, conversation_obj.dict())
        if persistence_observer is not None:
            persistence_observer(True)
        return conversation_obj

    def fake_reprocess_after_update(uid, conversation_id, language):
        reprocessed.append(conversation_id)

        conversation = read_conversation(uid, conversation_id)
        assert conversation is not None
        conversation["id"] = conversation_id
        structured = dict(conversation.get("structured") or {})
        structured.update(
            {
                "title": "Hermetic Sync Conversation Reprocessed",
                "overview": "The target conversation was reprocessed once after sync merge.",
                "emoji": "🧪",
                "category": "work",
                "action_items": [],
                "events": [],
            }
        )
        updated = dict(conversation)
        updated["id"] = conversation_id
        updated["structured"] = structured
        seed_conversation(uid, updated)

    monkeypatch.setattr(sync_pipeline, "decode_files_to_wav", fake_decode_files_to_wav)
    monkeypatch.setattr(sync_pipeline, "retrieve_vad_segments", fake_retrieve_vad_segments)
    monkeypatch.setattr(sync_pipeline, "get_wav_duration", lambda path: 1.25)
    monkeypatch.setattr(sync_router, "has_transcription_credits", lambda uid: True)
    monkeypatch.setattr(sync_pipeline, "build_person_embeddings_cache", lambda uid: {})
    monkeypatch.setattr(sync_pipeline, "get_syncing_file_temporal_signed_url", lambda path: path)
    monkeypatch.setattr(sync_pipeline, "schedule_syncing_temporal_file_deletion", lambda path: None)
    monkeypatch.setattr(sync_pipeline, "prerecorded", fake_prerecorded)
    monkeypatch.setattr(sync_pipeline, "postprocess_words", fake_postprocess_words)
    monkeypatch.setattr(sync_pipeline, "process_conversation", fake_process_conversation)
    monkeypatch.setattr(sync_pipeline, "_reprocess_conversation_after_update", fake_reprocess_after_update)
    monkeypatch.setattr(sync_router, "start_background_task", capture_background_task)
    monkeypatch.setattr(sync_pipeline, "FAIR_USE_ENABLED", False)
    return pending_coroutines


def test_sync_v2_completes_job_and_creates_conversation(client, auth_headers, monkeypatch):
    patch_fresh_sync_lane(monkeypatch)
    reprocessed = []
    pending_coroutines = _patch_sync_pipeline(
        monkeypatch,
        transcript_text="Hermetic sync transcript from a fake prerecorded STT boundary.",
        reprocessed=reprocessed,
    )

    response = client.post(
        "/v2/sync-local-files",
        files=[("files", (_sync_filename(), b"fake-pcm-frame", "application/octet-stream"))],
        headers=auth_headers,
    )
    assert response.status_code == 202, response.text
    queued = response.json()
    assert queued["status"] == "queued"

    _drain_background_coroutines(pending_coroutines)
    job = _poll_sync_job(client, auth_headers, queued["job_id"])
    assert job["status"] == "completed", job
    assert job["total_segments"] == 1
    assert job["successful_segments"] == 1
    assert job["result"]["new_memories"] == ["sync-created-conversation"]
    assert job["result"]["updated_memories"] == []

    persisted = client.get("/v1/conversations/sync-created-conversation", headers=auth_headers)
    assert persisted.status_code == 200, persisted.text
    body = persisted.json()
    assert body["structured"]["title"] == "Hermetic Sync Conversation"
    assert body["status"] == "completed"
    assert [segment["text"] for segment in body["transcript_segments"]] == [
        "Hermetic sync transcript from a fake prerecorded STT boundary."
    ]
    assert read_conversation("123", "sync-created-conversation") is not None
    assert reprocessed == []


def test_sync_v2_merges_into_target_conversation_and_reprocesses_once(client, auth_headers, monkeypatch):
    patch_fresh_sync_lane(monkeypatch)
    import database.conversations as conversations_db

    target_id = "sync-target-conversation"
    timestamp = int(time.time()) - 120
    target_timestamp = timestamp - 3600
    seed_conversation(
        "123",
        {
            "id": target_id,
            "created_at": datetime.fromtimestamp(target_timestamp, tz=timezone.utc).isoformat(),
            "started_at": datetime.fromtimestamp(target_timestamp, tz=timezone.utc).isoformat(),
            "finished_at": datetime.fromtimestamp(target_timestamp + 1, tz=timezone.utc).isoformat(),
            "source": "desktop",
            "language": "en",
            "structured": {
                "title": "Before Sync Merge",
                "overview": "",
                "emoji": "🧠",
                "category": "other",
                "action_items": [],
                "events": [],
            },
            "transcript_segments": [
                {
                    "id": "seg-existing",
                    "text": "Existing live transcript.",
                    "speaker": "SPEAKER_00",
                    "is_user": True,
                    "start": 0.0,
                    "end": 1.0,
                }
            ],
            "discarded": False,
            "status": "completed",
            "is_locked": False,
            "data_protection_level": "standard",
        },
    )
    assert read_conversation("123", target_id) is not None
    assert conversations_db.get_conversation("123", target_id)["id"] == target_id
    reprocessed = []
    pending_coroutines = _patch_sync_pipeline(
        monkeypatch,
        transcript_text="Merged sync transcript appended to the target conversation.",
        reprocessed=reprocessed,
    )

    response = client.post(
        f"/v2/sync-local-files?conversation_id={target_id}",
        files=[("files", (f"audio_{timestamp}.bin", b"fake-pcm-frame", "application/octet-stream"))],
        headers=auth_headers,
    )
    assert response.status_code == 202, response.text

    _drain_background_coroutines(pending_coroutines)
    job = _poll_sync_job(client, auth_headers, response.json()["job_id"])
    assert job["status"] == "completed", job
    assert job["result"]["new_memories"] == []
    assert job["result"]["updated_memories"] == [target_id]
    assert reprocessed == [target_id]

    persisted = client.get(f"/v1/conversations/{target_id}", headers=auth_headers)
    assert persisted.status_code == 200, persisted.text
    body = persisted.json()
    assert body["structured"]["title"] == "Hermetic Sync Conversation Reprocessed"
    assert [segment["text"] for segment in body["transcript_segments"]] == [
        "Existing live transcript.",
        "Merged sync transcript appended to the target conversation.",
    ]
