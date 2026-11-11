"""Which stored voiceprints are trustworthy enough to identify a speaker."""

from typing import Any, Mapping, Optional

from utils.speakers import auto_enroll


def usable_person_voiceprint(
    person: Mapping[str, Any],
    *,
    uid: Optional[str] = None,
    auto_enroll_allowed: Mapping[str, Any] | bool = False,
) -> Optional[list]:
    """The person's embedding, or None when it cannot be trusted.
    Only people with v3+ speech samples qualify (pre-v3 models carry stale embeddings, #6238).
    """
    if person.get(auto_enroll.REVOKED_FIELD):
        return None
    enrolled = auto_enroll.usable(uid, person, auto_enroll_allowed) if uid else None
    if enrolled is not None:
        return enrolled
    return auto_enroll.legacy_voiceprint(person)
