"""Tests for utils/screen_frames/writer.py (contract §5).

The writer is the only code path allowed to write BUCKET_SCREEN_FRAMES.
These tests cover the three fail-closed cases the task specifically calls
out — expired approval, wrong-digest approval, replayed jti — plus the
happy path, all with storage and Redis mocked out (no real GCS/Redis).

write_screen_frame() verifies approvals through the module-level cached
signer (utils.screen_frames.approval.get_signer()), not an injectable
parameter, so these tests mint tokens the same way the router would: via
the env-driven HMAC signer, with the cache reset around each test so the
env var actually takes effect.
"""

import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from models.screen_frame import ScreenFrameJudgement
from utils.screen_frames import approval as approval_mod
from utils.screen_frames import writer as writer_mod
from utils.screen_frames.approval import build_approval_claims, mint_approval
from utils.screen_frames.writer import ScreenFrameWriteError, write_screen_frame

UID = "user-1"
CONTENT = b"canonical-jpeg-bytes"
THUMB = b"thumbnail-jpeg-bytes"


def _approved_judgement() -> ScreenFrameJudgement:
    return ScreenFrameJudgement(
        outcome="approved_clean",
        reject_reason=None,
        caption="a code editor",
        labels=["code"],
        source_badge="code",
        banner_suitability=0.6,
    )


def _valid_token(*, canonical_sha256=None, **claim_overrides):
    digest = canonical_sha256 or hashlib.sha256(CONTENT).hexdigest()
    claims = build_approval_claims(
        uid=UID,
        purpose="meeting_note_v1",
        subject_id="conv-1",
        canonical_sha256=digest,
        model="gemini-2.5-flash-lite",
        policy_version="meeting_note_privacy.v1",
        prompt_version="meeting_note_frame_judge.v1",
        retention="with_subject",
        judgement=_approved_judgement(),
    )
    if claim_overrides:
        claims = claims.model_copy(update=claim_overrides)
    return mint_approval(claims), claims


@pytest.fixture(autouse=True)
def _stub_boundaries(monkeypatch):
    """Stub storage (no real GCS) and redis_db (no real Redis), and point
    the signer at a fixed HMAC secret via env so mint_approval() here and
    verify_approval() inside write_screen_frame() agree.
    """
    fake_storage = MagicMock()
    fake_redis = MagicMock()
    fake_redis.try_consume_screen_frame_jti.return_value = True
    monkeypatch.setattr(writer_mod, "storage", fake_storage)
    monkeypatch.setattr(writer_mod, "redis_db", fake_redis)

    monkeypatch.delenv("SCREEN_FRAME_KMS_KEY", raising=False)
    monkeypatch.setenv("SCREEN_FRAME_SIGNING_SECRET", "test-secret")
    approval_mod.reset_signer_cache()
    yield fake_storage, fake_redis
    approval_mod.reset_signer_cache()


class TestHappyPath:
    def test_writes_and_returns_frame(self, _stub_boundaries):
        fake_storage, fake_redis = _stub_boundaries
        token, claims = _valid_token()

        out = write_screen_frame(token, jpeg_bytes=CONTENT, thumbnail_jpeg_bytes=THUMB)

        assert out.uid == UID
        assert out.conversation_id == "conv-1"
        fake_storage.upload_screen_frame_blobs.assert_called_once()
        called_args = fake_storage.upload_screen_frame_blobs.call_args.args
        assert called_args[0] == UID
        assert called_args[1] == "conv-1"
        assert called_args[3] == CONTENT
        assert called_args[4] == THUMB
        fake_redis.try_consume_screen_frame_jti.assert_called_once_with(str(claims.jti))


class TestExpiredApprovalRejected:
    def test_expired_approval_is_rejected_and_nothing_is_written(self, _stub_boundaries):
        fake_storage, fake_redis = _stub_boundaries
        now = datetime.now(timezone.utc)
        token, _claims = _valid_token(issued_at=now - timedelta(minutes=20), expires_at=now - timedelta(minutes=10))

        with pytest.raises(ScreenFrameWriteError):
            write_screen_frame(token, jpeg_bytes=CONTENT, thumbnail_jpeg_bytes=THUMB)

        fake_storage.upload_screen_frame_blobs.assert_not_called()
        fake_redis.try_consume_screen_frame_jti.assert_not_called()


class TestWrongDigestRejected:
    def test_bytes_not_matching_claimed_digest_is_rejected(self, _stub_boundaries):
        fake_storage, fake_redis = _stub_boundaries
        # Approval claims a digest for different bytes than what the writer
        # is actually handed — must be refused even though the approval
        # itself verifies (signature, expiry) fine.
        token, _claims = _valid_token(canonical_sha256="0" * 64)

        with pytest.raises(ScreenFrameWriteError):
            write_screen_frame(token, jpeg_bytes=CONTENT, thumbnail_jpeg_bytes=THUMB)

        fake_storage.upload_screen_frame_blobs.assert_not_called()
        # jti consumption happens AFTER the digest check, so a wrong-digest
        # approval must not burn the jti either — it might still be usable
        # with the bytes it actually names.
        fake_redis.try_consume_screen_frame_jti.assert_not_called()


class TestReplayedJtiRejected:
    def test_second_use_of_the_same_approval_is_rejected(self, _stub_boundaries):
        fake_storage, fake_redis = _stub_boundaries
        token, claims = _valid_token()

        # First use succeeds.
        write_screen_frame(token, jpeg_bytes=CONTENT, thumbnail_jpeg_bytes=THUMB)
        assert fake_storage.upload_screen_frame_blobs.call_count == 1

        # Simulate the jti already being consumed (this is what the real
        # Redis SETNX would report on a replay).
        fake_redis.try_consume_screen_frame_jti.return_value = False

        with pytest.raises(ScreenFrameWriteError):
            write_screen_frame(token, jpeg_bytes=CONTENT, thumbnail_jpeg_bytes=THUMB)

        # Still just the one upload from the first, legitimate use.
        assert fake_storage.upload_screen_frame_blobs.call_count == 1
