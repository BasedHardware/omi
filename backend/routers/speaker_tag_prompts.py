"""Speaker tag prompts ("Is this you?" / "Who is this?") and voice-profile preferences."""

import base64
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import Response

from database import conversations as conversations_db
from database import voice_profiles as voice_profiles_db
from models.speaker_tag_prompts import (
    SpeakerTagPromptAnswerRequest,
    SpeakerTagPromptAnswerResponse,
    SpeakerTagPromptClip,
    SpeakerTagPromptsResponse,
    SpeakerTagPromptsShownRequest,
    SpeakerTagPromptsShownResponse,
    VoiceProfileSettings,
    VoiceProfileSettingsUpdate,
)
from utils.log_sanitizer import sanitize
from utils.other import endpoints as auth
from utils.speaker_tag_prompts import service
from utils.speaker_tag_prompts.clips import (
    CLIP_SAMPLE_RATE,
    MAX_CLIP_REQUEST_SECONDS,
    conversation_clip_pcm,
    pcm_to_wav,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/v1/speaker-tag-prompts",
    tags=["speaker-tag-prompts"],
    response_model=SpeakerTagPromptsResponse,
)
def get_speaker_tag_prompts(uid: str = Depends(auth.get_current_user_uid)):
    """Today's small set of voices to confirm, from conversations in the last 48 hours."""
    try:
        return service.get_prompts(uid)
    except Exception as exc:
        logger.error(
            f"Failed to get speaker tag prompts for user {uid}: {sanitize(str(exc))}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to retrieve speaker tag prompts") from exc


@router.post(
    "/v1/speaker-tag-prompts/shown",
    tags=["speaker-tag-prompts"],
    response_model=SpeakerTagPromptsShownResponse,
)
def mark_speaker_tag_prompts_shown(data: SpeakerTagPromptsShownRequest, uid: str = Depends(auth.get_current_user_uid)):
    """The client displayed a set; starts the once-a-day cooldown."""
    try:
        return SpeakerTagPromptsShownResponse(first_time=service.mark_shown(uid, len(data.prompt_ids)))
    except Exception as exc:
        logger.error(
            f"Failed to mark speaker tag prompts shown for user {uid}: {sanitize(str(exc))}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to mark speaker tag prompts shown") from exc


@router.post("/v1/speaker-tag-prompts/dismiss", tags=["speaker-tag-prompts"], status_code=204)
def dismiss_speaker_tag_prompts(uid: str = Depends(auth.get_current_user_uid)):
    """The user closed a set without answering; repeated dismissals slow the prompts down."""
    try:
        service.mark_dismissed(uid)
        return Response(status_code=204)
    except Exception as exc:
        logger.error(
            f"Failed to dismiss speaker tag prompts for user {uid}: {sanitize(str(exc))}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to dismiss speaker tag prompts") from exc


@router.post(
    "/v1/speaker-tag-prompts/answer",
    tags=["speaker-tag-prompts"],
    response_model=SpeakerTagPromptAnswerResponse,
)
def answer_speaker_tag_prompt(
    data: SpeakerTagPromptAnswerRequest,
    background_tasks: BackgroundTasks,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "speaker_tag_prompts:answer")),
):
    try:
        return service.apply_answer(uid, data, schedule=background_tasks.add_task)
    except service.TagPromptInvalid as error:
        logger.warning(f"Invalid speaker tag prompt answer for user {uid}: {sanitize(str(error))}")
        raise HTTPException(status_code=400, detail=sanitize(str(error))) from error
    except service.TagPromptForbidden as error:
        logger.warning(f"Forbidden speaker tag prompt access for user {uid}: {sanitize(str(error))}")
        raise HTTPException(status_code=402, detail=sanitize(str(error))) from error
    except LookupError as error:
        logger.warning(f"Speaker tag prompt lookup failed for user {uid}: {sanitize(str(error))}")
        raise HTTPException(status_code=404, detail=sanitize(str(error))) from error
    except PermissionError as error:
        logger.warning(f"Paid plan required for user {uid}: {sanitize(str(error))}")
        raise HTTPException(
            status_code=402,
            detail="A paid plan is required to access this conversation.",
        ) from error
    except ValueError as error:
        logger.warning(f"Conflict answering speaker tag prompt for user {uid}: {sanitize(str(error))}")
        raise HTTPException(status_code=409, detail=sanitize(str(error))) from error
    except Exception as exc:
        logger.error(
            f"Unexpected error answering speaker tag prompt for user {uid}: {sanitize(str(exc))}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get(
    "/v1/speaker-tag-prompts/clip",
    tags=["speaker-tag-prompts"],
    response_model=SpeakerTagPromptClip,
)
def get_speaker_tag_prompt_clip(
    conversation_id: str = Query(min_length=1, max_length=128),
    start: float = Query(ge=0),
    end: float = Query(gt=0),
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "speaker_tag_prompts:clip")),
):
    """A short clip of the user's own stored conversation audio (base64 WAV, at most 12 s)."""
    if end <= start or end - start > MAX_CLIP_REQUEST_SECONDS:
        raise HTTPException(status_code=400, detail="Clip must be at most 12 seconds")
    conversation = conversations_db.get_conversation(uid, conversation_id)
    if not conversation or conversation.get("deleted"):
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation.get("is_locked"):
        raise HTTPException(
            status_code=402,
            detail="A paid plan is required to access this conversation.",
        )
    try:
        pcm = conversation_clip_pcm(uid, conversation, start, end)
        if not pcm:
            raise HTTPException(
                status_code=404,
                detail="No audio stored for this part of the conversation",
            )
        return SpeakerTagPromptClip(
            audio_base64=base64.b64encode(pcm_to_wav(pcm)).decode("ascii"),
            duration_seconds=round(len(pcm) / (2 * CLIP_SAMPLE_RATE), 3),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f"Failed to fetch speaker tag prompt clip for user {uid}: {sanitize(str(exc))}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to fetch speaker tag prompt clip") from exc


@router.get("/v1/users/voice-profile-settings", tags=["v1"], response_model=VoiceProfileSettings)
def get_voice_profile_settings(uid: str = Depends(auth.get_current_user_uid)):
    try:
        return VoiceProfileSettings(**voice_profiles_db.get_voice_profile_settings(uid))
    except Exception as exc:
        logger.error(
            f"Failed to fetch voice profile settings for user {uid}: {sanitize(str(exc))}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to fetch voice profile settings") from exc


@router.patch("/v1/users/voice-profile-settings", tags=["v1"], response_model=VoiceProfileSettings)
def update_voice_profile_settings(data: VoiceProfileSettingsUpdate, uid: str = Depends(auth.get_current_user_uid)):
    try:
        updates = data.model_dump(exclude_none=True, exclude={"source"})
        return VoiceProfileSettings(**service.update_settings(uid, updates, data.source))
    except Exception as exc:
        logger.error(
            f"Failed to update voice profile settings for user {uid}: {sanitize(str(exc))}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to update voice profile settings") from exc
