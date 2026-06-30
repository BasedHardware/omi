from typing import List, Optional, Tuple

from database.entities import USER_ENTITY_ID, person_entity_id
from models.memories import SubjectAttribution


def infer_subject_from_segments(segments: List) -> Tuple[Optional[str], SubjectAttribution]:
    if not segments:
        return None, SubjectAttribution.unknown

    user_count = sum(1 for segment in segments if getattr(segment, 'is_user', False))
    non_user_segments = [segment for segment in segments if not getattr(segment, 'is_user', False)]
    if user_count and not non_user_segments:
        return USER_ENTITY_ID, SubjectAttribution.user
    if non_user_segments and not user_count:
        person_ids = {segment.person_id for segment in non_user_segments if getattr(segment, 'person_id', None)}
        if len(person_ids) == 1:
            return person_entity_id(next(iter(person_ids))), SubjectAttribution.third_party
        return None, SubjectAttribution.third_party
    return None, SubjectAttribution.unknown
