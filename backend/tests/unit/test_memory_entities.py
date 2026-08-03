from types import SimpleNamespace

from database import entities, memory_ledger
from models.memories import SubjectAttribution
from utils.conversations.subjects import infer_subject_from_segments


def test_infer_subject_from_user_only_segments():
    subject_id, attribution = infer_subject_from_segments([SimpleNamespace(is_user=True, person_id=None)])

    assert subject_id == entities.USER_ENTITY_ID
    assert attribution == SubjectAttribution.user


def test_infer_subject_from_non_user_person_segments():
    subject_id, attribution = infer_subject_from_segments([SimpleNamespace(is_user=False, person_id='p1')])

    assert subject_id == entities.person_entity_id('p1')
    assert attribution == SubjectAttribution.third_party


def test_infer_subject_attributes_a_one_to_one_thread_to_the_identified_counterpart():
    """A 1:1 thread — the user plus exactly one identified person — resolves to that person.

    This is the shape every on-device message-thread ingest uploads. Before this branch existed,
    the mere presence of a user turn forced `unknown`, which is true of *every* 1:1 conversation by
    construction — so a populated `person_id` could never affect anything downstream.
    """
    subject_id, attribution = infer_subject_from_segments(
        [
            SimpleNamespace(is_user=True, person_id=None),
            SimpleNamespace(is_user=False, person_id='p1'),
            SimpleNamespace(is_user=True, person_id=None),
            SimpleNamespace(is_user=False, person_id='p1'),
        ]
    )

    assert subject_id == entities.person_entity_id('p1')
    assert attribution == SubjectAttribution.third_party


def test_infer_subject_from_mixed_segments_without_person_id_is_unknown():
    """The carve-out is for an *identified* counterpart only — an anonymous one stays unknown."""
    subject_id, attribution = infer_subject_from_segments(
        [SimpleNamespace(is_user=True, person_id=None), SimpleNamespace(is_user=False, person_id=None)]
    )

    assert subject_id is None
    assert attribution == SubjectAttribution.unknown


def test_infer_subject_from_multi_party_conversation_is_unknown():
    """Two identified people plus the user is a group conversation, not one person's memories."""
    subject_id, attribution = infer_subject_from_segments(
        [
            SimpleNamespace(is_user=True, person_id=None),
            SimpleNamespace(is_user=False, person_id='p1'),
            SimpleNamespace(is_user=False, person_id='p2'),
        ]
    )

    assert subject_id is None
    assert attribution == SubjectAttribution.unknown


def test_infer_subject_requires_every_non_user_segment_to_be_identified():
    """One unattributed non-user speaker means a third voice is in the room.

    Its memories must not be pinned on the one person we happen to recognize, so partial
    attribution stays unknown even though only a single distinct person_id appears.
    """
    subject_id, attribution = infer_subject_from_segments(
        [
            SimpleNamespace(is_user=True, person_id=None),
            SimpleNamespace(is_user=False, person_id='p1'),
            SimpleNamespace(is_user=False, person_id=None),
        ]
    )

    assert subject_id is None
    assert attribution == SubjectAttribution.unknown


def test_merge_then_split_entities_round_trips_state():
    original = {
        'person:p1': {'id': 'person:p1', 'label': 'Sarah Chen', 'aliases': []},
        'person:p2': {'id': 'person:p2', 'label': 'Sarah from sales', 'aliases': []},
    }
    merged = entities.apply_entity_mutations(
        original,
        [memory_ledger.merge_entities('person:p1', 'person:p2', evidence={'source': 'test'}, confidence=0.9)],
    )

    restored = entities.apply_entity_mutations(
        merged,
        [
            memory_ledger.split_entity(
                'person:p1',
                into=[original['person:p1'], original['person:p2']],
                reason='wrong Sarah merge',
            )
        ],
    )

    assert set(merged) == {'person:p1'}
    assert restored == original
