from fastapi import HTTPException, status
import firebase_admin
from firebase_admin import auth, firestore
from firebase_admin.exceptions import FirebaseError
from typing import Optional
import logging

from backend.utils.posthog import _safe_emit_posthog_event
from backend.services.referrals import claim_referral_trial

logger = logging.getLogger(__name__)

class ReferralClaimError(Exception):
    pass

def _get_user_safe(uid: str) -> Optional[auth.UserRecord]:
    try:
        return auth.get_user(uid)
    except FirebaseError as e:
        logger.error(f"Firebase auth lookup failed for UID {uid}: {str(e)}")
        raise ReferralClaimError("User authentication metadata temporarily unavailable")

def _claim_referral_safe(uid: str, referral_code: str) -> bool:
    try:
        return claim_referral_trial(uid, referral_code)
    except FirebaseError as e:
        logger.error(f"Referral claim failed for UID {uid}: {str(e)}")
        raise ReferralClaimError("Referral claim service temporarily unavailable")

async def claim_referral_endpoint(uid: str, referral_code: str):
    if not referral_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Referral code cannot be empty"
        )

    try:
        user = _get_user_safe(uid)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        success = _claim_referral_safe(uid, referral_code)
        if success:
            _safe_emit_posthog_event("referral_claimed", {"uid": uid})
            return {"status": "success"}
        return {"status": "already_claimed"}

    except ReferralClaimError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error in referral claim: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )