import logging
import re
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path

from database import conversations as conversations_db
from database import voice_profiles as voice_profiles_db
from models.conversation import Conversation
from models.speaker_labels import RejectSpeakerRequest, VoiceMatchesResponse
from utils.conversations.factory import deserialize_conversation
from utils.other import endpoints as auth
from utils.other.storage import delete_speech_profile_blob
from utils.speaker_voice_matches import find_person_voice_matches

logger = logging.getLogger(__name__)

router = APIRouter()

# Firestore document ids used as path parameters: a caller-controlled value with
# a path separator or traversal sequence would be read as a subcollection path by
# document(). Restrict to a plain doc-id charset and bound the length.
_DOC_ID_PATTERN = r'^[A-Za-z0-9_-]{1,128}$'


@router.post(
    '/v1/conversations/{conversation_id}/speakers/{speaker_id}/reject',
    response_model=Conversation,
    tags=['conversations'],
)
def reject_speaker_label(
    conversation_id: Annotated[str, Path(pattern=_DOC_ID_PATTERN)],
    speaker_id: Annotated[int, Path(ge=0, le=1_000_000)],
    data: RejectSpeakerRequest,
    background_tasks: BackgroundTasks,
    uid: str = Depends(auth.get_current_user_uid),
):
    # The request body's person_id flows into the same document() sink as the
    # path param; validate the exact value passed downstream — a padded or
    # separator-carrying id is rejected outright.
    if data.person_id is not None and not re.fullmatch(_DOC_ID_PATTERN, data.person_id):
        raise HTTPException(status_code=400, detail='invalid person_id')
    try:
        raw, resolved, removed, _before = conversations_db.assign_conversation_speaker(
            uid,
            conversation_id,
            person_id=None,
            is_user=False,
            speaker_id=speaker_id,
            segment_ids=data.segment_ids,
            use_for_speech_training=False,
            rejection={'kind': data.kind, 'person_id': data.person_id},
        )
    except LookupError as error:
        # Same rule as the 409 below: log the real detail, return a static one —
        # a future raise site must not be able to regress this reflection.
        logger.warning('speaker label reject lookup miss conv=%s speaker=%s: %s', conversation_id, speaker_id, error)
        raise HTTPException(status_code=404, detail='Conversation or speaker not found') from error
    except PermissionError as error:
        raise HTTPException(status_code=402, detail='A paid plan is required to access this conversation.') from error
    except ValueError as error:
        # A conflict detail is user-actionable, but log the real message and return
        # a generic one so an internal detail never leaks through the boundary.
        logger.warning('speaker label reject conflict conv=%s speaker=%s: %s', conversation_id, speaker_id, error)
        raise HTTPException(status_code=409, detail='The speaker cannot be updated right now.') from error
    except Exception as error:
        # Unexpected (Firestore, network, bug): log full context internally,
        # surface a sanitized 500 to the client.
        logger.error(
            'speaker label reject failed conv=%s speaker=%s uid=%s: %s',
            conversation_id,
            speaker_id,
            uid,
            type(error).__name__,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail='Failed to update the speaker') from error
    if data.kind == 'not_a_person':
        resolved_ids = set(resolved)
        affected = {
            int(segment['speaker_id'])
            for segment in raw.get('transcript_segments') or []
            if segment.get('id') in resolved_ids and isinstance(segment.get('speaker_id'), int)
        } or {speaker_id}
        generation = (raw.get('manual_speaker_assignments') or {}).get('generation')
        for affected_speaker in sorted(affected):
            voice_profiles_db.record_ignored_voice(
                uid, raw['id'], affected_speaker, datetime.now(timezone.utc), assignment_generation=generation
            )
    for path in removed:
        background_tasks.add_task(delete_speech_profile_blob, path)
    return deserialize_conversation(raw)


@router.get('/v1/users/people/{person_id}/voice-matches', response_model=VoiceMatchesResponse, tags=['v1'])
async def get_person_voice_matches(
    person_id: Annotated[str, Path(pattern=_DOC_ID_PATTERN)],
    uid: str = Depends(auth.get_current_user_uid),
):
    try:
        return await find_person_voice_matches(uid, person_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail='Person not found') from error
    except Exception as error:
        logger.error(
            'person voice-matches failed person=%s uid=%s: %s',
            person_id,
            uid,
            type(error).__name__,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail='Failed to load voice matches') from error
