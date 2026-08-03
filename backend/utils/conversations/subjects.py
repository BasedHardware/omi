from typing import List, Optional, Set, Tuple

from database.entities import USER_ENTITY_ID, person_entity_id
from models.memories import SubjectAttribution
from models.transcript_segment import TranscriptSegment


def infer_subject_from_segments(
    segments: List[TranscriptSegment],
) -> Tuple[Optional[str], SubjectAttribution]:
    if not segments:
        return None, SubjectAttribution.unknown

    user_count = sum(1 for segment in segments if getattr(segment, 'is_user', False))
    non_user_segments = [segment for segment in segments if not getattr(segment, 'is_user', False)]
    if user_count and not non_user_segments:
        return USER_ENTITY_ID, SubjectAttribution.user

    person_ids: Set[str] = set()
    attributed_count = 0
    for segment in non_user_segments:
        pid = getattr(segment, 'person_id', None)
        if pid:
            person_ids.add(pid)
            attributed_count += 1
    sole_person_id = next(iter(person_ids)) if len(person_ids) == 1 else None

    if non_user_segments and not user_count:
        if sole_person_id:
            return person_entity_id(sole_person_id), SubjectAttribution.third_party
        return None, SubjectAttribution.third_party

    # Both sides speak. That is *every* 1:1 conversation by construction — a message thread, a
    # phone call — so bailing to `unknown` here left an identified counterpart inert no matter how
    # confidently the client attributed them, which made a populated `person_id` do nothing at all.
    # Narrow carve-out: when the entire non-user side is ONE identified person, that person is the
    # subject.
    #
    # The guard is deliberately stricter than the no-user branch above: every non-user segment must
    # carry a person_id. A single unattributed non-user speaker means this is a multi-party
    # conversation, whose memories must not be pinned on the one person we happen to recognize.
    if sole_person_id and attributed_count == len(non_user_segments):
        return person_entity_id(sole_person_id), SubjectAttribution.third_party
    return None, SubjectAttribution.unknown
