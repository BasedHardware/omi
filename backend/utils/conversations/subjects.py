from typing import List, Optional, Set, Tuple

from database.entities import USER_ENTITY_ID, person_entity_id
from models.memories import SubjectAttribution
from models.transcript_segment import TranscriptSegment
from utils.conversations.owner_attribution import OwnerAttributionEvidence, may_attribute_to_owner


def infer_subject_from_segments(
    segments: List[TranscriptSegment],
) -> Tuple[Optional[str], SubjectAttribution]:
    if not segments:
        return None, SubjectAttribution.unknown

    user_count = sum(1 for segment in segments if getattr(segment, 'is_user', False))
    non_user_segments = [segment for segment in segments if not getattr(segment, 'is_user', False)]
    if user_count and not non_user_segments:
        if may_attribute_to_owner(OwnerAttributionEvidence.from_segments(segments)):
            return USER_ENTITY_ID, SubjectAttribution.user
        return None, SubjectAttribution.unknown
    if non_user_segments and not user_count:
        person_ids: Set[str] = set()
        for segment in non_user_segments:
            pid = segment.person_id
            if pid:
                person_ids.add(pid)
        if len(person_ids) == 1:
            only_id = next(iter(person_ids))
            return person_entity_id(only_id), SubjectAttribution.third_party
        return None, SubjectAttribution.third_party
    return None, SubjectAttribution.unknown
