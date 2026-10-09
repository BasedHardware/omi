"""Minimal authenticated release-channel record for the default-off cohort."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from config.dream_agent import mode
from database._client import get_firestore_client
from utils.other import endpoints as auth

router = APIRouter()


class ReleaseChannel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    release_channel: Literal['testflight', 'app_store', 'dev']
    app_build: int | None = Field(default=None, ge=1, strict=True)


@router.put('/v1/users/release-channel', status_code=204)
def record_channel(body: ReleaseChannel, uid: str = Depends(auth.get_current_user_uid)):
    if mode() == 'off':
        raise HTTPException(status_code=404, detail='dream_disabled')
    # The channel/build are client assertions, scoped to this caller's own user doc.
    # Always replace the optional build so an old qualifying build cannot linger.
    get_firestore_client().collection('users').document(uid).set(
        {'dream_release_channel': body.release_channel, 'dream_app_build': body.app_build}, merge=True
    )
