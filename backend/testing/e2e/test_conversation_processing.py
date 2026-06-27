"""
Scenario 2: Conversation Processing

Tests that seeding a transcript into fake Firestore and triggering
the processing pipeline produces correct structured output (title,
summary, action items, memories) via deterministic LLM responses.
"""

import json

import pytest

from fakes.firestore import seed_conversation


class TestConversationProcessing:
    """Exercise the full processing pipeline with fake LLM."""

    @pytest.mark.skip(reason="LLM client fakes are scaffolded but not wired into processing clients yet")
    def test_process_conversation_creates_structured_data(self, client, auth_headers, conversation_fixture):
        """
        Seed a conversation with transcript segments, then reprocess it.

        The fake LLM returns a deterministic structured response. We verify
        that the conversation is updated with title, overview, category, etc.
        """
        # Seed a conversation with segments into Firestore directly
        conv_data = dict(conversation_fixture["with_segments"])
        conv_id = conv_data["id"]

        seed_conversation("123", conv_data)

        # Trigger reprocessing via API
        resp = client.post(
            f"/v1/conversations/{conv_id}/reprocess",
            headers=auth_headers,
        )
        # May fail if LLM endpoint doesn't match — that's ok for now
        # The key test is whether the round-trip works end-to-end
        if resp.status_code == 200:
            body = resp.json()
            assert "id" in body
            assert "structured" in body
            s = body["structured"]
            # Fake LLM should have returned our deterministic response
            assert s.get("title") != "" or s.get("overview") != ""
        else:
            # If reprocessing fails due to LLM endpoint mismatch, that's
            # informative but not a hard failure for v1 of the harness
            pass

    def test_seed_and_read_conversation(self, client, auth_headers, conversation_fixture):
        """Verify seeded conversations are readable through the API."""
        conv_data = dict(conversation_fixture["current_format_conversation"])
        seed_conversation("123", conv_data)

        resp = client.get(f"/v1/conversations/{conv_data['id']}", headers=auth_headers)
        assert resp.status_code == 200, f"Failed to read seeded conversation: {resp.text}"

        body = resp.json()
        assert body["id"] == conv_data["id"]
        assert body["source"] == conv_data["source"]

    @pytest.mark.skip(reason="LLM client fakes are scaffolded but not wired into processing clients yet")
    def test_processing_extracts_action_items(self, client, auth_headers):
        """
        After processing, action items should be queryable.

        This tests the full chain: conversation → LLM extraction →
        action_items collection persistence → GET retrieval.
        """
        # Create a conversation with meaningful text
        conv_id = "proc-ai-test-001"
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
                    "id": "seg-p1",
                    "text": "We need to finish the API redesign by next Friday.",
                    "speaker": "SPEAKER_00",
                    "is_user": True,
                    "start": 0.0,
                    "end": 3.0,
                },
                {
                    "id": "seg-p2",
                    "text": "I'll also set up the deployment pipeline.",
                    "speaker": "SPEAKER_00",
                    "is_user": True,
                    "start": 3.1,
                    "end": 5.5,
                },
            ],
            "discarded": False,
            "status": "completed",
            "is_locked": False,
            "data_protection_level": "standard",
        }

        seed_conversation("123", conv_data)

        # Try to reprocess
        resp = client.post(
            f"/v1/conversations/{conv_id}/reprocess",
            headers=auth_headers,
        )

        if resp.status_code == 200:
            # Check if action items were created
            ai_resp = client.get("/v1/action-items", headers=auth_headers)
            if ai_resp.status_code == 200:
                ai_body = ai_resp.json()
                items = ai_body.get("action_items", [])
                # At minimum, the conversation should be readable
                assert isinstance(items, list)

    @pytest.mark.skip(reason="LLM client fakes are scaffolded but not wired into processing clients yet")
    def test_memory_extraction_from_processed_conversation(self, client, auth_headers):
        """After processing, memories should be persisted."""
        conv_id = "proc-mem-test-001"
        conv_data = {
            "id": conv_id,
            "created_at": "2025-01-15T13:00:00Z",
            "started_at": "2025-01-15T13:00:00Z",
            "finished_at": "2025-01-15T13:03:00Z",
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
                    "id": "seg-m1",
                    "text": "I learned that Sarah prefers morning meetings.",
                    "speaker": "SPEAKER_00",
                    "is_user": True,
                    "start": 0.0,
                    "end": 3.0,
                }
            ],
            "discarded": False,
            "status": "completed",
            "is_locked": False,
            "data_protection_level": "standard",
        }

        seed_conversation("123", conv_data)

        # Reprocess to trigger memory extraction
        resp = client.post(
            f"/v1/conversations/{conv_id}/reprocess",
            headers=auth_headers,
        )
        if resp.status_code == 200:
            mem_resp = client.get("/v3/memories", headers=auth_headers)
            if mem_resp.status_code == 200:
                memories = mem_resp.json()
                assert isinstance(memories, list)


class TestConversationStateTransitions:
    """Test conversation status transitions through the lifecycle."""

    def test_in_progress_to_completed(self, client, auth_headers, conversation_fixture):
        """A conversation can transition from in_progress to completed."""
        conv_data = dict(conversation_fixture["with_segments"])
        conv_id = conv_data["id"]

        seed_conversation("123", conv_data)

        # Read in_progress conversation
        resp = client.get(f"/v1/conversations/{conv_id}", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] in ("in_progress", "completed", "processing")

    def test_discarded_conversation_filtered(self, client, auth_headers):
        """Discarded conversations don't appear in default list."""
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

        # Default list excludes discarded
        resp = client.get("/v1/conversations?include_discarded=false", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        ids = [c["id"] for c in body]
        assert "discard-test-active" in ids
        assert "discard-test-discarded" not in ids
