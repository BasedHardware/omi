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


def test_infer_subject_from_mixed_segments_is_unknown():
    subject_id, attribution = infer_subject_from_segments(
        [SimpleNamespace(is_user=True, person_id=None), SimpleNamespace(is_user=False, person_id='p1')]
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
