import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from backend.routers.referrals import (
    claim_referral_endpoint,
    ReferralClaimError,
    _get_user_safe,
    _claim_referral_safe
)
from firebase_admin.exceptions import FirebaseError

@pytest.mark.asyncio
async def test_empty_referral_code():
    with pytest.raises(HTTPException) as exc_info:
        await claim_referral_endpoint("test-uid", "")
    assert exc_info.value.status_code == 400

@patch('backend.routers.referrals.auth.get_user')
def test_auth_lookup_failure(mock_get_user):
    mock_get_user.side_effect = FirebaseError("Auth failed")
    with pytest.raises(HTTPException) as exc_info:
        _get_user_safe("test-uid")
    assert exc_info.value.status_code == 503

@patch('backend.routers.referrals.claim_referral_trial')
def test_claim_referral_failure(mock_claim):
    mock_claim.side_effect = FirebaseError("Claim failed")
    with pytest.raises(ReferralClaimError):
        _claim_referral_safe("test-uid", "test-code")

@patch('backend.routers.referrals._safe_emit_posthog_event')
@patch('backend.routers.referrals._claim_referral_safe')
@patch('backend.routers.referrals._get_user_safe')
async def test_telemetry_decoupling(
    mock_get_user,
    mock_claim,
    mock_emit
):
    mock_get_user.return_value = MagicMock()
    mock_claim.return_value = True
    mock_emit.side_effect = Exception("Telemetry failed")

    result = await claim_referral_endpoint("test-uid", "test-code")
    assert result == {"status": "success"}
    mock_emit.assert_called_once()