"""Speaker assignment utilities.

Extracted from transcribe.py for testability.
"""

from typing import Dict, List, Optional, Tuple
from models.transcript_segment import TranscriptSegment


def process_speaker_assigned_segments(
    transcript_segments: List[TranscriptSegment],
    segment_person_assignment_map: Dict[str, str],
    speaker_to_person_map: Dict[int, Tuple[str, str]],
) -> None:
    """Apply speaker assignments to transcript segments.

    For each segment without is_user or person_id:
    1. First check segment_person_assignment_map by segment.id
    2. Fall back to speaker_to_person_map by segment.speaker_id
    3. Handle special 'user' person_id by setting is_user=True

    Args:
        transcript_segments: List of segments to process (modified in place)
        segment_person_assignment_map: Map of segment_id -> person_id
        speaker_to_person_map: Map of speaker_id -> (person_id, person_name)
    """
    for segment in transcript_segments:
        if segment.is_user or segment.person_id:
            continue

        person_id = None
        if segment.id in segment_person_assignment_map:
            person_id = segment_person_assignment_map[segment.id]
        elif segment.speaker_id in speaker_to_person_map:
            person_id = speaker_to_person_map[segment.speaker_id][0]

        if person_id:
            if person_id == 'user':
                segment.is_user = True
                segment.person_id = None
            else:
                segment.is_user = False
                segment.person_id = person_id


def update_speaker_assignment_maps(
    speaker_id: int,
    person_id: str,
    person_name: str,
    segment_ids: List[str],
    speaker_to_person_map: Dict[int, Tuple[str, str]],
    segment_person_assignment_map: Dict[str, str],
) -> bool:
    """Update speaker assignment maps from speaker_assigned event.

    Always updates maps regardless of can_assign status.

    Args:
        speaker_id: The speaker ID being assigned
        person_id: The person ID to assign
        person_name: The person's name
        segment_ids: List of segment IDs to assign
        speaker_to_person_map: Map to update (speaker_id -> (person_id, person_name))
        segment_person_assignment_map: Map to update (segment_id -> person_id)

    Returns:
        True if maps were updated, False if required fields were missing
    """
    if speaker_id is None or person_id is None or person_name is None:
        return False

    speaker_to_person_map[speaker_id] = (person_id, person_name)
    for sid in segment_ids:
        segment_person_assignment_map[sid] = person_id

    return True


def should_update_speaker_to_person_map(speaker_id: Optional[int]) -> bool:
    """Check if speaker_to_person_map should be updated for text detection.

    Only update when diarization is active (speaker_id > 0).
    When diarization is off, speaker_id defaults to 0, and we don't want to
    auto-assign all segments with speaker_id 0 to one person.

    Args:
        speaker_id: The speaker ID from the segment

    Returns:
        True if map should be updated, False otherwise
    """
    return speaker_id is not None and speaker_id > 0
