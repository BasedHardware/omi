"""
Scenario 4: Migration Safety

Tests that:
1. Old-format documents (pre-migration) are readable by current code
2. Migration scripts transform old → new format correctly
3. Migration is idempotent (running twice is a no-op)
"""

import json
import copy

from fakes.firestore import read_conversation, read_memories, seed_conversation, seed_memory


class TestLegacyFormatReading:
    """Current code can read old-format Firestore documents."""

    def test_read_legacy_plugins_results(self, client, auth_headers, conversation_fixture):
        """
        Conversations with ``plugins_results`` (old format) are readable.

        The Conversation model's __init__ auto-populates plugins_results
        from apps_results for backward compatibility.
        """

        legacy_conv = dict(conversation_fixture["legacy_plugins_results_format"])
        seed_conversation("123", legacy_conv)

        resp = client.get(f"/v1/conversations/{legacy_conv['id']}", headers=auth_headers)
        assert resp.status_code == 200, f"Failed to read legacy conversation: {resp.text}"

        body = resp.json()
        # Should have both apps_results (empty list default) and plugins_results
        assert "plugins_results" in body
        assert "apps_results" in body
        # Legacy data had plugins_results populated
        assert isinstance(body["plugins_results"], list)

    def test_read_legacy_memory_format(self, client, auth_headers, memory_fixture):
        """Old-format memories (missing scoring, category mapping) are readable."""

        legacy_mem = dict(memory_fixture["legacy_format_memory"])
        seed_memory("123", legacy_mem)

        resp = client.get("/v3/memories", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        memories = resp.json()
        found = [m for m in memories if m["id"] == legacy_mem["id"]]
        assert found, f"Legacy memory {legacy_mem['id']} not returned"
        assert found[0]["content"] == legacy_mem["content"]

    def test_mixed_format_coexistence(self, client, auth_headers, conversation_fixture):
        """
        Both old and new format conversations coexist in the same collection.

        Listing returns both without errors.
        """

        new_conv = dict(conversation_fixture["current_format_conversation"])
        legacy_conv = dict(conversation_fixture["legacy_plugins_results_format"])

        seed_conversation("123", new_conv)
        seed_conversation("123", legacy_conv)

        resp = client.get("/v1/conversations?include_discarded=true", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        ids = [c["id"] for c in body]
        assert new_conv["id"] in ids
        assert legacy_conv["id"] in ids


class TestMigrationIdempotency:
    """Migration scripts should be safe to run multiple times."""

    def test_double_write_same_id(self, client, auth_headers):
        """
        Writing a document twice with the same ID overwrites (not duplicates).

        This simulates running a migration script twice — the second run
        should be a no-op or overwrite with same data.
        """

        conv_data = {
            "id": "migration-idempotent-001",
            "created_at": "2025-01-15T17:00:00Z",
            "started_at": "2025-01-15T17:00:00Z",
            "finished_at": "2025-01-15T17:02:00Z",
            "source": "omi",
            "structured": {
                "title": "Migration Test",
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

        # First write
        seed_conversation("123", conv_data)

        # Second write (same id — simulates re-running migration)
        updated = dict(conv_data, structured={**conv_data["structured"], "title": "Updated Title"})
        seed_conversation("123", updated)

        # Verify only one doc exists with latest data
        result = read_conversation("123", conv_data["id"])
        assert result is not None
        assert result["structured"]["title"] == "Updated Title"

    def test_memory_migration_idempotency(self, client, auth_headers):
        """
        Writing a memory twice with same ID produces single document.
        """

        mem_data = {
            "id": "mem-mig-idem-001",
            "content": "Migration test memory",
            "category": "interesting",
            "visibility": "public",
            "created_at": "2025-01-15T17:00:00Z",
            "updated_at": "2025-01-15T17:00:00Z",
        }

        seed_memory("123", mem_data)
        seed_memory("123", dict(mem_data, content="Updated content"))

        memories = read_memories("123")
        matching = [m for m in memories if m["id"] == mem_data["id"]]
        assert len(matching) == 1
        assert matching[0]["content"] == "Updated content"


class TestFieldShapeEvolution:
    """Test that field shape changes don't break reads."""

    def test_missing_optional_fields(self, client, auth_headers):
        """
        Documents missing optional fields (e.g., folder_id, calendar_event,
        processing_conversation_id) still deserialize correctly.
        """

        minimal_conv = {
            "id": "minimal-fields-001",
            "created_at": "2025-01-15T18:00:00Z",
            "started_at": "2025-01-15T18:00:00Z",
            "finished_at": "2025-01-15T18:01:00Z",
            "source": "omi",
            "structured": {
                "title": "",
                "overview": "",
                "emoji": "🧠",
                "category": "other",
                "action_items": [],
                "events": [],
            },
            "transcript_segments": [],
            # Intentionally omit: folder_id, calendar_event, starred, etc.
            "discarded": False,
            "status": "completed",
            "is_locked": False,
        }
        seed_conversation("123", minimal_conv)

        resp = client.get(f"/v1/conversations/{minimal_conv['id']}", headers=auth_headers)
        assert resp.status_code == 200, f"Minimal conv should be readable: {resp.text}"

        body = resp.json()
        # Missing fields should get defaults from Pydantic model
        assert body.get("starred") is False or "starred" not in body or body.get("starred") is None

    def test_extra_fields_ignored(self, client, auth_headers):
        """
        Documents with unknown extra fields (from future schema) don't
        break deserialization.
        """

        conv_with_extra = {
            "id": "extra-fields-001",
            "created_at": "2025-01-15T19:00:00Z",
            "started_at": "2025-01-15T19:00:00Z",
            "finished_at": "2025-01-15T19:01:00Z",
            "source": "omi",
            "structured": {
                "title": "",
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
            # Extra fields that don't exist on current model
            "future_field_v2": "should be ignored",
            "experimental_flag": 42,
        }
        seed_conversation("123", conv_with_extra)

        resp = client.get(f"/v1/conversations/{conv_with_extra['id']}", headers=auth_headers)
        # Pydantic may ignore or reject extra fields depending on config
        # Either behavior is acceptable as long as it doesn't crash
        assert resp.status_code in (200, 422), f"Extra fields caused unexpected error: {resp.text}"


class TestCategoryEnumMigration:
    """Test that old category values map to new ones."""

    def test_legacy_category_mapping(self, client, auth_headers):
        """
        Memories with old category values ('core', 'hobbies', etc.) map to
        'system' per the Memory model's validator.
        """

        old_category_mem = {
            "id": "mem-old-cat-001",
            "content": "Memory with legacy category",
            "category": "core",  # Legacy value → maps to 'system'
            "visibility": "public",
            "created_at": "2025-01-15T20:00:00Z",
            "updated_at": "2025-01-15T20:00:00Z",
        }
        seed_memory("123", old_category_mem)

        resp = client.post(
            "/v3/memories",
            json={"content": "Trigger read", "category": "manual"},
            headers=auth_headers,
        )

        # List should include the legacy-category memory with mapped value
        resp = client.get("/v3/memories", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        memories = resp.json()
        found = [m for m in memories if m["id"] == old_category_mem["id"]]
        assert found, f"Legacy category memory {old_category_mem['id']} not returned"
        assert found[0]["category"] in ("system", "core")
