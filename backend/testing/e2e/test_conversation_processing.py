"""Hermetic conversation create/process/finalize lifecycle coverage."""

from datetime import datetime, timezone

from fakes.firestore import read_action_items, read_conversation, seed_conversation
from models.memories import Memory
from models.structured import ActionItem, Structured
from models.transcript_segment import TranscriptSegment


class UnexpectedLLMCall(BaseException):
    pass


def _patch_process_conversation_boundaries(monkeypatch):
    import utils.conversations.process_conversation as process_module
    import utils.llm.knowledge_graph as kg_module

    kg_calls = []

    def run_selected_postprocess(_executor, fn, *args, **kwargs):
        if fn.__name__ in {"_extract_memories", "_save_action_items"}:
            fn(*args, **kwargs)

        class DoneFuture:
            def result(self, timeout=None):
                return None

        return DoneFuture()

    def record_kg_extract(*args, **kwargs):
        kg_calls.append((args, kwargs))
        return {"nodes": [], "edges": []}

    monkeypatch.setattr(process_module, "is_trial_paywalled", lambda *args, **kwargs: False)
    monkeypatch.setattr(process_module, "should_defer_desktop_processing", lambda uid: False)
    monkeypatch.setattr(process_module, "get_user_name", lambda uid, use_default=True: "David")
    monkeypatch.setattr(process_module.notification_db, "get_user_time_zone", lambda uid: "UTC")
    monkeypatch.setattr(process_module.users_db, "get_user_language_preference", lambda uid: "en")
    monkeypatch.setattr(process_module.users_db, "get_people_by_ids", lambda uid, person_ids: [])
    monkeypatch.setattr(process_module.folders_db, "get_folders", lambda uid: [])
    monkeypatch.setattr(process_module.folders_db, "initialize_system_folders", lambda uid: [])
    monkeypatch.setattr(process_module, "record_usage", lambda *args, **kwargs: None)
    monkeypatch.setattr(process_module, "track_usage", lambda *args, **kwargs: _NoopContext())
    monkeypatch.setattr(process_module, "should_discard_conversation", lambda *args, **kwargs: False)
    monkeypatch.setattr(process_module, "find_similar_action_items", lambda *args, **kwargs: [])
    monkeypatch.setattr(process_module, "find_similar_memories", lambda *args, **kwargs: [])
    monkeypatch.setattr(process_module, "upsert_vector2", lambda *args, **kwargs: None)
    monkeypatch.setattr(process_module, "update_vector_metadata", lambda *args, **kwargs: None)
    monkeypatch.setattr(process_module, "upsert_transcript_chunk_vectors", lambda *args, **kwargs: None)
    monkeypatch.setattr(process_module, "upsert_memory_vector", lambda *args, **kwargs: None)
    monkeypatch.setattr(process_module, "delete_memory_vector", lambda *args, **kwargs: None)
    monkeypatch.setattr(process_module, "upsert_action_item_vectors_batch", lambda *args, **kwargs: None)
    monkeypatch.setattr(process_module, "delete_action_item_vectors_batch", lambda *args, **kwargs: None)
    monkeypatch.setattr(process_module, "send_action_item_data_message", lambda *args, **kwargs: None)
    monkeypatch.setattr(process_module, "auto_sync_action_items_batch", _async_noop)
    monkeypatch.setattr(process_module, "conversation_created_webhook", _async_noop)
    monkeypatch.setattr(process_module, "get_overlapping_calendar_event", _async_none)
    monkeypatch.setattr(process_module, "write_conversation_link_to_calendar_event", _async_noop)
    monkeypatch.setattr(process_module, "precache_conversation_audio", lambda *args, **kwargs: None)
    monkeypatch.setattr(process_module, "_trigger_apps", lambda *args, **kwargs: None)
    monkeypatch.setattr(process_module, "_update_goal_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(process_module, "submit_with_context", run_selected_postprocess)
    monkeypatch.setattr(kg_module, "extract_knowledge_from_memory", record_kg_extract)
    # process_conversation imported extract_knowledge_from_memory directly,
    # so patch it on the process_module namespace too
    monkeypatch.setattr(process_module, "extract_knowledge_from_memory", record_kg_extract)
    monkeypatch.setattr(
        kg_module,
        "get_llm",
        lambda *args, **kwargs: (_ for _ in ()).throw(UnexpectedLLMCall("unexpected KG LLM call")),
    )
    monkeypatch.setattr(
        process_module,
        "get_transcript_structure",
        lambda *args, **kwargs: Structured(
            title="Hermetic Conversation Lifecycle",
            overview="A deterministic processing result created by the E2E harness.",
            emoji="🧪",
            category="work",
        ),
    )
    monkeypatch.setattr(
        process_module,
        "get_reprocess_transcript_structure",
        lambda *args, **kwargs: Structured(
            title="Hermetic Conversation Lifecycle Reprocessed",
            overview="A deterministic reprocess result created by the E2E harness.",
            emoji="🧪",
            category="work",
        ),
    )
    monkeypatch.setattr(
        process_module,
        "extract_action_items",
        lambda *args, **kwargs: [
            ActionItem(description="Ship deterministic conversation lifecycle coverage", completed=False)
        ],
    )
    monkeypatch.setattr(
        process_module,
        "new_memories_extractor",
        lambda *args, **kwargs: [
            Memory(
                content="David wants conversation lifecycle tests to fail hard.",
                category="system",
                visibility="public",
                tags=["e2e", "conversation"],
            )
        ],
    )
    return kg_calls


class _NoopContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


async def _async_noop(*args, **kwargs):
    return None


async def _async_none(*args, **kwargs):
    return None


def test_conversation_create_process_finalize_lifecycle(client, auth_headers, monkeypatch):
    kg_calls = _patch_process_conversation_boundaries(monkeypatch)

    import utils.conversations.process_conversation as process_module
    from models.conversation import CreateConversation

    started_at = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)
    create_conversation = CreateConversation(
        started_at=started_at,
        finished_at=started_at.replace(minute=5),
        source="omi",
        language="en",
        transcript_segments=[
            TranscriptSegment(
                id="seg-life-1",
                text="We should ship deterministic conversation lifecycle coverage.",
                speaker="SPEAKER_00",
                is_user=True,
                start=0.0,
                end=2.0,
            )
        ],
    )

    processed = process_module.process_conversation("123", "en", create_conversation)
    assert processed.status == "completed"
    assert processed.discarded is False
    assert processed.structured.title == "Hermetic Conversation Lifecycle"
    assert processed.structured.action_items[0].description == "Ship deterministic conversation lifecycle coverage"

    persisted = client.get(f"/v1/conversations/{processed.id}", headers=auth_headers)
    assert persisted.status_code == 200, persisted.text
    body = persisted.json()
    assert body["id"] == processed.id
    assert body["status"] == "completed"
    assert body["structured"]["title"] == "Hermetic Conversation Lifecycle"
    assert body["transcript_segments"][0]["text"] == "We should ship deterministic conversation lifecycle coverage."

    action_items = read_action_items("123")
    assert [item["description"] for item in action_items] == ["Ship deterministic conversation lifecycle coverage"]
    memories_response = client.get("/v3/memories", headers=auth_headers)
    assert memories_response.status_code == 200, memories_response.text
    memories = memories_response.json()
    assert [memory["content"] for memory in memories] == ["David wants conversation lifecycle tests to fail hard."]
    assert read_conversation("123", processed.id)["status"] == "completed"
    assert kg_calls == [
        (("123", "David wants conversation lifecycle tests to fail hard.", memories[0]["id"], "David"), {})
    ]


def test_reprocess_route_persists_deterministic_processing_result(client, auth_headers, monkeypatch):
    kg_calls = _patch_process_conversation_boundaries(monkeypatch)
    conv_id = "deterministic-processing-001"
    seed_conversation(
        "123",
        {
            "id": conv_id,
            "created_at": "2025-01-15T12:00:00Z",
            "started_at": "2025-01-15T12:00:00Z",
            "finished_at": "2025-01-15T12:05:00Z",
            "source": "omi",
            "language": "en",
            "structured": {
                "title": "Before Reprocess",
                "overview": "",
                "emoji": "🧠",
                "category": "other",
                "action_items": [],
                "events": [],
            },
            "transcript_segments": [
                {
                    "id": "seg-1",
                    "text": "Remember to ship the hermetic harness follow-up.",
                    "speaker": "SPEAKER_00",
                    "is_user": True,
                    "start": 0.0,
                    "end": 2.0,
                }
            ],
            "discarded": False,
            "status": "completed",
            "is_locked": False,
            "data_protection_level": "standard",
        },
    )

    response = client.post(f"/v1/conversations/{conv_id}/reprocess", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == conv_id
    assert body["structured"]["title"] == "Hermetic Conversation Lifecycle Reprocessed"
    assert body["structured"]["action_items"][0]["description"] == (
        "Ship deterministic conversation lifecycle coverage"
    )

    persisted = client.get(f"/v1/conversations/{conv_id}", headers=auth_headers)
    assert persisted.status_code == 200, persisted.text
    persisted_body = persisted.json()
    assert persisted_body["structured"]["title"] == "Hermetic Conversation Lifecycle Reprocessed"
    assert persisted_body["structured"]["action_items"][0]["description"] == (
        "Ship deterministic conversation lifecycle coverage"
    )
    memories_response = client.get("/v3/memories", headers=auth_headers)
    assert memories_response.status_code == 200, memories_response.text
    memories = memories_response.json()
    assert kg_calls == [
        (("123", "David wants conversation lifecycle tests to fail hard.", memories[0]["id"], "David"), {})
    ]


def test_seed_and_read_conversation(client, auth_headers, conversation_fixture):
    conv_data = dict(conversation_fixture["current_format_conversation"])
    seed_conversation("123", conv_data)

    response = client.get(f"/v1/conversations/{conv_data['id']}", headers=auth_headers)
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["id"] == conv_data["id"]
    assert body["source"] == conv_data["source"]


def test_in_progress_to_completed_fixture_is_readable(client, auth_headers, conversation_fixture):
    conv_data = dict(conversation_fixture["with_segments"])
    seed_conversation("123", conv_data)

    response = client.get(f"/v1/conversations/{conv_data['id']}", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] in ("in_progress", "completed", "processing")


def test_discarded_conversation_filtered(client, auth_headers):
    active_conv = {
        "id": "discard-test-active",
        "created_at": "2025-01-15T14:00:00Z",
        "started_at": "2025-01-15T14:00:00Z",
        "finished_at": "2025-01-15T14:02:00Z",
        "source": "omi",
        "structured": {
            "title": "Active",
            "overview": "",
            "emoji": "🧠",
            "category": "other",
            "action_items": [],
            "events": [],
        },
        "transcript_segments": [],
        "discarded": False,
        "status": "completed",
        "is_locked": False,
    }
    discarded_conv = dict(active_conv, id="discard-test-discarded", discarded=True)

    seed_conversation("123", active_conv)
    seed_conversation("123", discarded_conv)

    response = client.get("/v1/conversations?include_discarded=false", headers=auth_headers)
    assert response.status_code == 200, response.text
    ids = [conversation["id"] for conversation in response.json()]
    assert "discard-test-active" in ids
    assert "discard-test-discarded" not in ids
