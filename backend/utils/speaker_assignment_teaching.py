"""Background voice-learning orchestration for manual speaker assignments.

After a successful assignment the router hands scheduling here so the route
stays slim: retire superseded sample blobs, queue person voice-learning for
labeled people, and queue an owner confirmation for "that's me" labels. All
policy stays in the underlying sample functions; this module only decides
what a successful assignment may schedule.
"""

from typing import Any, List, Mapping, Optional, Sequence

from utils.manual_speaker_assignments import teaching_segment_ids
from utils.other.storage import delete_speech_profile_blob
from utils.speaker_identification import extract_speaker_samples
from utils.speaker_tag_prompts.service import store_owner_voice_sample


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
            extract_speaker_samples,
            uid=uid,
            person_id=person_id,
            conversation_id=conversation_id,
            segment_ids=teaching_segment_ids(raw.get('transcript_segments') or [], resolved),
        )
    elif is_user:
        background_tasks.add_task(
            store_owner_voice_sample,
            uid=uid,
            conversation_id=conversation_id,
            segment_ids=list(resolved),
        )
