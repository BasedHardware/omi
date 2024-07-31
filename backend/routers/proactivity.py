from typing import List

from fastapi import APIRouter, Depends

from models.transcript_segment import TranscriptSegment
from utils import auth

router = APIRouter()


# ConversationCoachResponse
@router.post('/coach', response_model=dict, tags=['memories'])
def coach_conversation(transcript: List[TranscriptSegment], uid: str = Depends(auth.get_current_user_uid)):
    # return {'advise': advise_on_current_conversation(transcript.transcript, transcript.language_code)}
    return {'advise': 'advise'}
