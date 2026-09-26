from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

import firebase_admin.auth
from database import referrals as referrals_db
from routers import referrals
from utils.referrals import ReferralCodeError


def test_claim_referral_rejects_empty_code():
    request = referrals.ReferralClaimRequest(code='')
    with pytest.raises(HTTPException) as exc_info:
        referrals.claim_referral(request, uid='test-uid')
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == 'Referral code cannot be blank'


def test_claim_referral_rejects_whitespace_code():
    request = referrals.ReferralClaimRequest(code='   ')
    with pytest.raises(HTTPException) as exc_info:
        referrals.claim_referral(request, uid='test-uid')
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == 'Referral code cannot be blank'


def test_claim_referral_unknown_code_returns_404(monkeypatch):
    request = referrals.ReferralClaimRequest(code='invalid-code')

    def broken_code_lookup(code):
        raise ReferralCodeError('invalid_referral_code')

    monkeypatch.setattr(referrals, 'referrer_uid_from_code', broken_code_lookup)

    with pytest.raises(HTTPException) as exc_info:
        referrals.claim_referral(request, uid='test-uid')
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == 'Referral link not found'


def test_claim_referral_auth_lookup_failure_returns_503(monkeypatch):
    request = referrals.ReferralClaimRequest(code='valid-code')
    monkeypatch.setattr(referrals, 'referrer_uid_from_code', lambda code: 'referrer-uid')

    def broken_get_user(uid):
        raise RuntimeError('Firebase auth timeout')

    monkeypatch.setattr(firebase_admin.auth, 'get_user', broken_get_user)

    with pytest.raises(HTTPException) as exc_info:
        referrals.claim_referral(request, uid='test-uid')
    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == 'User authentication metadata temporarily unavailable'


def test_claim_referral_storage_failure_returns_503(monkeypatch):
    request = referrals.ReferralClaimRequest(code='valid-code')
    monkeypatch.setattr(referrals, 'referrer_uid_from_code', lambda code: 'referrer-uid')

    fake_user = SimpleNamespace(user_metadata=SimpleNamespace(creation_timestamp=1700000000000))
    monkeypatch.setattr(firebase_admin.auth, 'get_user', lambda uid: fake_user)

    def broken_claim(*args, **kwargs):
        raise RuntimeError('Firestore lock timeout')

    monkeypatch.setattr(referrals, 'claim_referral_trial', broken_claim)

    with pytest.raises(HTTPException) as exc_info:
        referrals.claim_referral(request, uid='test-uid')
    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == 'Referral claim service temporarily unavailable'


def test_claim_referral_decouples_telemetry_failure(monkeypatch):
    request = referrals.ReferralClaimRequest(code='valid-code')
    monkeypatch.setattr(referrals, 'referrer_uid_from_code', lambda code: 'referrer-uid')

    fake_user = SimpleNamespace(user_metadata=SimpleNamespace(creation_timestamp=1700000000000))
    monkeypatch.setattr(firebase_admin.auth, 'get_user', lambda uid: fake_user)
    monkeypatch.setattr(referrals, 'claim_referral_trial', lambda *args, **kwargs: (True, 'granted'))

    def broken_telemetry(*args, **kwargs):
        raise ConnectionError('PostHog timeout')

    monkeypatch.setattr(referrals, 'emit_posthog_event', broken_telemetry)

    response = referrals.claim_referral(request, uid='test-uid')
    assert response.claimed is True
    assert response.trial_days == 30