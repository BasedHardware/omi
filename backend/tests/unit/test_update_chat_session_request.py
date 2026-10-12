"""Tests for UpdateChatSessionRequest validation and normalization.

Validates that:
- Empty or whitespace-only titles are rejected with ValidationError (which FastAPI translates to 422).
- None title with starred=True succeeds (star-only updates).
- Valid titles with leading/trailing whitespace are stripped and normalized.
- Default empty payload succeeds.
"""

import pytest
from pydantic import ValidationError

from routers.chat_sessions import UpdateChatSessionRequest


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
