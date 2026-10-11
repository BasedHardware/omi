"""Speaker tag prompts ("Was this you?" / "Who is this?") and voice-profile preferences."""

import base64
import hashlib
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import Response

from database import owner_confirmation as owner_confirmation_db
from database import conversations as conversations_db
from database import voice_profiles as voice_profiles_db
from models.speaker_tag_prompts import (
    IgnoredVoicesResponse,
    SpeakerTagPromptAnswerRequest,
    SpeakerTagPromptAnswerResponse,
    SpeakerTagPromptClip,
    SpeakerTagPromptsResponse,
    SpeakerTagPromptsShownRequest,
    SpeakerTagPromptsShownResponse,
    VoiceProfileSettings,
    VoiceProfileSettingsUpdate,
)
from utils.other import endpoints as auth
from utils.speaker_tag_prompts import service
from utils.speaker_tag_prompts.clips import (
    CLIP_SAMPLE_RATE,
    MAX_CLIP_REQUEST_SECONDS,
    conversation_clip_pcm,
    pcm_to_wav,
)
from utils.speaker_tag_prompts.coverage import prompt_window_covered
from utils.speaker_tag_prompts.owner_confirmation import StaleOwnerConfirmation, validate_binding
from utils.observability.speaker_tag_prompts import OWNER_CONFIRMATION_EVENTS

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get('/v1/speaker-tag-prompts', tags=['speaker-tag-prompts'], response_model=SpeakerTagPromptsResponse)
def get_speaker_tag_prompts(
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, 'speaker_tag_prompts:list')),
    owner_excerpt: bool = Query(default=False),
):
    """Today's small set of voices to confirm, from conversations in the last 48 hours."""
    return service.get_prompts(uid, owner_excerpt=owner_excerpt)


@router.post(
    '/v1/speaker-tag-prompts/shown', tags=['speaker-tag-prompts'], response_model=SpeakerTagPromptsShownResponse
)
def mark_speaker_tag_prompts_shown(data: SpeakerTagPromptsShownRequest, uid: str = Depends(auth.get_current_user_uid)):
    """The client displayed a set; starts the once-a-day cooldown."""
    return SpeakerTagPromptsShownResponse(first_time=service.mark_shown(uid, data.prompt_ids, set_shown=data.set_shown))


@router.post('/v1/speaker-tag-prompts/dismiss', tags=['speaker-tag-prompts'], status_code=204)
def dismiss_speaker_tag_prompts(uid: str = Depends(auth.get_current_user_uid)):
    """The user closed a set without answering; repeated dismissals slow the prompts down."""
    service.mark_dismissed(uid)
    return Response(status_code=204)


@router.post(
    '/v1/speaker-tag-prompts/answer', tags=['speaker-tag-prompts'], response_model=SpeakerTagPromptAnswerResponse
)
def answer_speaker_tag_prompt(
    data: SpeakerTagPromptAnswerRequest,
    background_tasks: BackgroundTasks,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, 'speaker_tag_prompts:answer')),
):
    try:
        return service.apply_answer(uid, data, schedule=background_tasks.add_task)
    except service.TagPromptInvalid as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PermissionError as error:
        raise HTTPException(status_code=402, detail='A paid plan is required to access this conversation.') from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get('/v1/speaker-tag-prompts/clip', tags=['speaker-tag-prompts'], response_model=SpeakerTagPromptClip)
def get_speaker_tag_prompt_clip(
    conversation_id: str = Query(min_length=1, max_length=128),
    start: float = Query(ge=0),
    end: float = Query(gt=0),
    prompt_id: str | None = Query(default=None, max_length=64),
    evidence_id: str | None = Query(default=None, max_length=64),
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, 'speaker_tag_prompts:clip')),
):
    """A short clip of the user's own stored conversation audio (base64 WAV, at most 12 s)."""
    if end <= start or end - start > MAX_CLIP_REQUEST_SECONDS:
        raise HTTPException(status_code=400, detail='Clip must be at most 12 seconds')
    conversation = conversations_db.get_conversation(uid, conversation_id)
    if not conversation or conversation.get('deleted'):
        raise HTTPException(status_code=404, detail='Conversation not found')
    if conversation.get('is_locked'):
        raise HTTPException(status_code=402, detail='A paid plan is required to access this conversation.')
    binding = None
    if prompt_id is not None or evidence_id is not None:
        try:
            binding = validate_binding(conversation, prompt_id or '', evidence_id or '')
            if start != binding['clip_start'] or end != binding['clip_end']:
                raise StaleOwnerConfirmation('Owner excerpt bounds changed')
        except StaleOwnerConfirmation as error:
            OWNER_CONFIRMATION_EVENTS.labels(event='stale_rejected').inc()
            raise HTTPException(status_code=409, detail=str(error)) from error
    if not prompt_window_covered(conversation, start, end):
        raise HTTPException(status_code=404, detail='No audio stored for this part of the conversation')
    pcm = conversation_clip_pcm(uid, conversation, start, end)
    if not pcm:
        raise HTTPException(status_code=404, detail='No audio stored for this part of the conversation')
    expected = service.clip_expected_text(conversation, start, end)
    pcm = service.verified_clip_pcm(uid, conversation, start, end, expected, pcm)
    if not pcm:
        raise HTTPException(status_code=404, detail='No matching speech stored for this part of the conversation')
    if binding is not None:
        try:
            owner_confirmation_db.record(
                uid, conversation_id, 'played', binding, pcm_sha256=hashlib.sha256(pcm).hexdigest()
            )
        except StaleOwnerConfirmation as error:
            OWNER_CONFIRMATION_EVENTS.labels(event='stale_rejected').inc()
            raise HTTPException(status_code=409, detail=str(error)) from error
    return SpeakerTagPromptClip(
        audio_base64=base64.b64encode(pcm_to_wav(pcm)).decode('ascii'),
        duration_seconds=round(len(pcm) / (2 * CLIP_SAMPLE_RATE), 3),
    )


@router.get(
    '/v1/speaker-tag-prompts/ignored-voices', tags=['speaker-tag-prompts'], response_model=IgnoredVoicesResponse
)
def get_ignored_voices(uid: str = Depends(auth.get_current_user_uid)):
    """Voices the user marked Not a Person, newest first."""
    return service.list_ignored_voices(uid)


@router.delete(
    '/v1/speaker-tag-prompts/ignored-voices/{conversation_id}/{speaker_id}',
    tags=['speaker-tag-prompts'],
    status_code=204,
)
def restore_ignored_voice(conversation_id: str, speaker_id: int, uid: str = Depends(auth.get_current_user_uid)):
    """Undo Not a Person: Omi may ask about this voice again."""
    if not service.restore_ignored_voice(uid, conversation_id, speaker_id):
        raise HTTPException(status_code=404, detail='Voice not found')
    return Response(status_code=204)


@router.get('/v1/users/voice-profile-settings', tags=['v1'], response_model=VoiceProfileSettings)
def get_voice_profile_settings(uid: str = Depends(auth.get_current_user_uid)):
    return VoiceProfileSettings(**voice_profiles_db.get_voice_profile_settings(uid))


@router.patch('/v1/users/voice-profile-settings', tags=['v1'], response_model=VoiceProfileSettings)
def update_voice_profile_settings(data: VoiceProfileSettingsUpdate, uid: str = Depends(auth.get_current_user_uid)):
    updates = data.model_dump(exclude_none=True, exclude={'source'})
    return VoiceProfileSettings(**service.update_settings(uid, updates, data.source))
