import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from database import conversations as conversations_db
from database import voice_profiles as voice_profiles_db
from models.conversation import Conversation
from models.speaker_labels import RejectSpeakerRequest, VoiceMatchesResponse
from utils.conversations.factory import deserialize_conversation
from utils.log_sanitizer import sanitize
from utils.other import endpoints as auth
from utils.other.storage import delete_speech_profile_blob
from utils.speaker_voice_matches import find_person_voice_matches

logger = logging.getLogger(__name__)

router = APIRouter()


def _clean_id(id_val: str | None, field_name: str = "id") -> str:
    cleaned = (id_val or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail=f"Valid {field_name} is required")
    return cleaned


@router.post(
    "/v1/conversations/{conversation_id}/speakers/{speaker_id}/reject",
    response_model=Conversation,
    tags=["conversations"],
)
def reject_speaker_label(
    conversation_id: str,
    speaker_id: int,
    data: RejectSpeakerRequest,
    background_tasks: BackgroundTasks,
    uid: str = Depends(auth.get_current_user_uid),
):
    clean_conv_id = _clean_id(conversation_id, "conversation_id")
    if speaker_id < 0:
        raise HTTPException(
            status_code=400, detail="Valid speaker_id must be non-negative"
        )

    try:
        raw, resolved, removed, _before = conversations_db.assign_conversation_speaker(
            uid,
            clean_conv_id,
            person_id=None,
            is_user=False,
            speaker_id=speaker_id,
            segment_ids=data.segment_ids,
            use_for_speech_training=False,
            rejection={"kind": data.kind, "person_id": data.person_id},
        )
    except HTTPException:
        raise
    except LookupError as error:
        logger.warning(
            "Speaker label rejection target not found: %s", sanitize(str(error))
        )
        raise HTTPException(
            status_code=404, detail="Conversation or speaker not found"
        ) from error
    except PermissionError as error:
        raise HTTPException(
            status_code=402,
            detail="A paid plan is required to access this conversation.",
        ) from error
    except (ValueError,) as error:
        logger.warning(
            "Speaker label rejection validation error: %s", sanitize(str(error))
        )
        raise HTTPException(
            status_code=409, detail="Invalid speaker rejection request"
        ) from error
    except Exception as error:
        logger.error(
            "Unhandled speaker label rejection error: %s", sanitize(str(error))
        )
        raise HTTPException(
            status_code=500, detail="Unable to process speaker label rejection"
        ) from error

    try:
        if data.kind == "not_a_person":
            resolved_ids = set(resolved)
            affected = {
                int(segment["speaker_id"])
                for segment in raw.get("transcript_segments") or []
                if segment.get("id") in resolved_ids
                and isinstance(segment.get("speaker_id"), int)
            } or {speaker_id}
            generation = (raw.get("manual_speaker_assignments") or {}).get("generation")
            for affected_speaker in sorted(affected):
                voice_profiles_db.record_ignored_voice(
                    uid,
                    raw["id"],
                    affected_speaker,
                    datetime.now(timezone.utc),
                    assignment_generation=generation,
                )
        for path in removed:
            background_tasks.add_task(delete_speech_profile_blob, path)
        return deserialize_conversation(raw)
    except HTTPException:
        raise
    except Exception as error:
        logger.error(
            "Unhandled post-rejection processing error: %s", sanitize(str(error))
        )
        raise HTTPException(
            status_code=500, detail="Unable to process speaker label rejection"
        ) from error


@router.get(
    "/v1/users/people/{person_id}/voice-matches",
    response_model=VoiceMatchesResponse,
    tags=["v1"],
)
async def get_person_voice_matches(
    person_id: str, uid: str = Depends(auth.get_current_user_uid)
):
    clean_person_id = _clean_id(person_id, "person_id")
    try:
        return await find_person_voice_matches(uid, clean_person_id)
    except HTTPException:
        raise
    except LookupError as error:
        logger.warning(
            "Person voice matches target not found: %s", sanitize(str(error))
        )
        raise HTTPException(status_code=404, detail="Person not found") from error
    except Exception as error:
        logger.error("Unhandled voice matches query error: %s", sanitize(str(error)))
        raise HTTPException(
            status_code=500, detail="Unable to retrieve voice matches"
        ) from error
