"""Router-level tests for routers/screen_frames.py.

Follows the direct-call pattern from tests/routers/test_imports.py: call the
endpoint function directly with uid=UID and patch.object the db modules the
router imports, rather than spinning up a full FastAPI TestClient.

Covers: a digest mismatch fails the whole adjudication request with 400,
admission is refused (409) when the account's
meeting_note_screenshots_enabled setting is off, and the public shared route
returns an empty set whenever sharing isn't currently on — never a 404 (that
would leak whether a conversation_id exists).
"""

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from models.conversation_enums import ConversationStatus, ConversationVisibility
from models.screen_frame import ScreenFrameAdjudicationRequest, ScreenFrameCandidateIn, ScreenFrameSubjectIn
from routers import screen_frames as screen_frames_mod

UID = "user-1"
CONVERSATION_ID = "conv-1"


def _conversation(**overrides):
    started_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    base = {
        "id": CONVERSATION_ID,
        "status": ConversationStatus.completed.value,
        "started_at": started_at,
        "finished_at": started_at + timedelta(minutes=30),
        "deleted": False,
        "visibility": ConversationVisibility.private.value,
    }
    base.update(overrides)
    return base


def _candidate(**overrides) -> ScreenFrameCandidateIn:
    raw = b"some fake candidate bytes"
    base = dict(
        client_frame_id="c1",
        captured_at=datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc),
        mime_type="image/jpeg",
        declared_width=800,
        declared_height=600,
        sha256_base64=base64.b64encode(hashlib.sha256(raw).digest()).decode(),
        bytes_base64=base64.b64encode(raw).decode(),
    )
    base.update(overrides)
    return ScreenFrameCandidateIn(**base)


def _request(**overrides) -> ScreenFrameAdjudicationRequest:
    base = dict(
        schema_version=1,
        attempt_id=uuid4(),
        purpose="meeting_note_v1",
        subject=ScreenFrameSubjectIn(kind="conversation", id=CONVERSATION_ID),
        candidates=[_candidate()],
    )
    base.update(overrides)
    return ScreenFrameAdjudicationRequest(**base)


@pytest.fixture(autouse=True)
def _stub_admission_dependencies(monkeypatch):
    fake_conversations_db = MagicMock()
    fake_conversations_db.get_conversation.return_value = _conversation()
    fake_conversations_db.is_soft_deleted.return_value = False
    monkeypatch.setattr(screen_frames_mod, "conversations_db", fake_conversations_db)
    monkeypatch.setattr(screen_frames_mod, "screen_frames_db", fake_conversations_db)

    fake_users_db = MagicMock()
    fake_users_db.get_meeting_note_screenshots_enabled.return_value = True
    monkeypatch.setattr(screen_frames_mod, "users_db", fake_users_db)

    fake_redis_db = MagicMock()
    fake_redis_db.reserve_screen_frame_adjudication_attempt.return_value = None
    monkeypatch.setattr(screen_frames_mod, "redis_db", fake_redis_db)

    return fake_conversations_db, fake_users_db, fake_redis_db


class TestDigestMismatch:
    def test_digest_mismatch_returns_400_for_the_whole_request(self):
        bad_candidate = _candidate(sha256_base64=base64.b64encode(hashlib.sha256(b"different bytes").digest()).decode())
        request = _request(candidates=[bad_candidate])

        with pytest.raises(HTTPException) as exc_info:
            screen_frames_mod.adjudicate_screen_frames(request, uid=UID)

        assert exc_info.value.status_code == 400


class TestAdmissionRefusedWhenSettingDisabled:
    def test_returns_409_when_meeting_note_screenshots_disabled(self, _stub_admission_dependencies):
        _fake_conversations_db, fake_users_db, _fake_redis_db = _stub_admission_dependencies
        fake_users_db.get_meeting_note_screenshots_enabled.return_value = False

        request = _request()
        with pytest.raises(HTTPException) as exc_info:
            screen_frames_mod.adjudicate_screen_frames(request, uid=UID)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "meeting_note_screenshots_disabled"


class TestAdmissionRefusedWhenNotCompleted:
    def test_returns_409_when_conversation_not_completed(self, _stub_admission_dependencies):
        fake_conversations_db, _fake_users_db, _fake_redis_db = _stub_admission_dependencies
        fake_conversations_db.get_conversation.return_value = _conversation(status=ConversationStatus.in_progress.value)

        request = _request()
        with pytest.raises(HTTPException) as exc_info:
            screen_frames_mod.adjudicate_screen_frames(request, uid=UID)

        assert exc_info.value.status_code == 409


class TestUnknownConversationIs404:
    def test_returns_404_when_conversation_missing(self, _stub_admission_dependencies):
        fake_conversations_db, _fake_users_db, _fake_redis_db = _stub_admission_dependencies
        fake_conversations_db.get_conversation.return_value = None

        request = _request()
        with pytest.raises(HTTPException) as exc_info:
            screen_frames_mod.adjudicate_screen_frames(request, uid=UID)

        assert exc_info.value.status_code == 404


class TestSettingsRoutes:
    def test_get_reads_from_users_db(self, _stub_admission_dependencies):
        _fake_conversations_db, fake_users_db, _fake_redis_db = _stub_admission_dependencies
        fake_users_db.get_meeting_note_screenshots_enabled.return_value = False

        result = screen_frames_mod.get_screen_frame_settings(uid=UID)
        assert result.meeting_note_screenshots_enabled is False

    def test_patch_writes_and_echoes(self, _stub_admission_dependencies):
        _fake_conversations_db, fake_users_db, _fake_redis_db = _stub_admission_dependencies
        from models.screen_frame import ScreenFrameSettingsUpdateRequest

        result = screen_frames_mod.update_screen_frame_settings(
            ScreenFrameSettingsUpdateRequest(meeting_note_screenshots_enabled=False), uid=UID
        )
        fake_users_db.set_meeting_note_screenshots_enabled.assert_called_once_with(UID, False)
        assert result.meeting_note_screenshots_enabled is False


class TestSharedScreenshotsRoute:
    def test_empty_when_conversation_id_unknown(self, monkeypatch):
        fake_redis_db = MagicMock()
        fake_redis_db.get_conversation_uid.return_value = ""
        monkeypatch.setattr(screen_frames_mod, "redis_db", fake_redis_db)

        result = screen_frames_mod.get_shared_conversation_screenshots(CONVERSATION_ID)
        assert result == screen_frames_mod.EMPTY_FRAME_SET

    def test_empty_when_visibility_is_private(self, monkeypatch):
        fake_redis_db = MagicMock()
        fake_redis_db.get_conversation_uid.return_value = UID
        monkeypatch.setattr(screen_frames_mod, "redis_db", fake_redis_db)

        fake_conversations_db = MagicMock()
        fake_conversations_db.get_conversation.return_value = _conversation(
            visibility=ConversationVisibility.private.value
        )
        fake_conversations_db.is_soft_deleted.return_value = False
        monkeypatch.setattr(screen_frames_mod, "conversations_db", fake_conversations_db)
        monkeypatch.setattr(screen_frames_mod, "screen_frames_db", fake_conversations_db)

        result = screen_frames_mod.get_shared_conversation_screenshots(CONVERSATION_ID)
        assert result == screen_frames_mod.EMPTY_FRAME_SET

    def test_empty_when_screenshot_sharing_disabled_even_if_publicly_shared(self, monkeypatch):
        fake_redis_db = MagicMock()
        fake_redis_db.get_conversation_uid.return_value = UID
        monkeypatch.setattr(screen_frames_mod, "redis_db", fake_redis_db)

        fake_conversations_db = MagicMock()
        fake_conversations_db.get_conversation.return_value = _conversation(
            visibility=ConversationVisibility.public.value, screenshot_sharing_enabled=False
        )
        fake_conversations_db.is_soft_deleted.return_value = False
        fake_conversations_db.get_conversation_screenshot_sharing_enabled.return_value = False
        monkeypatch.setattr(screen_frames_mod, "conversations_db", fake_conversations_db)
        monkeypatch.setattr(screen_frames_mod, "screen_frames_db", fake_conversations_db)

        result = screen_frames_mod.get_shared_conversation_screenshots(CONVERSATION_ID)
        assert result == screen_frames_mod.EMPTY_FRAME_SET

    def test_builds_frame_set_when_public_and_sharing_enabled(self, monkeypatch):
        fake_redis_db = MagicMock()
        fake_redis_db.get_conversation_uid.return_value = UID
        monkeypatch.setattr(screen_frames_mod, "redis_db", fake_redis_db)

        fake_conversations_db = MagicMock()
        fake_conversations_db.get_conversation.return_value = _conversation(
            visibility=ConversationVisibility.public.value, screenshot_sharing_enabled=True
        )
        fake_conversations_db.is_soft_deleted.return_value = False
        fake_conversations_db.get_conversation_screenshot_sharing_enabled.return_value = True
        monkeypatch.setattr(screen_frames_mod, "conversations_db", fake_conversations_db)
        monkeypatch.setattr(screen_frames_mod, "screen_frames_db", fake_conversations_db)

        fake_enforcement = MagicMock()
        sentinel = object()
        fake_enforcement.build_frame_set_response.return_value = sentinel
        monkeypatch.setattr(screen_frames_mod, "enforcement", fake_enforcement)

        result = screen_frames_mod.get_shared_conversation_screenshots(CONVERSATION_ID)
        assert result is sentinel
        fake_enforcement.build_frame_set_response.assert_called_once_with(UID, CONVERSATION_ID)
