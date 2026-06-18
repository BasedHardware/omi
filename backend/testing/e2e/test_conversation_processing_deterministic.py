"""Deterministic conversation-processing seam coverage."""

from fakes.firestore import seed_action_item, seed_conversation


def test_reprocess_route_persists_deterministic_processing_result(client, auth_headers, monkeypatch):
    """The reprocess route should persist and return deterministic processing output.

    This intentionally fakes the provider-heavy processing function at the route seam.
    It still exercises real auth, route validation, model serialization, Firestore read/write,
    and downstream action-item queryability.
    """
    conv_id = "deterministic-processing-001"
    conv_data = {
        "id": conv_id,
        "created_at": "2025-01-15T12:00:00Z",
        "started_at": "2025-01-15T12:00:00Z",
        "finished_at": "2025-01-15T12:05:00Z",
        "source": "omi",
        "language": "en",
        "structured": {
            "title": "",
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
    }
    seed_conversation("123", conv_data)

    def fake_process_conversation(uid, language_code, conversation, **kwargs):
        import database.conversations as conversations_db

        structured = conversation.structured.model_dump() if hasattr(conversation.structured, "model_dump") else {}
        structured.update(
            {
                "title": "Hermetic Harness Follow-up",
                "overview": "David asked to expand backend hermetic e2e coverage.",
                "emoji": "🧪",
                "category": "work",
                "action_items": [
                    {
                        "description": "Ship the hermetic harness follow-up",
                        "completed": False,
                        "conversation_id": conversation.id,
                    }
                ],
            }
        )
        update = {"structured": structured, "status": "completed"}
        conversations_db.update_conversation(uid, conversation.id, update)
        seed_action_item(
            uid,
            {
                "id": "ai-deterministic-processing",
                "description": "Ship the hermetic harness follow-up",
                "completed": False,
                "created_at": "2025-01-15T12:05:00Z",
                "updated_at": "2025-01-15T12:05:00Z",
                "conversation_id": conversation.id,
            },
        )
        refreshed = conversations_db.get_conversation(uid, conversation.id)
        from utils.conversations.factory import deserialize_conversation

        return deserialize_conversation(refreshed)

    import routers.conversations as conversations_router

    monkeypatch.setattr(conversations_router, "process_conversation", fake_process_conversation)

    resp = client.post(f"/v1/conversations/{conv_id}/reprocess", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == conv_id
    assert body["structured"]["title"] == "Hermetic Harness Follow-up"
    assert body["structured"]["overview"] == "David asked to expand backend hermetic e2e coverage."
    assert body["structured"]["action_items"][0]["description"] == "Ship the hermetic harness follow-up"

    persisted = client.get(f"/v1/conversations/{conv_id}", headers=auth_headers)
    assert persisted.status_code == 200, persisted.text
    assert persisted.json()["structured"]["title"] == "Hermetic Harness Follow-up"

    action_items = client.get("/v1/action-items", headers=auth_headers)
    assert action_items.status_code == 200, action_items.text
    descriptions = [item["description"] for item in action_items.json().get("action_items", [])]
    assert "Ship the hermetic harness follow-up" in descriptions
