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
    # Egress is default-off in production and the gate sits above everything else in
    # the handler, so without this every test here would assert against a 409 from
    # the gate rather than the behaviour it means to pin. TestEgressDisabled below
    # is where the off state is covered.
    monkeypatch.setenv("SCREEN_FRAME_EGRESS_ENABLED", "true")
    monkeypatch.setenv("BUCKET_SCREEN_FRAMES", "test-screen-frames")
    monkeypatch.setenv("SCREEN_FRAME_SIGNING_SECRET", "test-secret")

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
    # The owner GET route drains cross-environment cleanup records in the background.
    monkeypatch.setattr(screen_frames_mod.screen_frame_store, "drain_screen_frame_cleanups", MagicMock(return_value=0))

    return fake_conversations_db, fake_users_db, fake_redis_db


class TestEgressDisabled:
    """The gate that makes merging this safe before the bucket exists.

    The judge is the first step that sends screen bytes to Gemini and it runs two
    stages before any bucket or signer check, so these assert on what did NOT
    happen: no judging, and no adjudication stamp.
    """

    def test_returns_409_when_flag_not_set(self, _stub_admission_dependencies, monkeypatch):
        monkeypatch.delenv("SCREEN_FRAME_EGRESS_ENABLED", raising=False)

        with pytest.raises(HTTPException) as exc_info:
            screen_frames_mod.adjudicate_screen_frames(_request(), uid=UID)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "screen_frame_egress_unavailable"

    def test_returns_409_when_flag_set_but_bucket_missing(self, _stub_admission_dependencies, monkeypatch):
        monkeypatch.delenv("BUCKET_SCREEN_FRAMES", raising=False)

        with pytest.raises(HTTPException) as exc_info:
            screen_frames_mod.adjudicate_screen_frames(_request(), uid=UID)

        assert exc_info.value.status_code == 409

    def test_returns_409_when_no_signer_is_configured(self, _stub_admission_dependencies, monkeypatch):
        monkeypatch.delenv("SCREEN_FRAME_SIGNING_SECRET", raising=False)
        monkeypatch.delenv("SCREEN_FRAME_KMS_KEY", raising=False)

        with pytest.raises(HTTPException) as exc_info:
            screen_frames_mod.adjudicate_screen_frames(_request(), uid=UID)

        assert exc_info.value.status_code == 409

    def test_nothing_is_judged_and_nothing_is_stamped_when_disabled(self, _stub_admission_dependencies, monkeypatch):
        fake_conversations_db, _fake_users_db, _fake_redis_db = _stub_admission_dependencies
        monkeypatch.delenv("SCREEN_FRAME_EGRESS_ENABLED", raising=False)
        judged = MagicMock()
        monkeypatch.setattr(screen_frames_mod, "judge_canonical", judged)

        with pytest.raises(HTTPException):
            screen_frames_mod.adjudicate_screen_frames(_request(), uid=UID)

        judged.assert_not_called()
        # A stamp here would tell the client this conversation was already decided,
        # and it would never retry once the feature is switched on.
        fake_conversations_db.mark_conversation_screen_frames_adjudicated.assert_not_called()


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


class TestCaptureWindowVerification:
    def test_trusted_transcript_window_rejects_early_lifecycle_frame_and_accepts_speech_frame(self):
        started_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        conversation = _conversation(
            started_at=started_at,
            finished_at=started_at + timedelta(minutes=16, seconds=34),
            transcript_segments=[{"text": "speech", "start": 14 * 60 + 39, "end": 16 * 60 + 34}],
            external_data={"from_segments_client_session_id": "desktop-session"},
        )

        with pytest.raises(HTTPException) as exc_info:
            screen_frames_mod._validate_capture_window(
                conversation, [_candidate(captured_at=started_at + timedelta(minutes=1))]
            )
        assert exc_info.value.detail["code"] == "captured_at_outside_conversation_window"

        fingerprint = screen_frames_mod._validate_capture_window(
            conversation, [_candidate(captured_at=started_at + timedelta(minutes=15))]
        )
        assert fingerprint == "meeting-content-v1:1767226479000:1767226594000"

    def test_inconsistent_legacy_listen_window_keeps_old_client_fallback(self):
        started_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        conversation = _conversation(
            started_at=started_at,
            finished_at=started_at + timedelta(minutes=16, seconds=34),
            transcript_segments=[{"text": "speech", "start": 0, "end": 109}],
        )

        fingerprint = screen_frames_mod._validate_capture_window(
            conversation, [_candidate(captured_at=started_at + timedelta(minutes=1))]
        )

        assert fingerprint == screen_frames_mod.LEGACY_LIFECYCLE_FINGERPRINT


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


class TestAuthenticatedScreenshotsRoute:
    def test_empty_set_when_account_setting_off(self, _stub_admission_dependencies, monkeypatch):
        """Contract §9: the account gate hides existing frames on every surface, not just
        the ones that remember to check it client-side — the web GET goes through this
        route and has no local gate."""
        _fake_conversations_db, fake_users_db, _fake_redis_db = _stub_admission_dependencies
        fake_users_db.get_meeting_note_screenshots_enabled.return_value = False

        fake_enforcement = MagicMock()
        monkeypatch.setattr(screen_frames_mod, "enforcement", fake_enforcement)

        result = screen_frames_mod.get_conversation_screenshots(CONVERSATION_ID, uid=UID)
        assert result == screen_frames_mod.EMPTY_FRAME_SET
        fake_enforcement.build_frame_set_response.assert_not_called()

    def test_builds_frame_set_when_account_setting_on(self, _stub_admission_dependencies, monkeypatch):
        from models.screen_frame import ConversationScreenFrameSet

        fake_enforcement = MagicMock()
        built = ConversationScreenFrameSet(revision=3)
        fake_enforcement.build_frame_set_response.return_value = built
        monkeypatch.setattr(screen_frames_mod, "enforcement", fake_enforcement)

        result = screen_frames_mod.get_conversation_screenshots(CONVERSATION_ID, uid=UID)
        assert result.revision == 3 and result.trusted_selection_fingerprint is None
        fake_enforcement.build_frame_set_response.assert_called_once_with(UID, CONVERSATION_ID)


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

        fake_users_db = MagicMock()
        fake_users_db.get_meeting_note_screenshots_enabled.return_value = True
        monkeypatch.setattr(screen_frames_mod, "users_db", fake_users_db)

        fake_enforcement = MagicMock()
        sentinel = object()
        fake_enforcement.build_frame_set_response.return_value = sentinel
        monkeypatch.setattr(screen_frames_mod, "enforcement", fake_enforcement)

        result = screen_frames_mod.get_shared_conversation_screenshots(CONVERSATION_ID)
        assert result is sentinel
        # Pinned deliberately: this public route resolves the OWNER's uid from the share index,
        # and serving any other uid's frames from an unauthenticated endpoint is the worst thing
        # it could do. Asserting the return value alone would not catch that.
        fake_enforcement.build_frame_set_response.assert_called_once_with(UID, CONVERSATION_ID)

    def test_empty_when_account_setting_off_even_if_publicly_shared(self, monkeypatch):
        """Contract §9 on the public route too: the owner turning the account gate off
        must hide the shared note's screenshots, not just the owner's own clients."""
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

        fake_users_db = MagicMock()
        fake_users_db.get_meeting_note_screenshots_enabled.return_value = False
        monkeypatch.setattr(screen_frames_mod, "users_db", fake_users_db)

        result = screen_frames_mod.get_shared_conversation_screenshots(CONVERSATION_ID)
        assert result == screen_frames_mod.EMPTY_FRAME_SET


def _live_meeting(status: str, **overrides):
    """A cloud-listen meeting whose transcript already fixes the trusted window."""
    started_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    fields = dict(
        status=status,
        started_at=started_at,
        finished_at=None,
        audio_timeline={"version": 2},
        transcript_segments=[{"text": "hello", "start": 10, "end": 20}, {"text": "bye", "start": 300, "end": 320}],
    )
    fields.update(overrides)
    return _conversation(**fields)


class TestOnePassAdmission:
    """The Mac adjudicates before it finalizes, so open conversations must be admitted."""

    @pytest.mark.parametrize("status", [ConversationStatus.in_progress.value, ConversationStatus.processing.value])
    def test_an_open_conversation_with_a_trusted_window_is_admitted(self, status, _stub_admission_dependencies):
        screen_frames_mod._require_adjudication_admission(UID, _live_meeting(status))

    def test_an_open_conversation_without_speech_waits_for_completion(self, _stub_admission_dependencies):
        conversation = _live_meeting(ConversationStatus.in_progress.value, transcript_segments=[])
        with pytest.raises(HTTPException) as exc_info:
            screen_frames_mod._require_adjudication_admission(UID, conversation)
        assert exc_info.value.detail["code"] == "conversation_not_completed"

    def test_other_statuses_stay_refused(self, _stub_admission_dependencies):
        for status in (ConversationStatus.failed.value, ConversationStatus.merging.value):
            with pytest.raises(HTTPException):
                screen_frames_mod._require_adjudication_admission(UID, _live_meeting(status))

    def test_the_account_setting_still_gates_an_open_conversation(self, _stub_admission_dependencies):
        _fake_conversations_db, fake_users_db, _fake_redis_db = _stub_admission_dependencies
        fake_users_db.get_meeting_note_screenshots_enabled.return_value = False
        with pytest.raises(HTTPException) as exc_info:
            screen_frames_mod._require_adjudication_admission(UID, _live_meeting(ConversationStatus.in_progress.value))
        assert exc_info.value.detail["code"] == "meeting_note_screenshots_disabled"

    def test_finalize_does_not_move_the_fingerprint_adjudicated_before_it(self):
        """Finalize flips status and stamps finished_at; the fingerprint is the transcript span, so it holds.

        It moves only if finalize changes segment timing (a late flush extends the last
        segment); the client then sees a different fingerprint and offers the new tail.
        """
        live = _live_meeting(ConversationStatus.in_progress.value)
        candidate = [_candidate(captured_at=live["started_at"] + timedelta(seconds=60))]
        before = screen_frames_mod._validate_capture_window(live, candidate)
        finalized = {
            **live,
            "status": ConversationStatus.completed.value,
            "finished_at": live["started_at"] + timedelta(seconds=320),
        }
        assert screen_frames_mod._validate_capture_window(finalized, candidate) == before
        assert before == "meeting-content-v1:1767225610000:1767225920000"


class TestConcurrentJudging:
    """Only the judge call runs on the LLM pool, concurrently; the writer runs after it."""

    def _candidates(self, count):
        return [
            _candidate(client_frame_id=f"c{i}", captured_at=datetime(2026, 1, 1, 0, i + 1, tzinfo=timezone.utc))
            for i in range(count)
        ]

    def _stub_seams(self, monkeypatch, *, judge, commit):
        monkeypatch.setattr(screen_frames_mod, "canonicalize_for_judging", lambda **kw: MagicMock(name="canonical"))
        monkeypatch.setattr(screen_frames_mod, "judge_canonical", judge)
        monkeypatch.setattr(screen_frames_mod, "commit_approved", commit)
        enforce = MagicMock(return_value=(screen_frames_mod.EMPTY_FRAME_SET, False))
        monkeypatch.setattr(screen_frames_mod.enforcement, "enforce_and_persist", enforce)
        return enforce

    def test_judging_is_concurrent_and_writes_stay_off_the_llm_pool(self, _stub_admission_dependencies, monkeypatch):
        import threading

        barrier = threading.Barrier(3, timeout=5)
        commit_threads = []

        def judge(*, candidate, **_kwargs):
            barrier.wait()  # times out if the judge calls ran one at a time
            return MagicMock(name=f"judgement-{candidate.client_frame_id}")

        def commit(*, candidate, **_kwargs):
            commit_threads.append(threading.current_thread().name)
            return MagicMock(frame_id=f"frame-{candidate.client_frame_id}")

        enforce = self._stub_seams(monkeypatch, judge=judge, commit=commit)

        screen_frames_mod.adjudicate_screen_frames(_request(candidates=self._candidates(3)), uid=UID)

        assert len(commit_threads) == 3
        assert not any(name.startswith("llm") for name in commit_threads)
        persisted = enforce.call_args.args[3]
        assert [frame.frame_id for frame in persisted] == ["frame-c0", "frame-c1", "frame-c2"]

    def test_a_writer_failure_is_503_and_removes_bytes_already_written(self, _stub_admission_dependencies, monkeypatch):
        """Frames written before the failure have no Firestore doc and no delete path
        would ever find them; they are removed before the error returns."""
        from utils.screen_frames.writer import ScreenFrameWriteError

        def commit(*, candidate, **_kwargs):
            if candidate.client_frame_id == "c1":
                raise ScreenFrameWriteError("upload_failed")
            return MagicMock(frame_id=f"landed-{candidate.client_frame_id}")

        enforce = self._stub_seams(monkeypatch, judge=lambda **kw: MagicMock(), commit=commit)
        deleted = []
        monkeypatch.setattr(
            screen_frames_mod.storage,
            "delete_screen_frame_blobs",
            lambda uid, cid, fid: deleted.append((uid, cid, fid)),
        )

        with pytest.raises(HTTPException) as exc_info:
            screen_frames_mod.adjudicate_screen_frames(_request(candidates=self._candidates(2)), uid=UID)

        assert exc_info.value.status_code == 503
        assert deleted == [(UID, CONVERSATION_ID, "landed-c0")]
        enforce.assert_not_called()

    def test_rejected_candidates_are_never_written(self, _stub_admission_dependencies, monkeypatch):
        commit = MagicMock()
        self._stub_seams(monkeypatch, judge=lambda **kw: None, commit=commit)

        response = screen_frames_mod.adjudicate_screen_frames(_request(candidates=self._candidates(2)), uid=UID)

        commit.assert_not_called()
        assert response.outcome == "no_approved_frames"


class TestPerFrameDeleteHonoursTheAccountSetting:
    def test_setting_off_returns_the_gated_empty_set(self, _stub_admission_dependencies, monkeypatch):
        _fake_conversations_db, fake_users_db, _fake_redis_db = _stub_admission_dependencies
        fake_users_db.get_meeting_note_screenshots_enabled.return_value = False
        monkeypatch.setattr(screen_frames_mod.screen_frame_store, "delete_screen_frame", lambda *a: True)
        remaining = MagicMock(name="remaining_frame_set")
        promote = MagicMock(return_value=remaining)
        monkeypatch.setattr(screen_frames_mod.enforcement, "promote_banner_after_deletion", promote)

        result = screen_frames_mod.delete_conversation_screenshot(CONVERSATION_ID, "frame-a", uid=UID)

        promote.assert_called_once_with(UID, CONVERSATION_ID)  # the delete itself still happens
        assert result == screen_frames_mod.EMPTY_FRAME_SET and result.revision == 0

    def test_setting_on_returns_the_remaining_set(self, _stub_admission_dependencies, monkeypatch):
        monkeypatch.setattr(screen_frames_mod.screen_frame_store, "delete_screen_frame", lambda *a: True)
        remaining = MagicMock(name="remaining_frame_set")
        monkeypatch.setattr(
            screen_frames_mod.enforcement, "promote_banner_after_deletion", MagicMock(return_value=remaining)
        )

        assert screen_frames_mod.delete_conversation_screenshot(CONVERSATION_ID, "frame-a", uid=UID) is remaining


def test_owner_read_drains_cleanup_records_for_this_bucket(_stub_admission_dependencies, monkeypatch):
    drain = screen_frames_mod.screen_frame_store.drain_screen_frame_cleanups
    monkeypatch.setattr(screen_frames_mod.enforcement, "build_frame_set_response", MagicMock())

    submitted = []
    monkeypatch.setattr(screen_frames_mod, "submit_with_context", lambda pool, fn: submitted.append((pool, fn)))

    screen_frames_mod.get_conversation_screenshots(CONVERSATION_ID, uid=UID)

    assert submitted == [(screen_frames_mod.storage_executor, drain)]


class TestTrustedSelectionFingerprint:
    """Owner route only: the client checks its selection without GET /v1/conversations/{id}."""

    EXPECTED = "meeting-content-v1:1767225610000:1767225920000"

    def _owner_read(self, deps, monkeypatch, *, setting_on):
        from models.screen_frame import ConversationScreenFrameSet

        fake_conversations_db, fake_users_db, _fake_redis_db = deps
        fake_conversations_db.get_conversation.return_value = _live_meeting(ConversationStatus.in_progress.value)
        fake_users_db.get_meeting_note_screenshots_enabled.return_value = setting_on
        fake_enforcement = MagicMock()
        fake_enforcement.build_frame_set_response.return_value = ConversationScreenFrameSet(revision=2)
        monkeypatch.setattr(screen_frames_mod, "enforcement", fake_enforcement)
        return screen_frames_mod.get_conversation_screenshots(CONVERSATION_ID, uid=UID)

    def test_owner_read_reports_the_trusted_window_fingerprint(self, _stub_admission_dependencies, monkeypatch):
        result = self._owner_read(_stub_admission_dependencies, monkeypatch, setting_on=True)
        assert result.trusted_selection_fingerprint == self.EXPECTED
        # The same arithmetic adjudication stamps, so a client can compare the two.
        live = _live_meeting(ConversationStatus.in_progress.value)
        assert (
            screen_frames_mod._validate_capture_window(
                live, [_candidate(captured_at=live["started_at"] + timedelta(seconds=60))]
            )
            == self.EXPECTED
        )

    def test_setting_off_still_reports_it_on_the_empty_set(self, _stub_admission_dependencies, monkeypatch):
        result = self._owner_read(_stub_admission_dependencies, monkeypatch, setting_on=False)
        assert result.revision == 0 and result.banner is None and result.strip == []
        assert result.trusted_selection_fingerprint == self.EXPECTED
        assert screen_frames_mod.EMPTY_FRAME_SET.trusted_selection_fingerprint is None  # shared constant untouched

    def test_no_trusted_window_is_null(self, _stub_admission_dependencies, monkeypatch):
        fake_conversations_db, _fake_users_db, _fake_redis_db = _stub_admission_dependencies
        fake_conversations_db.get_conversation.return_value = _conversation()
        monkeypatch.setattr(screen_frames_mod, "enforcement", MagicMock())
        screen_frames_mod.enforcement.build_frame_set_response.return_value = screen_frames_mod.EMPTY_FRAME_SET
        result = screen_frames_mod.get_conversation_screenshots(CONVERSATION_ID, uid=UID)
        assert result.trusted_selection_fingerprint is None

    def test_the_public_shared_route_never_carries_it(self, monkeypatch):
        from models.screen_frame import ConversationScreenFrameSet

        fake_redis_db = MagicMock()
        fake_redis_db.get_conversation_uid.return_value = UID
        monkeypatch.setattr(screen_frames_mod, "redis_db", fake_redis_db)
        fake_conversations_db = MagicMock()
        fake_conversations_db.get_conversation.return_value = _live_meeting(
            ConversationStatus.completed.value, visibility=ConversationVisibility.public.value
        )
        fake_conversations_db.is_soft_deleted.return_value = False
        fake_conversations_db.get_conversation_screenshot_sharing_enabled.return_value = True
        monkeypatch.setattr(screen_frames_mod, "conversations_db", fake_conversations_db)
        monkeypatch.setattr(screen_frames_mod, "screen_frames_db", fake_conversations_db)
        fake_users_db = MagicMock()
        fake_users_db.get_meeting_note_screenshots_enabled.return_value = True
        monkeypatch.setattr(screen_frames_mod, "users_db", fake_users_db)
        fake_enforcement = MagicMock()
        fake_enforcement.build_frame_set_response.return_value = ConversationScreenFrameSet(revision=1)
        monkeypatch.setattr(screen_frames_mod, "enforcement", fake_enforcement)

        result = screen_frames_mod.get_shared_conversation_screenshots(CONVERSATION_ID)

        assert result.revision == 1 and result.trusted_selection_fingerprint is None


class TestEmptyEvidencePass:
    """An empty candidate list means "evidence pass done, nothing to offer"."""

    def test_it_stamps_this_buckets_marker_without_judging_or_writing(self, _stub_admission_dependencies, monkeypatch):
        fake_conversations_db, _fake_users_db, _fake_redis_db = _stub_admission_dependencies
        live = _live_meeting(ConversationStatus.in_progress.value)
        fake_conversations_db.get_conversation.return_value = live
        judge, commit = MagicMock(), MagicMock()
        monkeypatch.setattr(screen_frames_mod, "judge_canonical", judge)
        monkeypatch.setattr(screen_frames_mod, "commit_approved", commit)
        enforce = MagicMock(return_value=(screen_frames_mod.EMPTY_FRAME_SET, False))
        monkeypatch.setattr(screen_frames_mod.enforcement, "enforce_and_persist", enforce)

        response = screen_frames_mod.adjudicate_screen_frames(_request(candidates=[]), uid=UID)

        assert response.outcome == "no_approved_frames"
        judge.assert_not_called()
        commit.assert_not_called()
        fake_conversations_db.mark_conversation_screen_frames_adjudicated.assert_called_once_with(
            UID,
            CONVERSATION_ID,
            selection_fingerprint="meeting-content-v1:1767225610000:1767225920000",
            bucket="test-screen-frames",
        )
        assert enforce.call_args.args[3] == []

    def test_it_keeps_the_admission_checks(self, _stub_admission_dependencies):
        _fake_conversations_db, fake_users_db, _fake_redis_db = _stub_admission_dependencies
        fake_users_db.get_meeting_note_screenshots_enabled.return_value = False

        with pytest.raises(HTTPException) as exc_info:
            screen_frames_mod.adjudicate_screen_frames(_request(candidates=[]), uid=UID)

        assert exc_info.value.status_code == 409

    def test_more_than_eight_candidates_is_still_rejected(self):
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            _request(candidates=[_candidate(client_frame_id=f"c{i}") for i in range(9)])


def test_the_adjudication_marker_is_stamped_only_after_frame_docs_persist(_stub_admission_dependencies, monkeypatch):
    """The notes finalizer proceeds on this marker; it must never precede readable frame docs."""
    fake_conversations_db, _fake_users_db, _fake_redis_db = _stub_admission_dependencies
    fake_conversations_db.get_conversation.return_value = _live_meeting(ConversationStatus.in_progress.value)
    order = []
    stamp = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
    fake_conversations_db.mark_conversation_screen_frames_adjudicated.side_effect = (
        lambda *a, **k: order.append("stamp") or stamp
    )

    def persist(*_args):
        order.append("persist")
        return screen_frames_mod.EMPTY_FRAME_SET, False

    monkeypatch.setattr(screen_frames_mod.enforcement, "enforce_and_persist", persist)

    response = screen_frames_mod.adjudicate_screen_frames(_request(candidates=[]), uid=UID)

    assert order == ["persist", "stamp"]
    assert response.frame_set.adjudicated_at == stamp
    assert response.frame_set.selection_fingerprint == "meeting-content-v1:1767225610000:1767225920000"
