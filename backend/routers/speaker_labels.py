from fastapi import APIRouter, Depends, HTTPException

from models.conversation import Conversation
from models.speaker_labels import RejectSpeakerRequest, VoiceMatchesResponse
from utils.other import endpoints as auth

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
    uid: str = Depends(auth.get_current_user_uid),
):
    raise HTTPException(status_code=501, detail='Speaker rejection is not implemented yet')


@router.get('/v1/users/people/{person_id}/voice-matches', response_model=VoiceMatchesResponse, tags=['v1'])
def get_person_voice_matches(person_id: str, uid: str = Depends(auth.get_current_user_uid)):
    return VoiceMatchesResponse()
