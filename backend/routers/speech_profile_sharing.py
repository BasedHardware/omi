from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from models.speech_profile_share import (
    RevokeSpeechProfileRequest,
    ShareSpeechProfileRequest,
    SharedProfileResponse,
)
from utils.other import get_current_user_uid
from utils.speech_profile_sharing import (
    create_share,
    delete_share,
    get_shares_for_recipient,
    get_user_by_email,
    load_embedding_from_gcs,
    publish_share_event,
    share_exists,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v3/speech-profile", tags=["speech-profile"])


@router.post(
    "/share",
    response_model=dict,
    summary="Share your speech profile with another Omi user",
)
async def share_speech_profile(
    body: ShareSpeechProfileRequest,
    uid: str = Depends(get_current_user_uid),
) -> dict:
    """Share the calling user's speech profile with a recipient.

    The recipient is identified by ``recipient_user_id`` or ``recipient_email``.
    A custom ``display_name`` labels the speaker in the recipient's conversations.
    """
    # Resolve recipient UID
    if body.recipient_user_id:
        recipient_uid = body.recipient_user_id
    else:
        user = get_user_by_email(body.recipient_email)  # type: ignore[arg-type]
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No Omi user found with email '{body.recipient_email}'",
            )
        recipient_uid = user["uid"]

    if recipient_uid == uid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot share your speech profile with yourself",
        )

    # Caller must have a speech profile to share
    if load_embedding_from_gcs(uid) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="You must record a speech profile before sharing it",
        )

    if share_exists(uid, recipient_uid):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already shared your speech profile with this user",
        )

    share_id = create_share(
        sharer_uid=uid,
        recipient_uid=recipient_uid,
        display_name=body.display_name,
    )
    publish_share_event(recipient_uid, "share", uid, body.display_name)
    return {"success": True, "share_id": share_id}


@router.post(
    "/revoke",
    response_model=dict,
    summary="Revoke a previously shared speech profile",
)
async def revoke_speech_profile(
    body: RevokeSpeechProfileRequest,
    uid: str = Depends(get_current_user_uid),
) -> dict:
    """Revoke the calling user's speech profile share from a specific recipient."""
    deleted = delete_share(sharer_uid=uid, recipient_uid=body.recipient_user_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active share found for this recipient",
        )
    publish_share_event(body.recipient_user_id, "revoke", uid, "")
    return {"success": True}


@router.get(
    "/shared",
    response_model=list[SharedProfileResponse],
    summary="List speech profiles shared with me",
)
async def list_shared_profiles(
    uid: str = Depends(get_current_user_uid),
) -> list[SharedProfileResponse]:
    """Return all speech profiles that other users have shared with the caller."""
    shares = get_shares_for_recipient(uid)
    return [
        SharedProfileResponse(
            sharer_uid=s["sharer_uid"],
            display_name=s["display_name"],
            created_at=s["created_at"],
        )
        for s in shares
    ]
