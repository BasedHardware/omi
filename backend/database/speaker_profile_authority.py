"""Publication-time source fences for slow person voice teaching."""

from typing import Any, Optional, Sequence

from utils.speaker_learning_policy import authorized_teaching_segments


def person_teaching_authorized(
    transaction: Any,
    user_ref: Any,
    person_id: str,
    uid: str,
    conversation_id: str,
    segment_ids: Sequence[str],
    generation: Optional[int],
) -> bool:
    # Deferred codec import breaks users -> this module -> conversations -> storage -> users.
    from database.conversations import decode_transcript_segments_verified, decode_manual_speaker_assignments

    raw = user_ref.collection('conversations').document(conversation_id).get(transaction=transaction).to_dict()
    # A conversation locked or discarded after extraction left the retry coordinator's
    # scope; its speech must not publish either.
    if not raw or raw.get('deleted') or raw.get('discarded') or raw.get('is_locked') or not segment_ids:
        return False
    receipt = decode_manual_speaker_assignments(
        uid, raw.get('manual_speaker_assignments'), bool(raw.get('manual_speaker_assignments_compressed'))
    )
    # The attempt must have observed a receipt no newer than the current one. A later
    # edit to another voice bumps the generation without touching this label, so the
    # per-segment authority below, not generation equality, decides. Malformed or
    # legacy generation values deny publication instead of raising mid-transaction.
    current_generation = receipt.get('generation', 0)
    if (
        generation is None
        or isinstance(generation, bool)
        or not isinstance(current_generation, int)
        or isinstance(current_generation, bool)
    ):
        return False
    if current_generation < generation:
        return False
    # An undecodable transcript blob denies publication (returns False) rather than
    # raising inside the person-write transaction, so the caller's cleanup path runs.
    try:
        segments = decode_transcript_segments_verified(
            uid, raw.get('transcript_segments', []), bool(raw.get('transcript_segments_compressed'))
        )
    except Exception:
        return False
    if receipt.get('segments') or receipt.get('speakers'):
        segments = authorized_teaching_segments(
            {'transcript_segments': segments, 'manual_speaker_assignments': receipt}, person_id
        )
    # Receipt-less historical labels remain supported, but cannot teach after correction.
    allowed = {s.get('id') for s in segments if s.get('person_id') == person_id and not s.get('is_user')}
    return set(segment_ids).issubset(allowed)
