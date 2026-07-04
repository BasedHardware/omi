"""Unit tests for GET /v1/focus-sessions/{session_id} (fetch one focus session).

Exercises the router handler's 404-vs-passthrough logic and the database
helper's exists-check + id injection, using the sanctioned seams (import the
modules normally and patch.object on the singletons — no sys.modules mutation).
"""

import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import database.focus_sessions as focus_sessions_db
from routers import focus_sessions as focus_router


# ---------------------------------------------------------------------------
# Router handler: 404 when missing, passthrough when found
# ---------------------------------------------------------------------------
def test_handler_returns_session_when_found():
    session = {"id": "s1", "status": "focused", "app_or_site": "Editor", "description": "x"}
    with patch.object(focus_sessions_db, "get_focus_session", return_value=session) as m:
        result = focus_router.get_focus_session(session_id="s1", uid="u1")
    assert result == session
    m.assert_called_once_with("u1", "s1")


def test_handler_raises_404_when_missing():
    with patch.object(focus_sessions_db, "get_focus_session", return_value=None):
        with pytest.raises(HTTPException) as exc:
            focus_router.get_focus_session(session_id="nope", uid="u1")
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# DB helper: None when the doc is absent, id injected when present
# ---------------------------------------------------------------------------
def _fake_doc(exists, data=None):
    doc = MagicMock()
    doc.exists = exists
    doc.id = "s1"
    doc.to_dict.return_value = data if data is not None else {}
    return doc


def test_db_get_returns_none_when_absent():
    col = MagicMock()
    col.document.return_value.get.return_value = _fake_doc(False)
    with patch.object(focus_sessions_db, "_user_col", return_value=col):
        assert focus_sessions_db.get_focus_session("u1", "s1") is None


def test_db_get_injects_id_when_present():
    col = MagicMock()
    col.document.return_value.get.return_value = _fake_doc(True, {"status": "distracted", "app_or_site": "YT"})
    with patch.object(focus_sessions_db, "_user_col", return_value=col):
        result = focus_sessions_db.get_focus_session("u1", "s1")
    assert result == {"id": "s1", "status": "distracted", "app_or_site": "YT"}
    col.document.assert_called_once_with("s1")
