"""
Mobile-facing lifecycle and compatibility coverage.

These route-level tests are based on high-value Flutter/desktop callers:
- app/lib/backend/http/api/conversations.dart expects conversation lists as arrays
  of ServerConversation objects with parseable timestamps, structured summary
  fields, transcript segment arrays, and defaulted sync/visibility fields.
- app/lib/backend/http/api/memories.dart expects /v3/memories to return a list
  of Memory objects with stable id/content/category/timestamps/visibility fields.
- app/lib/backend/http/api/action_items.dart expects /v1/action-items to return
  {action_items, has_more}, item metadata defaults, batch updates, and sync-ish
  pending-export/synced response buckets.
- app/lib/backend/http/api/users.dart expects language and transcription prefs to
  round-trip in the same bootstrapping flow as the data reads above.
"""

from datetime import datetime, timezone

from fakes.firestore import seed_conversation


def _assert_iso_datetime(value):
    assert isinstance(value, str)
    # Dart DateTime.parse accepts the API's ISO-8601 strings; this verifies the
    # backend does not accidentally return native fake-store datetime reprs.
    datetime.fromisoformat(value.replace("Z", "+00:00"))


def _assert_mobile_conversation_shape(body, expected_id):
    assert body["id"] == expected_id
    _assert_iso_datetime(body["created_at"])
    assert body["started_at"] is None or isinstance(body["started_at"], str)
    assert body["finished_at"] is None or isinstance(body["finished_at"], str)
    assert isinstance(body["structured"], dict)
    assert set(["title", "overview", "emoji", "category", "action_items", "events"]).issubset(body["structured"])
    assert isinstance(body["structured"]["action_items"], list)
    assert isinstance(body["structured"]["events"], list)
    assert isinstance(body["transcript_segments"], list)
    assert isinstance(body.get("apps_results", []), list)
    assert isinstance(body.get("suggested_summarization_apps", []), list)
    assert isinstance(body.get("photos", []), list)
    assert isinstance(body.get("audio_files", []), list)
    assert body["source"] in {"omi", "sdcard", "screenpipe", "openglass"}
    assert body["status"] in {"completed", "processing", "failed"}
    assert isinstance(body.get("discarded", False), bool)
    assert isinstance(body.get("deleted", False), bool)
    assert isinstance(body.get("is_locked", False), bool)
    assert isinstance(body.get("starred", False), bool)
    assert body.get("visibility") in {"private", "public", "shared", None}


def _assert_mobile_memory_shape(body, expected_content):
    assert body["id"]
    assert body["uid"] == "123"
    assert body["content"] == expected_content
    assert body["category"] in {"system", "interesting", "manual", "workflow"}
    _assert_iso_datetime(body["created_at"])
    _assert_iso_datetime(body["updated_at"])
    assert isinstance(body.get("reviewed", False), bool)
    assert isinstance(body.get("manually_added", False), bool)
    assert isinstance(body.get("edited", False), bool)
    assert isinstance(body.get("deleted", False), bool)
    assert body.get("visibility") in {"public", "private"}
    assert isinstance(body.get("is_locked", False), bool)


def _assert_mobile_action_item_shape(body, expected_description):
    assert body["id"]
    assert body["description"] == expected_description
    assert isinstance(body["completed"], bool)
    assert body["created_at"] is None or isinstance(body["created_at"], str)
    assert body["updated_at"] is None or isinstance(body["updated_at"], str)
    assert body["due_at"] is None or isinstance(body["due_at"], str)
    assert body["completed_at"] is None or isinstance(body["completed_at"], str)
    assert body["conversation_id"] is None or isinstance(body["conversation_id"], str)
    assert isinstance(body.get("is_locked", False), bool)
    assert isinstance(body.get("exported", False), bool)
    assert body["export_date"] is None or isinstance(body["export_date"], str)
    assert body["export_platform"] is None or isinstance(body["export_platform"], str)
    assert body["apple_reminder_id"] is None or isinstance(body["apple_reminder_id"], str)
    assert isinstance(body.get("sort_order", 0), int)
    assert isinstance(body.get("indent_level", 0), int)


def test_mobile_bootstrap_lifecycle_shapes(client, auth_headers, sample_conversation_data):
    """Canonical app boot: prefs + conversations + memories + action items keep mobile parse contracts."""

    set_language = client.patch("/v1/users/language", json={"language": "en"}, headers=auth_headers)
    assert set_language.status_code == 200, set_language.text

    prefs_update = client.patch(
        "/v1/users/transcription-preferences",
        json={"single_language_mode": True, "vocabulary": ["Omi", "Hermes"]},
        headers=auth_headers,
    )
    assert prefs_update.status_code == 200, prefs_update.text

    memory_create = client.post(
        "/v3/memories",
        json={"content": "Mobile-visible memory", "category": "manual", "visibility": "public"},
        headers=auth_headers,
    )
    assert memory_create.status_code == 200, memory_create.text
    _assert_mobile_memory_shape(memory_create.json(), "Mobile-visible memory")

    action_create = client.post(
        "/v1/action-items",
        json={"description": "Mobile-visible task", "completed": False, "conversation_id": "mobile-lifecycle-conv"},
        headers=auth_headers,
    )
    assert action_create.status_code == 200, action_create.text
    _assert_mobile_action_item_shape(action_create.json(), "Mobile-visible task")

    seed_conversation("123", dict(sample_conversation_data, id="mobile-lifecycle-conv"))

    conversations = client.get(
        "/v1/conversations?include_discarded=true&limit=50&offset=0&statuses=completed,processing",
        headers=auth_headers,
    )
    assert conversations.status_code == 200, conversations.text
    conversation_items = conversations.json()
    assert isinstance(conversation_items, list)
    conversation_ids = [item["id"] for item in conversation_items]
    assert "mobile-lifecycle-conv" in conversation_ids, conversation_items
    listed_conversation = next(item for item in conversation_items if item["id"] == "mobile-lifecycle-conv")
    _assert_mobile_conversation_shape(listed_conversation, "mobile-lifecycle-conv")

    memories = client.get("/v3/memories?limit=100&offset=0", headers=auth_headers)
    assert memories.status_code == 200, memories.text
    memory_items = memories.json()
    assert isinstance(memory_items, list)
    listed_memory = next(item for item in memory_items if item["id"] == memory_create.json()["id"])
    _assert_mobile_memory_shape(listed_memory, "Mobile-visible memory")

    action_items = client.get("/v1/action-items?limit=50&offset=0", headers=auth_headers)
    assert action_items.status_code == 200, action_items.text
    action_body = action_items.json()
    assert set(action_body) == {"action_items", "has_more"}
    assert isinstance(action_body["action_items"], list)
    assert isinstance(action_body["has_more"], bool)
    listed_action = next(item for item in action_body["action_items"] if item["id"] == action_create.json()["id"])
    _assert_mobile_action_item_shape(listed_action, "Mobile-visible task")

    prefs = client.get("/v1/users/transcription-preferences", headers=auth_headers)
    assert prefs.status_code == 200, prefs.text
    prefs_body = prefs.json()
    assert prefs_body["language"] == "en"
    assert prefs_body["single_language_mode"] is True
    assert prefs_body["vocabulary"] == ["Omi", "Hermes"]
    assert prefs_body["uses_custom_stt"] is False
    assert prefs_body["custom_stt_since"] is None


def test_mobile_mutation_and_syncish_compatibility(client, auth_headers, sample_conversation_data):
    """Common mobile mutations keep response shapes stable, including sync-ish action-item buckets."""

    seed_conversation("123", dict(sample_conversation_data, id="mobile-mutate-conv"))

    star = client.patch("/v1/conversations/mobile-mutate-conv/starred?starred=true", headers=auth_headers)
    assert star.status_code == 200, star.text

    visibility = client.patch("/v1/conversations/mobile-mutate-conv/visibility?value=public", headers=auth_headers)
    assert visibility.status_code == 200, visibility.text

    conversation = client.get("/v1/conversations/mobile-mutate-conv", headers=auth_headers)
    assert conversation.status_code == 200, conversation.text
    conversation_body = conversation.json()
    _assert_mobile_conversation_shape(conversation_body, "mobile-mutate-conv")
    assert conversation_body["starred"] is True
    assert conversation_body["visibility"] == "public"

    memory = client.post(
        "/v3/memories",
        json={"content": "Private mobile memory", "category": "manual", "visibility": "private"},
        headers=auth_headers,
    )
    assert memory.status_code == 200, memory.text
    memory_id = memory.json()["id"]

    memory_visibility = client.patch(f"/v3/memories/{memory_id}/visibility?value=public", headers=auth_headers)
    assert memory_visibility.status_code == 200, memory_visibility.text
    memories = client.get("/v3/memories", headers=auth_headers)
    changed_memory = next(item for item in memories.json() if item["id"] == memory_id)
    _assert_mobile_memory_shape(changed_memory, "Private mobile memory")
    assert changed_memory["visibility"] == "public"

    action = client.post(
        "/v1/action-items",
        json={"description": "Sync me", "completed": False, "conversation_id": "mobile-mutate-conv"},
        headers=auth_headers,
    )
    assert action.status_code == 200, action.text
    action_id = action.json()["id"]

    action_update = client.patch(
        f"/v1/action-items/{action_id}",
        json={
            "completed": True,
            "exported": True,
            "export_platform": "apple_reminders",
            "sort_order": 7,
            "indent_level": 1,
        },
        headers=auth_headers,
    )
    assert action_update.status_code == 200, action_update.text
    _assert_mobile_action_item_shape(action_update.json(), "Sync me")
    assert action_update.json()["completed"] is True
    assert action_update.json()["exported"] is True
    assert action_update.json()["export_platform"] == "apple_reminders"
    assert action_update.json()["sort_order"] == 7
    assert action_update.json()["indent_level"] == 1

    batch = client.patch(
        "/v1/action-items/batch",
        json={"items": [{"id": action_id, "sort_order": 3, "indent_level": 0}]},
        headers=auth_headers,
    )
    assert batch.status_code == 200, batch.text
    assert batch.json() == {"status": "ok", "updated_count": 1}

    pending_sync = client.get("/v1/action-items/pending-sync?platform=apple_reminders", headers=auth_headers)
    assert pending_sync.status_code == 200, pending_sync.text
    pending_body = pending_sync.json()
    assert set(pending_body) == {"pending_export", "synced_items"}
    assert isinstance(pending_body["pending_export"], list)
    assert isinstance(pending_body["synced_items"], list)
    assert any(item["id"] == action_id for item in pending_body["synced_items"])

    delete_action = client.delete(f"/v1/action-items/{action_id}", headers=auth_headers)
    assert delete_action.status_code == 204, delete_action.text

    delete_memory = client.delete(f"/v3/memories/{memory_id}", headers=auth_headers)
    assert delete_memory.status_code == 200, delete_memory.text
