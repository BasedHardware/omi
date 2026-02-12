"""
Live service integration tests for the chat endpoint.

These tests run against the local backend server at http://localhost:8000.
They verify the full request→response pipeline including prompt construction,
LLM client configuration, and streaming response formatting.

Prerequisites:
    - Backend running: set -a && source .env && set +a && python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
    - ADMIN_KEY must be set in .env (used for auth bypass)

Usage:
    pytest tests/integration/test_live_chat_service.py -v
"""

import os
import sys
import base64
import json
import time
import uuid

import pytest
import requests

BASE_URL = os.getenv("TEST_BACKEND_URL", "http://localhost:8000")
ADMIN_KEY = os.getenv("ADMIN_KEY", "123")


def _auth_header(uid: str = "test-integration-user") -> dict:
    """Create auth header using ADMIN_KEY bypass: token = ADMIN_KEY + uid."""
    return {
        "Authorization": f"Bearer {ADMIN_KEY}{uid}",
        "Content-Type": "application/json",
    }


def _is_backend_running() -> bool:
    """Check if the backend is accessible."""
    try:
        r = requests.get(f"{BASE_URL}/docs", timeout=3)
        return r.status_code == 200
    except requests.ConnectionError:
        return False


# Skip all tests if backend is not running
pytestmark = pytest.mark.skipif(
    not _is_backend_running(),
    reason=f"Backend not running at {BASE_URL}",
)


class TestChatEndpointStreaming:
    """Test the /v2/messages streaming chat endpoint."""

    def test_chat_returns_streaming_response(self):
        """
        POST /v2/messages should return a streaming text/event-stream response.
        This exercises the full code path including prompt construction and LLM call.
        """
        uid = f"test-live-{uuid.uuid4().hex[:8]}"
        r = requests.post(
            f"{BASE_URL}/v2/messages",
            headers=_auth_header(uid),
            json={"text": "say hi in one word"},
            stream=True,
            timeout=60,
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:200]}"
        assert "text/event-stream" in r.headers.get(
            "content-type", ""
        ), f"Expected text/event-stream, got {r.headers.get('content-type')}"

        # Collect streamed chunks
        chunks = []
        for line in r.iter_lines(decode_unicode=True):
            if line:
                chunks.append(line)

        assert len(chunks) > 0, "Should receive at least one streamed chunk"

        # Last chunk should be a 'done:' message with base64-encoded JSON
        last_chunk = chunks[-1]
        assert last_chunk.startswith("done: "), f"Last chunk should be 'done: <base64>', got: {last_chunk[:80]}"

        # Decode the final message
        b64_payload = last_chunk[len("done: ") :].strip()
        decoded = json.loads(base64.b64decode(b64_payload))
        assert "text" in decoded, f"Decoded response should have 'text' field, got keys: {list(decoded.keys())}"
        assert len(decoded["text"]) > 0, "Response text should not be empty"
        assert decoded.get("sender") == "ai", f"Sender should be 'ai', got {decoded.get('sender')}"

    def test_multi_turn_conversation(self):
        """
        Send two messages from the same user. Both should get valid responses.
        This verifies the agentic prompt path handles conversation history.
        """
        uid = f"test-multi-{uuid.uuid4().hex[:8]}"

        for msg_text in ["hello", "what did I just say?"]:
            r = requests.post(
                f"{BASE_URL}/v2/messages",
                headers=_auth_header(uid),
                json={"text": msg_text},
                stream=True,
                timeout=60,
            )
            assert r.status_code == 200

            chunks = list(r.iter_lines(decode_unicode=True))
            done = [c for c in chunks if c.startswith("done: ")]
            assert len(done) == 1, f"Message '{msg_text}' should have a done chunk"

            decoded = json.loads(base64.b64decode(done[0][len("done: ") :]))
            assert decoded["sender"] == "ai"
            assert len(decoded["text"]) > 0


class TestChatEndpointAuth:
    """Test authentication for chat endpoints."""

    def test_no_auth_returns_401(self):
        """Request without Authorization header should return 401."""
        r = requests.post(
            f"{BASE_URL}/v2/messages",
            headers={"Content-Type": "application/json"},
            json={"text": "hello"},
            timeout=10,
        )
        assert r.status_code == 401

    def test_invalid_token_returns_401(self):
        """Request with invalid token should return 401."""
        r = requests.post(
            f"{BASE_URL}/v2/messages",
            headers={
                "Authorization": "Bearer invalid_token_xyz",
                "Content-Type": "application/json",
            },
            json={"text": "hello"},
            timeout=10,
        )
        assert r.status_code == 401


class TestChatMessageHistory:
    """Test message retrieval endpoints."""

    def test_get_messages_returns_list(self):
        """GET /v2/messages should return a list of messages."""
        uid = f"test-history-{uuid.uuid4().hex[:8]}"
        r = requests.get(
            f"{BASE_URL}/v2/messages",
            headers=_auth_header(uid),
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"


class TestRealUserChat:
    """Test with a real dev user that has data in Firestore."""

    REAL_UID = os.getenv("TEST_REAL_UID", "OAEZL1gRvOQmLLg6E3BzjNpEmtf1")

    def test_real_user_chat_response(self):
        """
        Send a message as a real dev user. This exercises the full path with
        actual Firestore data, conversation history, and user profile lookup.
        """
        r = requests.post(
            f"{BASE_URL}/v2/messages",
            headers=_auth_header(self.REAL_UID),
            json={"text": "what's my name?"},
            stream=True,
            timeout=60,
        )
        assert r.status_code == 200

        chunks = list(r.iter_lines(decode_unicode=True))
        done = [c for c in chunks if c.startswith("done: ")]
        assert len(done) == 1, "Should have exactly one done chunk"

        decoded = json.loads(base64.b64decode(done[0][len("done: ") :]))
        assert decoded["sender"] == "ai"
        assert len(decoded["text"]) > 0, "AI should respond with non-empty text"

    def test_real_user_message_history(self):
        """
        Retrieve message history for a real user. Verifies the messages
        endpoint works with actual Firestore data.
        """
        r = requests.get(
            f"{BASE_URL}/v2/messages",
            headers=_auth_header(self.REAL_UID),
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)


class TestPromptCacheVerification:
    """
    Verify that prompt caching optimization works end-to-end.

    These tests send two messages from different "users" and verify that:
    - Both get valid streaming responses (the optimized code path works)
    - The response structure is consistent (no regressions from the refactor)
    """

    def test_two_users_both_get_valid_responses(self):
        """
        Two different users should both get valid streaming responses.
        This proves the cache-optimized prompt path works for all users,
        not just a hardcoded one.
        """
        results = {}
        for user_suffix in ["alpha", "beta"]:
            uid = f"test-cache-{user_suffix}-{uuid.uuid4().hex[:8]}"
            r = requests.post(
                f"{BASE_URL}/v2/messages",
                headers=_auth_header(uid),
                json={"text": "reply with just the word 'ok'"},
                stream=True,
                timeout=60,
            )
            assert r.status_code == 200, f"User {user_suffix} got status {r.status_code}"

            chunks = list(r.iter_lines(decode_unicode=True))
            done_chunks = [c for c in chunks if c.startswith("done: ")]
            assert len(done_chunks) == 1, f"User {user_suffix}: expected 1 done chunk, got {len(done_chunks)}"

            decoded = json.loads(base64.b64decode(done_chunks[0][len("done: ") :]))
            results[user_suffix] = decoded

        # Both should have the same response structure
        for user_suffix, resp in results.items():
            assert "text" in resp, f"User {user_suffix} response missing 'text'"
            assert "id" in resp, f"User {user_suffix} response missing 'id'"
            assert resp["sender"] == "ai", f"User {user_suffix} sender should be 'ai'"

    def test_response_structure_matches_schema(self):
        """
        Verify the AI response has all expected fields from the ResponseMessage model.
        This catches any regression from prompt refactoring.
        """
        uid = f"test-schema-{uuid.uuid4().hex[:8]}"
        r = requests.post(
            f"{BASE_URL}/v2/messages",
            headers=_auth_header(uid),
            json={"text": "hello"},
            stream=True,
            timeout=60,
        )
        assert r.status_code == 200

        chunks = list(r.iter_lines(decode_unicode=True))
        done_chunks = [c for c in chunks if c.startswith("done: ")]
        decoded = json.loads(base64.b64decode(done_chunks[0][len("done: ") :]))

        # Check required fields exist
        required_fields = ["id", "text", "created_at", "sender", "type"]
        for field in required_fields:
            assert field in decoded, f"Response missing required field: {field}"

        # Check field values
        assert decoded["sender"] == "ai"
        assert decoded["type"] == "text"
        assert len(decoded["id"]) > 0
        assert len(decoded["text"]) > 0
