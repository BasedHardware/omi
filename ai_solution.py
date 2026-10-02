```python
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, status
from fastapi.params import Path, Query
from pydantic import constr
from ..schemas.base import BaseResponse
from ..schemas.speaker_labels import VoiceMatch, SpeakerLabel
from ..common import catch_exception
from ..types.conversations importSpeakerLabel
from ..types.people import Person

router = APIRouter()

@router.get(
    "/v1/users/people/{person_id}/voice-matches",
    response_model=BaseResponse[List[VoiceMatch]],
)
@catch_exception
async def get_voice_matches(
    person_id: constr(min_length=1) = Path(...),
) -> Dict[str, Any]:
    from ..dal.people import get_voice_matches

    validate_positive_integer(person_id)
    result = get_voice_matches(person_id)
    return {"result": result}

@router.post(
    "/v1/conversations/{conversation_id}/speakers/{speaker_id}/reject",
    response_model=BaseResponse[SpeakerLabel],
)
@catch_exception
async def reject_speaker(
    conversation_id: constr(min_length=1) = Path(...),
    speaker_id: constr(min_length=1) = Path(...),
) -> Dict[str, Any]:
    from ..dal.conversations import reject_speaker

    validate_uuid(conversation_id)
    validate_positive_integer(speaker_id)
    result = reject_speaker(conversation_id, speaker_id)
    return {"result": result}

def validate_uuid(suuid: str) -> None:
    from uuid import UUID

    try:
        UUID(suuid)
    except ValueError:
        raise ValueError("Invalid UUID")

def validate_positive_integer(snum: str) -> None:
    try:
        num = int(snum)
    except ValueError:
        raise ValueError("Invalid integer")
    if num <= 0:
        raise ValueError("ID must be positive")
```