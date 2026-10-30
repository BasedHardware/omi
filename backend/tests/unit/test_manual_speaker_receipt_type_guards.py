"""A stored manual-speaker receipt is user data: a wrong-typed nested section must not crash the
conversation / voice-match readers.

`manual_rejected_speakers`, `manual_owner_reserved`, and `apply_manual_assignments` previously called
`.items()` / `.values()` / `.get()` on whatever the receipt's `speakers` / `segments` fields held, so
a receipt carrying a list (from a corrupt or imported conversation doc) raised `AttributeError` and
500'd `GET /v1/conversations` and the voice-match route.
"""

from utils.manual_speaker_assignments import (
    apply_manual_assignments,
    manual_owner_reserved,
    manual_rejected_speakers,
)

SEGMENTS = [{'id': 'a', 'speaker_id': 0, 'start': 0.0, 'end': 1.0, 'text': 'hi'}]


def test_apply_manual_assignments_tolerates_non_mapping_sections():
    assert apply_manual_assignments(SEGMENTS, {'speakers': ['x'], 'segments': ['y']}) == SEGMENTS
    assert apply_manual_assignments(SEGMENTS, {'speakers': 'nope'}) == SEGMENTS


def test_apply_manual_assignments_tolerates_non_dict_entries():
    assert apply_manual_assignments(SEGMENTS, {'speakers': {'0': 'x'}}) == SEGMENTS
    assert apply_manual_assignments(SEGMENTS, {'segments': {'a': 'x'}}) == SEGMENTS
    assert apply_manual_assignments(SEGMENTS, {'speakers': {'0': None}}) == SEGMENTS


def test_manual_rejected_speakers_tolerates_non_mapping_sections():
    assert manual_rejected_speakers({'speakers': ['x']}) == {}
    assert manual_rejected_speakers({'segments': ['y']}) == {}
    assert manual_rejected_speakers(None) == {}


def test_manual_owner_reserved_tolerates_non_mapping_sections():
    assert manual_owner_reserved({'speakers': ['x'], 'segments': ['y']}) is False
    assert manual_owner_reserved(None) is False


def test_valid_receipts_still_apply():
    applied = apply_manual_assignments(SEGMENTS, {'speakers': {'0': {'person_id': 'person-1', 'generation': 2}}})
    assert applied[0]['person_id'] == 'person-1'

    rejected = manual_rejected_speakers(
        {'segments': {'seg-1': {'speaker_id': 0, 'generation': 1, 'rejection': {'kind': 'user'}}}}
    )
    assert 0 in rejected

    assert manual_owner_reserved({'speakers': {'0': {'is_user': True}}}) is True
