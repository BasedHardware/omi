"""Recording-wide speaker naming, available without episode cohort admission."""

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException

from config.recording_speakers import enabled, RecordingLimitExceeded
from config.app_channel import APP_CHANNEL_HEADER
from config.episodes import client_channel_admitted, episodes_enabled_for
from models.recording_speakers import (
    RecordingSpeakerRequest,
    RecordingSpeakerResponse,
    RecordingTranscriptResponse,
    RecordingSpeakerConflict,
    RecordingSpeakerLimit,
)
from utils import recording_speakers
from utils.other import endpoints as auth

router = APIRouter(tags=['conversations'])


def edit(uid, conversation_id, body, background_tasks, *, episode_id=None):
    if not enabled():
        raise HTTPException(409, detail='recording_speaker_rename_disabled')
    try:
        return recording_speakers.assign(uid, conversation_id, body, background_tasks, episode_id=episode_id)
    except RecordingLimitExceeded as error:
        raise HTTPException(413, detail='recording_speaker_limit_exceeded') from error
    except LookupError as error:
        raise HTTPException(404, detail=str(error)) from error
    except PermissionError as error:
        raise HTTPException(402, detail='A paid plan is required to access this conversation.') from error
    except ValueError as error:
        raise HTTPException(
            409, detail={'code': 'stale_speaker', 'message': 'Speaker changed. Select the lines again.'}
        ) from error


@router.get(
    '/v1/conversations/{conversation_id}/recording-speakers',
    response_model=RecordingTranscriptResponse,
    responses={413: {'model': RecordingSpeakerLimit, 'description': 'Recording exceeds the member or segment limit'}},
)
def get_recording_speakers(
    conversation_id: str,
    uid: str = Depends(auth.get_current_user_uid),
    channel: str | None = Header(None, alias=APP_CHANNEL_HEADER),
):
    try:
        result = recording_speakers.transcript(uid, conversation_id)
        if not (episodes_enabled_for(uid) and client_channel_admitted(channel)):
            result['episode_id'] = None
        return result
    except RecordingLimitExceeded as error:
        raise HTTPException(413, detail='recording_speaker_limit_exceeded') from error
    except LookupError as error:
        raise HTTPException(404, detail='Conversation not found') from error
    except PermissionError as error:
        raise HTTPException(402, detail='A paid plan is required to access this conversation.') from error


@router.patch(
    '/v1/conversations/{conversation_id}/recording-speakers',
    response_model=RecordingSpeakerResponse,
    responses={
        409: {'model': RecordingSpeakerConflict, 'description': 'Recording rename disabled or speaker selection stale'},
        413: {'model': RecordingSpeakerLimit, 'description': 'Recording exceeds the member or segment limit'},
    },
)
def assign_recording_speakers(
    conversation_id: str,
    body: RecordingSpeakerRequest,
    background_tasks: BackgroundTasks,
    uid: str = Depends(auth.get_current_user_uid),
):
    return edit(uid, conversation_id, body, background_tasks)
