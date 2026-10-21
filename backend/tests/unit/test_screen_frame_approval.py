"""Tests for utils/screen_frames/approval.py (contract §5).

Covers: an approval cannot be minted for anything but approved_clean, the
HMAC signer round-trips and rejects tampering/expiry, and env-driven signer
selection (HMAC vs KMS) dispatches correctly without needing a real KMS key.
"""

from datetime import datetime, timedelta, timezone

import pytest

from models.screen_frame import ScreenFrameJudgement
from utils.screen_frames import approval as approval_mod
from utils.screen_frames.approval import (
    ApprovalSignatureError,
    HmacSigner,
    KmsSigner,
    build_approval_claims,
    mint_approval,
    verify_approval,
)

UID = "user-1"


def _approved_judgement(**overrides) -> ScreenFrameJudgement:
    base = dict(
        outcome="approved_clean",
        reject_reason=None,
        caption="a code editor",
        labels=["code"],
        source_badge="code",
        banner_suitability=0.6,
    )
    base.update(overrides)
    return ScreenFrameJudgement(**base)


def _rejected_judgement(**overrides) -> ScreenFrameJudgement:
    base = dict(
        outcome="rejected",
        reject_reason="credentials",
        caption="a login form",
        labels=[],
        source_badge=None,
        banner_suitability=0.0,
    )
    base.update(overrides)
    return ScreenFrameJudgement(**base)


class TestApprovalOnlyForApprovedClean:
    def test_cannot_mint_claims_for_rejected_outcome(self):
        with pytest.raises(ValueError):
            build_approval_claims(
                uid=UID,
                purpose="meeting_note_v1",
                subject_id="conv-1",
                canonical_sha256="a" * 64,
                model="gemini-2.5-flash-lite",
                policy_version="meeting_note_privacy.v1",
                prompt_version="meeting_note_frame_judge.v1",
                retention="with_subject",
                judgement=_rejected_judgement(),
            )

    def test_can_mint_claims_for_approved_clean(self):
        claims = build_approval_claims(
            uid=UID,
            purpose="meeting_note_v1",
            subject_id="conv-1",
            canonical_sha256="a" * 64,
            model="gemini-2.5-flash-lite",
            policy_version="meeting_note_privacy.v1",
            prompt_version="meeting_note_frame_judge.v1",
            retention="with_subject",
            judgement=_approved_judgement(),
        )
        assert claims.decision == "approved_clean"
        assert claims.uid == UID
        assert claims.expires_at - claims.issued_at <= timedelta(seconds=approval_mod.APPROVAL_MAX_TTL_SECONDS)


class TestHmacSignerRoundTrip:
    def _claims(self, **overrides):
        base = build_approval_claims(
            uid=UID,
            purpose="meeting_note_v1",
            subject_id="conv-1",
            canonical_sha256="b" * 64,
            model="gemini-2.5-flash-lite",
            policy_version="meeting_note_privacy.v1",
            prompt_version="meeting_note_frame_judge.v1",
            retention="with_subject",
            judgement=_approved_judgement(),
        )
        if overrides:
            base = base.model_copy(update=overrides)
        return base

    def test_valid_token_round_trips(self):
        signer = HmacSigner("test-secret")
        claims = self._claims()
        token = mint_approval(claims, signer=signer)
        verified = verify_approval(token, signer=signer)
        assert verified.jti == claims.jti
        assert verified.canonical_sha256 == claims.canonical_sha256

    def test_tampered_signature_is_rejected(self):
        signer = HmacSigner("test-secret")
        token = mint_approval(self._claims(), signer=signer)
        header_b64, claims_b64, sig_b64 = token.split(".")
        tampered = f"{header_b64}.{claims_b64}.{sig_b64[:-4]}AAAA"
        with pytest.raises(ApprovalSignatureError):
            verify_approval(tampered, signer=signer)

    def test_wrong_key_is_rejected(self):
        token = mint_approval(self._claims(), signer=HmacSigner("secret-a"))
        with pytest.raises(ApprovalSignatureError):
            verify_approval(token, signer=HmacSigner("secret-b"))

    def test_expired_token_is_rejected(self):
        signer = HmacSigner("test-secret")
        now = datetime.now(timezone.utc)
        expired_claims = self._claims(issued_at=now - timedelta(minutes=20), expires_at=now - timedelta(minutes=10))
        token = mint_approval(expired_claims, signer=signer)
        with pytest.raises(ApprovalSignatureError):
            verify_approval(token, signer=signer)

    def test_malformed_token_is_rejected(self):
        with pytest.raises(ApprovalSignatureError):
            verify_approval("not-a-valid-token", signer=HmacSigner("test-secret"))

    def test_empty_secret_refuses_to_construct(self):
        with pytest.raises(ApprovalSignatureError):
            HmacSigner("")


class TestSignerDispatch:
    def test_uses_hmac_when_kms_key_not_set(self, monkeypatch):
        approval_mod.reset_signer_cache()
        monkeypatch.delenv("SCREEN_FRAME_KMS_KEY", raising=False)
        monkeypatch.setenv("SCREEN_FRAME_SIGNING_SECRET", "env-secret")
        signer = approval_mod.get_signer()
        assert isinstance(signer, HmacSigner)
        approval_mod.reset_signer_cache()

    def test_uses_kms_when_kms_key_set(self, monkeypatch):
        approval_mod.reset_signer_cache()
        monkeypatch.setenv("SCREEN_FRAME_KMS_KEY", "projects/p/locations/l/keyRings/r/cryptoKeys/k/cryptoKeyVersions/1")
        signer = approval_mod.get_signer()
        assert isinstance(signer, KmsSigner)
        approval_mod.reset_signer_cache()

    def test_signer_is_cached_across_calls(self, monkeypatch):
        approval_mod.reset_signer_cache()
        monkeypatch.delenv("SCREEN_FRAME_KMS_KEY", raising=False)
        monkeypatch.setenv("SCREEN_FRAME_SIGNING_SECRET", "env-secret")
        first = approval_mod.get_signer()
        second = approval_mod.get_signer()
        assert first is second
        approval_mod.reset_signer_cache()
