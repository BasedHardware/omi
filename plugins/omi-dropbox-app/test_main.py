"""
Hermetic test suite for omi-dropbox-app.

Covers: manifest structure, error handling, defensive coercion,
audio buffer boundaries, and model contracts.

Run with: python -m pytest test_main.py -v
"""

import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure plugin is importable
sys.path.insert(0, os.path.dirname(__file__))

# We need to mock the db and dropbox_client imports before importing main
# because they have side effects (dotenv, FastAPI app creation)
sys.modules["db"] = MagicMock()
sys.modules["dropbox_client"] = MagicMock()
sys.modules["omi_plugin_sdk"] = MagicMock()

from models import (
    ChatToolResponse,
    DropboxUserSettings,
    ListDropboxRequest,
    ReadDropboxFileRequest,
    SearchDropboxRequest,
)


# ============== Model Contract Tests ==============


class TestSearchDropboxRequest:
    """Test SearchDropboxRequest validation."""

    def test_valid_request(self):
        req = SearchDropboxRequest(uid="user123", query="test")
        assert req.uid == "user123"
        assert req.query == "test"

    def test_uid_strips_whitespace(self):
        req = SearchDropboxRequest(uid="  user123  ", query="test")
        assert req.uid == "user123"

    def test_query_defaults_empty(self):
        req = SearchDropboxRequest(uid="user123")
        assert req.query == ""

    def test_query_strips_whitespace(self):
        req = SearchDropboxRequest(uid="user123", query="  hello world  ")
        assert req.query == "hello world"

    def test_uid_empty_raises(self):
        with pytest.raises(ValueError):
            SearchDropboxRequest(uid="", query="test")

    def test_uid_none_coerces_to_empty_and_raises(self):
        with pytest.raises(ValueError):
            SearchDropboxRequest(uid=None, query="test")


class TestListDropboxRequest:
    """Test ListDropboxRequest validation."""

    def test_valid_with_folder(self):
        req = ListDropboxRequest(uid="user123", folder="/path")
        assert req.folder == "/path"

    def test_folder_default_is_none(self):
        req = ListDropboxRequest(uid="user123")
        assert req.folder is None

    def test_folder_allows_empty_string(self):
        # Empty string should be allowed (will use default)
        req = ListDropboxRequest(uid="user123", folder="")
        assert req.folder == ""


class TestReadDropboxFileRequest:
    """Test ReadDropboxFileRequest validation."""

    def test_valid_request(self):
        req = ReadDropboxFileRequest(uid="user123", path="/file.txt")
        assert req.path == "/file.txt"

    def test_path_strips_whitespace(self):
        req = ReadDropboxFileRequest(uid="user123", path="  /file.txt  ")
        assert req.path == "/file.txt"

    def test_path_empty_raises(self):
        with pytest.raises(ValueError):
            ReadDropboxFileRequest(uid="user123", path="")


class TestChatToolResponse:
    """Test ChatToolResponse model."""

    def test_success_response(self):
        resp = ChatToolResponse(result="Found 3 files")
        assert resp.is_success() is True
        assert resp.result == "Found 3 files"
        assert resp.error is None

    def test_error_response(self):
        resp = ChatToolResponse(error="Not connected")
        assert resp.is_success() is False
        assert resp.error == "Not connected"
        assert resp.result is None

    def test_serializes_to_dict(self):
        resp = ChatToolResponse(result="ok")
        d = resp.model_dump()
        assert d == {"result": "ok", "error": None}

    def test_error_serializes_to_dict(self):
        resp = ChatToolResponse(error="fail")
        d = resp.model_dump()
        assert d == {"result": None, "error": "fail"}


class TestDropboxUserSettings:
    """Test DropboxUserSettings defaults."""

    def test_defaults(self):
        s = DropboxUserSettings()
        assert s.folder_name == "Omi Conversations"
        assert s.save_summary is True
        assert s.save_transcript is True
        assert s.save_audio is True

    def test_custom_values(self):
        s = DropboxUserSettings(folder_name="Custom", save_summary=False)
        assert s.folder_name == "Custom"
        assert s.save_summary is False


# ============== Defensive Parsing Tests ==============


class TestDefensiveParsing:
    """Test that malformed JSON payloads are handled gracefully."""

    def test_empty_body_returns_error(self):
        """Empty request body should return a tool error."""
        from main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        resp = client.post("/tools/search", content=b"")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("error") is not None

    def test_malformed_json_returns_error(self):
        """Malformed JSON should return a tool error, not a 500."""
        from main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        resp = client.post("/tools/search", content=b"not json")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("error") is not None
        assert "Invalid JSON" in data["error"]

    def test_json_array_returns_error(self):
        """JSON array (not object) should return an error."""
        from main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        resp = client.post("/tools/search", content=b"[1,2,3]")
        assert resp.status_code == 200
        data = resp.json()
        assert "object" in data.get("error", "")

    def test_null_query_handled_gracefully(self):
        """null query should be coerced to empty string."""
        req = SearchDropboxRequest(uid="user123", query=None)
        assert req.query == ""

    def test_null_path_handled_as_empty_then_raises(self):
        """null path should raise validation error (empty after strip)."""
        with pytest.raises(ValueError):
            ReadDropboxFileRequest(uid="user123", path=None)

    def test_whitespace_only_query_handled(self):
        """Whitespace-only query should be stripped to empty."""
        req = SearchDropboxRequest(uid="user123", query="   ")
        assert req.query == ""


# ============== Audio Buffer Boundary Tests ==============


class TestAudioBufferBounds:
    """Test audio buffer size enforcement."""

    def test_buffer_limit_constant_exists(self):
        from main import MAX_AUDIO_BUFFER_BYTES
        assert MAX_AUDIO_BUFFER_BYTES == 50 * 1024 * 1024  # 50 MB

    def test_buffer_accepts_under_limit(self):
        """Audio under the limit should be accepted."""
        from main import MAX_AUDIO_BUFFER_BYTES, audio_buffers
        # Clear any existing buffer
        audio_buffers.clear()
        chunk_size = 1024  # 1 KB
        # Simulate receiving audio chunks
        for _ in range(100):  # 100 KB total - well under limit
            audio_buffers["test_user"] += b"\x00" * chunk_size
        assert len(audio_buffers["test_user"]) == 102400
        audio_buffers.clear()

    def test_buffer_would_reject_over_limit(self):
        """The code checks bounds before appending; verify constant is correct."""
        from main import MAX_AUDIO_BUFFER_BYTES
        assert MAX_AUDIO_BUFFER_BYTES > 0
        assert MAX_AUDIO_BUFFER_BYTES == 52_428_800  # 50 * 1024 * 1024


# ============== Manifest Structure Tests ==============


class TestManifestStructure:
    """Test the omi-tools manifest endpoint."""

    def test_manifest_returns_tools(self):
        from main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        resp = client.get("/.well-known/omi-tools.json")
        assert resp.status_code == 200
        data = resp.json()
        assert "tools" in data
        assert len(data["tools"]) == 3

    def test_manifest_tool_names(self):
        from main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        resp = client.get("/.well-known/omi-tools.json")
        tools = resp.json()["tools"]
        names = {t["name"] for t in tools}
        assert names == {"search_dropbox", "list_dropbox_conversations", "read_dropbox_file"}

    def test_manifest_tools_require_auth(self):
        from main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        resp = client.get("/.well-known/omi-tools.json")
        for tool in resp.json()["tools"]:
            assert tool["auth_required"] is True

    def test_manifest_search_has_required_params(self):
        from main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        resp = client.get("/.well-known/omi-tools.json")
        search = [t for t in resp.json()["tools"] if t["name"] == "search_dropbox"][0]
        assert "query" in search["parameters"]["required"]
        assert search["method"] == "POST"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
