"""Authenticated caller's identity (Firebase Auth profile).

Wires database.auth.get_user_from_uid to a read endpoint. Distinct from the Firestore
app profile under /v1/users/me/*: these fields come from Firebase Auth (verified email and
photo). Phone number and account-state flags are deliberately not exposed. Small self-contained
router; the natural host routers/auth.py is OAuth-callback heavy, so a new file keeps this
import-clean and contained.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database.auth import get_user_from_uid
from utils.other import endpoints as auth

router = APIRouter()


class IdentityResponse(BaseModel):
    """The authenticated caller's Firebase Auth identity."""

    uid: str
    email: Optional[str] = None
    email_verified: Optional[bool] = None
    display_name: Optional[str] = None
    photo_url: Optional[str] = None


@router.get('/v1/auth/me', response_model=IdentityResponse, tags=['auth'])
def get_my_identity(uid: str = Depends(auth.get_current_user_uid)):
    """Return the authenticated caller's Firebase Auth identity profile.

    A plain def endpoint: get_user_from_uid is a blocking Firebase call and FastAPI runs
    def handlers in a threadpool. Returns 404 when the uid has no Firebase user (deleted
    or unknown). response_model pins the returned fields to a minimal identity set (uid, email,
    email_verified, display_name, photo_url) so phone number, account-state flags, or any other
    Firebase profile field cannot leak.
    """
    user = get_user_from_uid(uid)
    if not user:
        raise HTTPException(status_code=404, detail="User identity not found")
    return user
