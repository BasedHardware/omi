"""Unit tests for chat_sessions safe deserialization, title generation guards, and error boundaries."""

from enum import Enum
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException
from pydantic import BaseModel

from testing.import_isolation import AutoMockModule, stub_modules

# Define real types for Pydantic annotations
class FeedbackReason(str, Enum):
    inaccurate = "inaccurate"
    irrelevant = "irrelevant"

class FeedbackSurface(str, Enum):
    chat_text = "chat_text"
    chat_voice = "chat_voice"
    chat_notification = "chat_notification"

mock_feedback = AutoMockModule("models.feedback")
mock_feedback.FeedbackReason = FeedbackReason
mock_feedback.FeedbackSurface = FeedbackSurface
mock_feedback.MAX_COMMENT_LENGTH = 1000

class Message(BaseModel):
    id: str = "msg_1"
    text: str = ""
    sender: str = "human"

    @classmethod
    def deserialize_many_safe(cls, records, on_error=None):
        return []

mock_chat_models = AutoMockModule("models.chat")
mock_chat_models.Message = Message

class StatusResponse(BaseModel):
    status: str = "ok"

mock_shared = AutoMockModule("models.shared")
mock_shared.StatusResponse = StatusResponse

with stub_modules({
    "models.feedback": mock_feedback,
    "models.chat": mock_chat_models,
    "models.shared": mock_shared,
    "database.chat": AutoMockModule("database.chat"),
    "database.llm_usage": AutoMockModule("database.llm_usage"),
    "utils.chat": AutoMockModule("utils.chat"),
    "utils.chat_rating_triage": AutoMockModule("utils.chat_rating_triage"),
    "utils.feedback": AutoMockModule("utils.feedback"),
    "utils.generated_compute": AutoMockModule("utils.generated_compute"),
    "utils.llm.clients": AutoMockModule("utils.llm.clients"),
    "utils.llm.usage_tracker": AutoMockModule("utils.llm.usage_tracker"),
    "utils.other.endpoints": AutoMockModule("utils.other.endpoints"),
    "utils.product_metrics": AutoMockModule("utils.product_metrics"),
}):
    from models.chat_session import ChatSessionResponse
    import routers.chat_sessions as cs_router
    from routers.chat_sessions import (
        GenerateTitleRequest,
        TitleMessageInput,
    )


class TestChatSessionSafeDeserialization:
    """Test ChatSessionResponse.deserialize_many_safe."""

    def test_deserialize_many_safe_filters_malformed(self):
        """Filters out non-dict, missing id, and invalid documents."""
        now = datetime.now(timezone.utc)
        valid_doc = {
            "id": "sess_1",
            "title": "Discussion",
            "created_at": now,
            "updated_at": now,
            "message_count": 2,
            "starred": False,
        }
        malformed_doc = {
            "id": "sess_2",
            "title": "Broken",
            "created_at": "invalid_date_format",
        }
        empty_doc = {}
        none_doc = None

        records = [valid_doc, malformed_doc, empty_doc, none_doc]
        errors = []
        result = ChatSessionResponse.deserialize_many_safe(
            records,
            on_error=lambda r, exc: errors.append(r.get("id")),
        )

        assert len(result) == 1
        assert result[0].id == "sess_1"
        assert result[0].title == "Discussion"
        assert errors == ["sess_2"]


class TestChatSessionsRouterGuards:
    """Test chat_sessions router endpoints and validation."""

    def test_get_chat_sessions_safe_against_poisoned_row(self):
        """get_chat_sessions skips malformed sessions without 500."""
        now = datetime.now(timezone.utc)
        valid_sess = {
            "id": "sess_1",
            "title": "Test Chat",
            "created_at": now,
            "updated_at": now,
            "message_count": 1,
            "starred": False,
        }
        poisoned_sess = {"id": "sess_poison", "created_at": "not-a-datetime"}

        with patch.object(cs_router.chat_db, "get_chat_sessions", return_value=[valid_sess, poisoned_sess]):
            res = cs_router.get_chat_sessions(uid="usr_1")
            assert len(res) == 1
            assert res[0].id == "sess_1"

    def test_session_id_empty_guards(self):
        """Rejects empty or whitespace session_id in path endpoints."""
        with pytest.raises(HTTPException) as exc:
            cs_router.get_chat_session(session_id="   ", uid="usr_1")
        assert exc.value.status_code == 400

        with pytest.raises(HTTPException) as exc:
            cs_router.delete_chat_session(session_id="   ", uid="usr_1")
        assert exc.value.status_code == 400

    def test_update_chat_session_title_validation(self):
        """Rejects whitespace-only title in update_chat_session."""
        req = cs_router.UpdateChatSessionRequest(title="   ")
        with pytest.raises(HTTPException) as exc:
            cs_router.update_chat_session(session_id="sess_1", request=req, uid="usr_1")
        assert exc.value.status_code == 400
        assert "Title cannot be empty" in exc.value.detail


class TestGenerateTitleGuardsAndBoundaries:
    """Test generate_session_title resilience, LLM response unpacking, and error boundary."""

    def test_generate_title_session_not_found(self):
        """Raises 404 when session_id does not exist."""
        req = GenerateTitleRequest(
            session_id="sess_missing",
            messages=[TitleMessageInput(text="Hello", sender="human")],
        )
        with patch.object(cs_router.chat_db, "get_chat_session_by_id", return_value=None):
            with pytest.raises(HTTPException) as exc:
                cs_router.generate_session_title(request=req, uid="usr_1")
            assert exc.value.status_code == 404

    def test_generate_title_with_string_llm_response(self):
        """Unpacks plain string LLM response correctly."""
        req = GenerateTitleRequest(
            session_id="sess_1",
            messages=[TitleMessageInput(text="Let's build a parser", sender="human")],
        )
        mock_response = MagicMock()
        mock_response.content = "Building a Parser"

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response

        with patch.object(cs_router.chat_db, "get_chat_session_by_id", return_value={"id": "sess_1"}), \
             patch.object(cs_router, "get_llm", return_value=mock_llm), \
             patch.object(cs_router.chat_db, "update_chat_session") as mock_update:

            res = cs_router.generate_session_title(request=req, uid="usr_1")
            assert res == {"title": "Building a Parser"}
            mock_update.assert_called_once_with("usr_1", "sess_1", title="Building a Parser")

    def test_generate_title_with_structured_list_llm_response(self):
        """Unpacks list of content blocks without AttributeError."""
        req = GenerateTitleRequest(
            session_id="sess_1",
            messages=[TitleMessageInput(text="Fix database pool", sender="human")],
        )
        mock_response = MagicMock()
        mock_response.content = [{"type": "text", "text": "Database Pool Fix"}]

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response

        with patch.object(cs_router.chat_db, "get_chat_session_by_id", return_value={"id": "sess_1"}), \
             patch.object(cs_router, "get_llm", return_value=mock_llm), \
             patch.object(cs_router.chat_db, "update_chat_session") as mock_update:

            res = cs_router.generate_session_title(request=req, uid="usr_1")
            assert res == {"title": "Database Pool Fix"}
            mock_update.assert_called_once_with("usr_1", "sess_1", title="Database Pool Fix")

    def test_generate_title_llm_failure_error_boundary(self):
        """Catches LLM exceptions and falls back to first message excerpt or New Chat."""
        req = GenerateTitleRequest(
            session_id="sess_1",
            messages=[TitleMessageInput(text="Optimize rendering loop in widget", sender="human")],
        )
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = RuntimeError("OpenAI rate limit exceeded")

        with patch.object(cs_router.chat_db, "get_chat_session_by_id", return_value={"id": "sess_1"}), \
             patch.object(cs_router, "get_llm", return_value=mock_llm), \
             patch.object(cs_router.chat_db, "update_chat_session") as mock_update:

            res = cs_router.generate_session_title(request=req, uid="usr_1")
            # Fallback to first human message
            assert res == {"title": "Optimize rendering loop in wid"}
            mock_update.assert_called_once_with("usr_1", "sess_1", title="Optimize rendering loop in wid")
