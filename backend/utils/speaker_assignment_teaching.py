"""Background voice-learning orchestration for manual speaker assignments.

After a successful assignment the router hands scheduling here so the route
stays slim: retire superseded sample blobs and run the durable learning-job
coordinator for the work the assignment transaction committed. All policy
stays in the underlying functions; this module only decides what a
successful assignment may schedule.
"""

from typing import Any, List, Mapping, Optional, Sequence

from database import conversations as conversations_db
from utils.manual_speaker_assignments import teaching_segment_ids
from utils.other.storage import delete_speech_profile_blob
from utils.speaker_learning_jobs import run_authorized_owner_learning, run_authorized_person_learning


def commit_manual_assignment(
    uid: str,
    conversation_id: str,
    *,
    person_id: Optional[str],
    is_user: bool,
    segment_ids: Optional[List[str]] = None,
    speaker_id: Optional[int] = None,
    segment_index: Optional[int] = None,
    use_for_speech_training: bool = True,
    rejection: Optional[dict] = None,
    time_range: Optional[tuple[float, float]] = None,
    background_tasks: Any = None,
):
    """The assignment transaction plus the background work it earned, one call."""
    raw, resolved, removed, before = conversations_db.assign_conversation_speaker(
        uid,
        conversation_id,
        person_id=person_id,
        is_user=is_user,
        segment_ids=segment_ids,
        speaker_id=speaker_id,
        segment_index=segment_index,
        use_for_speech_training=use_for_speech_training,
        rejection=rejection,
        time_range=time_range,
    )
    if background_tasks is not None:
        schedule_assignment_teaching(
            background_tasks,
            uid,
            raw.get('id') or conversation_id,
            raw,
            resolved,
            removed,
            person_id=person_id,
            is_user=is_user,
            use_for_speech_training=use_for_speech_training,
        )
    return raw, resolved, removed, before


def schedule_assignment_teaching(
    background_tasks: Any,
    uid: str,
    conversation_id: str,
    raw: Mapping[str, Any],
    resolved: List[str],
    removed: Sequence[str],
    *,
    person_id: Optional[str],
    is_user: bool,
    use_for_speech_training: bool,
) -> None:
    """Queue every follow-up sample task one committed manual assignment earned."""
    for path in removed:
        background_tasks.add_task(delete_speech_profile_blob, path)
    if not use_for_speech_training:
        return
    if person_id:
        background_tasks.add_task(
            run_authorized_person_learning,
            uid=uid,
            person_id=person_id,
            conversation_id=conversation_id,
            segment_ids=teaching_segment_ids(raw.get('transcript_segments') or [], resolved),
        )
    elif is_user:
        background_tasks.add_task(
            run_authorized_owner_learning,
            uid=uid,
            conversation_id=conversation_id,
            segment_ids=list(resolved),
        )
