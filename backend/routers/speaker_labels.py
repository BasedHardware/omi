import logging
import re
import traceback
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from database import conversations as conversations_db
from database import voice_profiles as voice_profiles_db
from models.conversation import Conversation
from models.speaker_labels import RejectSpeakerRequest, VoiceMatchesResponse
from utils.conversations.factory import deserialize_conversation
from utils.log_sanitizer import hash_log_identifier
from utils.other import endpoints as auth
from utils.other.storage import delete_speech_profile_blob
from utils.speaker_voice_matches import find_person_voice_matches

logger = logging.getLogger(__name__)

router = APIRouter()


def _valid_document_id(value: str) -> bool:
    """Keep legacy IDs intact; reject only invalid Firestore document shapes.

    Storage limits: https://docs.cloud.google.com/firestore/quotas
    Imported Datastore numeric IDs use the documented __id[0-9]+__ form.
    """
    try:
        encoded = value.encode('utf-8')
    except UnicodeEncodeError:
        return False
    reserved = re.fullmatch(r'__.*__', value, flags=re.DOTALL) is not None
    imported_numeric = re.fullmatch(r'__id[0-9]+__', value) is not None
    return (
        bool(value)
        and len(encoded) <= 1500
        and '/' not in value
        and value not in ('.', '..')
        and (not reserved or imported_numeric)
    )


@router.post(
    '/v1/conversations/{conversation_id}/speakers/{speaker_id}/reject',
    response_model=Conversation,
    tags=['conversations'],
)
def reject_speaker_label(
    conversation_id: str,
    speaker_id: int,
    data: RejectSpeakerRequest,
    background_tasks: BackgroundTasks,
    uid: str = Depends(auth.get_current_user_uid),
):
    if not _valid_document_id(conversation_id):
        raise HTTPException(status_code=422, detail='invalid conversation_id')
    # Check the exact ID sent downstream; do not strip or normalize legacy IDs.
    if data.person_id is not None and not _valid_document_id(data.person_id):
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
        logger.warning(
            'speaker label reject lookup miss conv_hash=%s speaker=%s: %s\n%s',
            hash_log_identifier(conversation_id),
            speaker_id,
            type(error).__name__,
            ''.join(traceback.format_tb(error.__traceback__)),
        )
        raise HTTPException(status_code=404, detail='Conversation or speaker not found') from error
    except PermissionError as error:
        raise HTTPException(status_code=402, detail='A paid plan is required to access this conversation.') from error
    except ValueError as error:
        logger.warning(
            'speaker label reject conflict conv_hash=%s speaker=%s: %s\n%s',
            hash_log_identifier(conversation_id),
            speaker_id,
            type(error).__name__,
            ''.join(traceback.format_tb(error.__traceback__)),
        )
        raise HTTPException(status_code=409, detail='The speaker cannot be updated right now.') from error
    except Exception as error:
        # Keep stack locations without exception text, which can echo opaque IDs.
        logger.error(
            'speaker label reject failed conv_hash=%s speaker=%s uid=%s: %s\n%s',
            hash_log_identifier(conversation_id),
            speaker_id,
            uid,
            type(error).__name__,
            ''.join(traceback.format_tb(error.__traceback__)),
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
    person_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    if not _valid_document_id(person_id):
        raise HTTPException(status_code=422, detail='invalid person_id')
    try:
        return await find_person_voice_matches(uid, person_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail='Person not found') from error
    except Exception as error:
        logger.error(
            'person voice-matches failed person_hash=%s uid=%s: %s\n%s',
            hash_log_identifier(person_id),
            uid,
            type(error).__name__,
            ''.join(traceback.format_tb(error.__traceback__)),
        )
        raise HTTPException(status_code=500, detail='Failed to load voice matches') from error
