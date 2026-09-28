"""A partial or legacy stored screen frame costs that frame, not the whole screenshots read.

build_frame_set_response already skipped a stored frame that failed ConversationScreenFrame
validation, but a doc missing `id` / `captured_at` or holding a non-numeric `rank` or a
non-iterable `labels` fails earlier, inside _to_api_frame, with KeyError / ValueError / TypeError.
Those escaped the loop and 500'd GET /v1/conversations/{id}/screenshots and the public
GET /v1/conversations/{id}/shared/screenshots, hiding every good screenshot in the note.
"""

import logging
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.conversation_enums import ConversationVisibility
from routers import screen_frames as screen_frames_router
from utils.screen_frames import enforcement

UID = "user-1"
CONVERSATION_ID = "conv-1"

_GOOD = {
    "id": "good",
    "captured_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    "role": "banner",
    "rank": 0,
    "caption": "Roadmap slide",
    "labels": [],
    "width": 800,
    "height": 600,
    "ground": {"stops": ["#111111", "#222222"], "is_neutral": True},
}
_STRIP = {**_GOOD, "id": "bad", "role": "strip", "rank": 1}
_WITHOUT_CAPTURED_AT = {k: v for k, v in _STRIP.items() if k != "captured_at"}
_WITHOUT_ID = {k: v for k, v in _STRIP.items() if k != "id"}

_PARTIAL_DOCS = {
    "missing_captured_at": _WITHOUT_CAPTURED_AT,  # KeyError
    "missing_id": _WITHOUT_ID,  # KeyError
    "non_numeric_rank": {**_STRIP, "rank": "first"},  # ValueError
    "non_iterable_labels": {**_STRIP, "labels": 5},  # TypeError
}


@pytest.fixture
def stored_frames(monkeypatch):
    frames = []
    db = enforcement.screen_frames_db
    monkeypatch.setattr(db, "get_conversation_screen_frames", lambda *_: list(frames))
    monkeypatch.setattr(db, "get_conversation_screen_frames_revision", lambda *_: 2)
    monkeypatch.setattr(db, "get_conversation_screen_frames_adjudicated_at", lambda *_: None)
    monkeypatch.setattr(db, "get_conversation_screen_frames_selection_fingerprint", lambda *_: None)
    monkeypatch.setattr(enforcement.storage, "get_screen_frame_signed_url", lambda *_: "https://signed/content")
    monkeypatch.setattr(enforcement.storage, "get_screen_frame_thumbnail_signed_url", lambda *_: "https://signed/thumb")
    return frames


@pytest.mark.parametrize("partial_doc", _PARTIAL_DOCS.values(), ids=list(_PARTIAL_DOCS))
def test_partial_stored_frame_is_skipped_and_the_rest_are_served(stored_frames, partial_doc):
    stored_frames.extend([_GOOD, partial_doc])

    frame_set = enforcement.build_frame_set_response(UID, CONVERSATION_ID)

    assert frame_set.banner is not None and frame_set.banner.id == "good"
    assert frame_set.strip == []
    assert frame_set.revision == 2


def test_skip_log_names_the_frame_and_error_type_but_not_the_stored_value(stored_frames, caplog):
    stored_frames.extend([_GOOD, {**_STRIP, "rank": "stored-rank-value"}])

    with caplog.at_level(logging.WARNING, logger=enforcement.__name__):
        enforcement.build_frame_set_response(UID, CONVERSATION_ID)

    assert "frame_id=bad" in caplog.text
    assert "ValueError" in caplog.text
    assert "stored-rank-value" not in caplog.text


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(screen_frames_router.router)
    app.dependency_overrides[screen_frames_router.auth.get_current_user_uid] = lambda: UID
    return TestClient(app, raise_server_exceptions=False)


def _conversation(visibility: ConversationVisibility) -> dict:
    return {"id": CONVERSATION_ID, "deleted": False, "visibility": visibility.value}


def test_owner_screenshots_route_serves_the_good_frames(stored_frames, monkeypatch):
    stored_frames.extend([_GOOD, _WITHOUT_CAPTURED_AT])
    conversation = _conversation(ConversationVisibility.private)
    monkeypatch.setattr(screen_frames_router.conversations_db, "get_conversation", lambda *_: conversation)
    monkeypatch.setattr(screen_frames_router.users_db, "get_meeting_note_screenshots_enabled", lambda *_: True)

    response = _client().get(f"/v1/conversations/{CONVERSATION_ID}/screenshots")

    assert response.status_code == 200
    assert response.json()["banner"]["id"] == "good"
    assert response.json()["strip"] == []


def test_public_shared_screenshots_route_serves_the_good_frames(stored_frames, monkeypatch):
    stored_frames.extend([_GOOD, _WITHOUT_ID])
    conversation = _conversation(ConversationVisibility.shared)
    monkeypatch.setattr(screen_frames_router.redis_db, "get_conversation_uid", lambda *_: UID)
    monkeypatch.setattr(screen_frames_router.conversations_db, "get_conversation", lambda *_: conversation)
    monkeypatch.setattr(screen_frames_router.users_db, "get_meeting_note_screenshots_enabled", lambda *_: True)

    response = _client().get(f"/v1/conversations/{CONVERSATION_ID}/shared/screenshots")

    assert response.status_code == 200
    assert response.json()["banner"]["id"] == "good"
    assert response.json()["strip"] == []
