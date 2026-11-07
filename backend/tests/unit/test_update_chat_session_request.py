"""Tests for CreateChatSessionRequest and UpdateChatSessionRequest validation and normalization.

Validates that:
- Empty or whitespace-only titles are rejected with ValidationError (which FastAPI translates to 422) on both create and update paths.
- None title with app_id (create) or starred=True (update) succeeds without modifying title.
- Valid titles with leading/trailing whitespace are stripped and normalized on both paths.
- Default empty payloads succeed.
"""

import pytest
from pydantic import ValidationError

from routers.chat_sessions import CreateChatSessionRequest, UpdateChatSessionRequest


def test_create_chat_session_request_rejects_empty_title():
    with pytest.raises(ValidationError) as exc_info:
        CreateChatSessionRequest(title="")
    errors = exc_info.value.errors()
    assert any("Title cannot be empty or blank" in err["msg"] for err in errors)


def test_create_chat_session_request_rejects_whitespace_only_title():
    with pytest.raises(ValidationError) as exc_info:
        CreateChatSessionRequest(title="   ")
    errors = exc_info.value.errors()
    assert any("Title cannot be empty or blank" in err["msg"] for err in errors)


def test_create_chat_session_request_allows_none_title_with_app_id():
    req = CreateChatSessionRequest(title=None, app_id="my-app")
    assert req.title is None
    assert req.app_id == "my-app"


def test_create_chat_session_request_normalizes_whitespace():
    req = CreateChatSessionRequest(title="  valid  ")
    assert req.title == "valid"
    assert req.app_id is None


def test_create_chat_session_request_default_none():
    req = CreateChatSessionRequest()
    assert req.title is None
    assert req.app_id is None


def test_update_chat_session_request_rejects_empty_title():
    with pytest.raises(ValidationError) as exc_info:
        UpdateChatSessionRequest(title="")
    errors = exc_info.value.errors()
    assert any("Title cannot be empty or blank" in err["msg"] for err in errors)


def test_update_chat_session_request_rejects_whitespace_only_title():
    with pytest.raises(ValidationError) as exc_info:
        UpdateChatSessionRequest(title="   ")
    errors = exc_info.value.errors()
    assert any("Title cannot be empty or blank" in err["msg"] for err in errors)


def test_update_chat_session_request_allows_none_title_with_starred():
    req = UpdateChatSessionRequest(title=None, starred=True)
    assert req.title is None
    assert req.starred is True


def test_update_chat_session_request_normalizes_whitespace():
    req = UpdateChatSessionRequest(title="  valid  ")
    assert req.title == "valid"
    assert req.starred is None


def test_update_chat_session_request_default_none():
    req = UpdateChatSessionRequest()
    assert req.title is None
    assert req.starred is None
