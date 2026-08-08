from types import SimpleNamespace

from database import entities, memory_ledger, projection_repair
from models.memories import SubjectAttribution
from tests.store_fakes import FakeDocumentStore
from utils.conversations.subjects import infer_subject_from_segments


def _use_fake_store(monkeypatch):
    """Point the ledger (and its repair enqueue) at one shared in-memory store.

    entities.merge/split/reassign do all their writes inside the projection_writer
    callback that memory_ledger.append_commit runs under _store().run_transaction,
    so wiring the ledger's store to a FakeDocumentStore exercises the neutral,
    path-based transaction ops the module now emits.
    """
    store = FakeDocumentStore()
    monkeypatch.setattr(memory_ledger, "_store", lambda: store)
    monkeypatch.setattr(projection_repair, "_store", lambda: store)
    return store


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


def test_merge_entities_projects_onto_store(monkeypatch):
    store = _use_fake_store(monkeypatch)
    uid = 'u1'
    nodes = f'users/{uid}/knowledge_nodes'
    store.set(f'{nodes}/person:p1', {'id': 'person:p1', 'label': 'Sarah Chen', 'aliases': []})
    store.set(f'{nodes}/person:p2', {'id': 'person:p2', 'label': 'Sarah from sales', 'aliases': []})

    result = entities.merge_entities(uid, 'person:p1', 'person:p2', evidence={'source': 'test'}, confidence=0.9)

    assert result['applied'] is True
    # entity_b is deleted, entity_a survives and absorbs the alias + merge provenance.
    assert store.get(f'{nodes}/person:p2').exists is False
    surviving = store.get(f'{nodes}/person:p1').to_dict()
    assert 'Sarah from sales' in surviving['aliases']
    assert surviving['merged_entity_ids'] == ['person:p2']


def test_merge_entities_noops_when_a_node_missing(monkeypatch):
    store = _use_fake_store(monkeypatch)
    uid = 'u1'
    nodes = f'users/{uid}/knowledge_nodes'
    store.set(f'{nodes}/person:p1', {'id': 'person:p1', 'label': 'Sarah Chen', 'aliases': []})

    entities.merge_entities(uid, 'person:p1', 'person:missing')

    surviving = store.get(f'{nodes}/person:p1').to_dict()
    assert surviving == {'id': 'person:p1', 'label': 'Sarah Chen', 'aliases': []}


def test_split_entity_replaces_node_with_children(monkeypatch):
    store = _use_fake_store(monkeypatch)
    uid = 'u1'
    nodes = f'users/{uid}/knowledge_nodes'
    store.set(f'{nodes}/person:merged', {'id': 'person:merged', 'label': 'Sarah'})

    entities.split_entity(
        uid,
        'person:merged',
        into=[{'id': 'person:p1', 'label': 'Sarah Chen'}, {'id': 'person:p2', 'label': 'Sarah from sales'}],
        reason='wrong merge',
    )

    assert store.get(f'{nodes}/person:merged').exists is False
    assert store.get(f'{nodes}/person:p1').to_dict() == {'id': 'person:p1', 'label': 'Sarah Chen'}
    assert store.get(f'{nodes}/person:p2').to_dict() == {'id': 'person:p2', 'label': 'Sarah from sales'}


def test_reassign_fact_subject_updates_memory_projection(monkeypatch):
    store = _use_fake_store(monkeypatch)
    uid = 'u1'
    memory_path = f'users/{uid}/memories/fact-1'
    store.set(memory_path, {'id': 'fact-1', 'subject_entity_id': None})

    entities.reassign_fact_subject(uid, 'fact-1', old=None, new=entities.USER_ENTITY_ID)

    updated = store.get(memory_path).to_dict()
    assert updated['subject_entity_id'] == entities.USER_ENTITY_ID
    assert updated['subject_attribution'] == SubjectAttribution.user.value
    assert 'updated_at' in updated
