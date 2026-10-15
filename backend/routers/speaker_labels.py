from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from database import conversations as conversations_db
from models.conversation import Conversation
from models.speaker_labels import RejectSpeakerRequest, VoiceMatchesResponse
from utils.conversations.factory import deserialize_conversation
from utils.ignored_voice_markers import record_exclusion_markers, retire_exclusion_markers
from utils.other import endpoints as auth
from utils.other.storage import delete_speech_profile_blob
from utils.speaker_voice_matches import find_person_voice_matches

router = APIRouter()


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
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PermissionError as error:
        raise HTTPException(status_code=402, detail='A paid plan is required to access this conversation.') from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if data.kind == 'not_a_person':
        # Live-sheet exclusions, card answers, and this reject route write the
        # same ignored-voice marker through the shared helpers: the marker only
        # powers Settings > Ignored Voices and restoration, and a persistence
        # failure there must not surface a committed rejection as failed
        # (fail-open with shared fallback telemetry).
        record_exclusion_markers(uid, raw['id'], raw, resolved, speaker_id=speaker_id)
    else:
        # Every other committed answer — not_me / not_person included — must
        # reconcile the ignored-voice marker: a newer non-not_a_person decision
        # supersedes an earlier media exclusion, and the shared helper decides
        # which markers still win (range-only entries keep theirs restorable).
        retire_exclusion_markers(uid, raw['id'], raw, resolved, speaker_id=speaker_id)
    for path in removed:
        background_tasks.add_task(delete_speech_profile_blob, path)
    return deserialize_conversation(raw)


@router.get('/v1/users/people/{person_id}/voice-matches', response_model=VoiceMatchesResponse, tags=['v1'])
async def get_person_voice_matches(person_id: str, uid: str = Depends(auth.get_current_user_uid)):
    try:
        return await find_person_voice_matches(uid, person_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail='Person not found') from error
