"""``excluded_speakers`` projects the manual receipt's live exclusions, never the receipt."""

from datetime import datetime, timezone

from models.conversation import Conversation
from models.speaker_exclusion import receipt_excluded_speakers


def _row(**extra):
    row = dict(
        id='c',
        created_at=datetime.now(timezone.utc),
        started_at=None,
        finished_at=None,
        structured={},
    )
    row.update(extra)
    return row


def _speaker_entry(generation, rejection_kind=None, person_id=None, is_user=False, segment_only=False):
    entry = dict(generation=generation, person_id=person_id, is_user=is_user)
    if segment_only:
        entry['segment_only'] = True
    if rejection_kind:
        entry['rejection'] = {'kind': rejection_kind}
    return entry


def test_no_receipt_projects_null():
    conversation = Conversation(**_row())
    assert conversation.excluded_speakers is None
    assert 'excluded_speakers' in conversation.model_dump(mode='json')
    assert conversation.model_dump(mode='json')['excluded_speakers'] is None


def test_whole_voice_not_a_person_projects():
    receipt = {
        'generation': 3,
        'speakers': {'4': _speaker_entry(3, rejection_kind='not_a_person')},
    }
    conversation = Conversation(**_row(manual_speaker_assignments=receipt))
    assert conversation.excluded_speakers == [4]
    dumped = conversation.model_dump(mode='json')
    assert dumped['excluded_speakers'] == [4]
    # The receipt itself never serializes.
    assert 'manual_speaker_assignments' not in dumped
    assert 'manual_speaker_assignments' not in conversation.model_dump()


def test_range_only_positive_keeps_the_exclusion():
    # A segment_only positive (start/end range assign) never unseats the
    # whole-voice rejection; the voice stays excluded.
    receipt = {
        'generation': 5,
        'speakers': {'4': _speaker_entry(2, rejection_kind='not_a_person')},
        'segments': {'seg-1': dict(_speaker_entry(5, person_id='p1'), speaker_id=4, segment_only=True)},
    }
    conversation = Conversation(**_row(manual_speaker_assignments=receipt))
    assert conversation.excluded_speakers == [4]


def test_selected_segment_superseder_retires_the_exclusion():
    # A selected-segment bulk assign (segment entry WITHOUT segment_only) is a
    # whole-voice superseder even though only its segments project a label.
    receipt = {
        'generation': 5,
        'speakers': {'4': _speaker_entry(2, rejection_kind='not_a_person')},
        'segments': {'seg-1': dict(_speaker_entry(5, person_id='p1'), speaker_id=4)},
    }
    conversation = Conversation(**_row(manual_speaker_assignments=receipt))
    assert conversation.excluded_speakers is None


def test_newer_whole_voice_positive_retires_the_exclusion():
    receipt = {
        'generation': 5,
        'speakers': {'4': _speaker_entry(5, person_id='p1')},
    }
    assert receipt_excluded_speakers(receipt) == []
    assert Conversation(**_row(manual_speaker_assignments=receipt)).excluded_speakers is None


def test_newer_not_me_supersedes_not_a_person():
    # The marker rule: only a still-winning not_a_person keeps the exclusion;
    # a newer not_me rejection replaces it.
    receipt = {
        'generation': 5,
        'speakers': {
            '4': _speaker_entry(5, rejection_kind='not_me'),
        },
    }
    assert receipt_excluded_speakers(receipt) == []
    assert Conversation(**_row(manual_speaker_assignments=receipt)).excluded_speakers is None


def test_malformed_receipt_sections_do_not_crash():
    receipt = {'speakers': {'x': 'not-a-dict'}, 'segments': {'seg': 7}, 'generation': 'oops'}
    assert receipt_excluded_speakers(receipt) == []
    assert Conversation(**_row(manual_speaker_assignments=receipt)).excluded_speakers is None


def test_explicit_excluded_speakers_roundtrips():
    # A caller-provided projection (cache round-trip) is honored as-is.
    conversation = Conversation(**_row(excluded_speakers=[9]))
    assert conversation.excluded_speakers == [9]
    public = conversation.model_dump(mode='json')
    assert Conversation(**public).excluded_speakers == [9]
