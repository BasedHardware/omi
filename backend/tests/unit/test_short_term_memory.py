import sys
import types
from datetime import datetime, timezone
from unittest.mock import MagicMock

google_stub = sys.modules.setdefault('google', types.ModuleType('google'))
cloud_stub = sys.modules.setdefault('google.cloud', types.ModuleType('google.cloud'))
firestore_stub = sys.modules.setdefault('google.cloud.firestore', types.ModuleType('google.cloud.firestore'))
firestore_stub.Query = type('Query', (), {'DESCENDING': 'DESCENDING'})
firestore_v1_stub = sys.modules.setdefault('google.cloud.firestore_v1', types.ModuleType('google.cloud.firestore_v1'))
firestore_v1_stub.FieldFilter = MagicMock
firestore_v1_stub.transactional = lambda func: func
cloud_stub.firestore = firestore_stub
google_stub.cloud = cloud_stub
pinecone_stub = sys.modules.setdefault('pinecone', types.ModuleType('pinecone'))
pinecone_stub.Pinecone = MagicMock

if 'database._client' not in sys.modules:
    client_stub = types.ModuleType('database._client')
    client_stub.db = MagicMock()
    client_stub.document_id_from_seed = lambda seed: 'id-' + str(abs(hash(seed)) % (10**12))
    sys.modules['database._client'] = client_stub
else:
    sys.modules['database._client'].db = getattr(sys.modules['database._client'], 'db', MagicMock())

for mod_name in ['database.users', 'database.redis_db']:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)
sys.modules['database.users'].get_user_language_preference = MagicMock(return_value='en')
sys.modules['database.users'].get_people_by_ids = MagicMock(return_value=[])

encryption_stub = types.ModuleType('utils.encryption')
encryption_stub.encrypt = lambda data, uid: f"encrypted:{uid}:{data}"
encryption_stub.decrypt = lambda data, uid: data.removeprefix(f"encrypted:{uid}:")
sys.modules['utils.encryption'] = encryption_stub

if 'utils.llm.clients' not in sys.modules:
    clients_stub = types.ModuleType('utils.llm.clients')
    clients_stub.embeddings = MagicMock()
    clients_stub.get_llm = MagicMock()
    sys.modules['utils.llm.clients'] = clients_stub

langchain_stub = sys.modules.setdefault('langchain_core', types.ModuleType('langchain_core'))
output_parsers_stub = sys.modules.setdefault(
    'langchain_core.output_parsers', types.ModuleType('langchain_core.output_parsers')
)
output_parsers_stub.PydanticOutputParser = MagicMock
langchain_stub.output_parsers = output_parsers_stub

prompts_stub = sys.modules.setdefault('utils.prompts', types.ModuleType('utils.prompts'))
prompts_stub.extract_memories_prompt = MagicMock()
prompts_stub.extract_learnings_prompt = MagicMock()
prompts_stub.extract_memories_text_content_prompt = MagicMock()

llms_memory_stub = sys.modules.setdefault('utils.llms.memory', types.ModuleType('utils.llms.memory'))
llms_memory_stub.get_prompt_memories = MagicMock(return_value=('User', ''))

from database import memory_reads, short_term_memories  # noqa: E402
from database import review_queue  # noqa: E402
from models.memories import Memory, MemoryCategory, ShortTermMemory  # noqa: E402
from utils.consolidation import worker  # noqa: E402
from utils.consolidation.typed_resolver import (  # noqa: E402
    mutations_for_typed_resolution,
    pending_review_fact,
    resolve_typed_relationship,
)
from utils.llm.memories import HighRecallMemories, Memories  # noqa: E402


def test_short_term_memory_has_retrieval_shape():
    memory = Memory(content='Lives in NYC', category=MemoryCategory.system)
    short_term = ShortTermMemory.from_memory(
        memory,
        'uid-1',
        source_id='conv1',
        source_type='conversation',
        source_signal='transcription',
        artifact_ref={'kind': 'transcript_segments', 'conversation_id': 'conv1'},
        subject_entity_id='user',
    )

    record = short_term_memories.to_retrieval_record(short_term.model_dump())

    assert record['id'] == short_term.id
    assert record['content'] == 'Lives in NYC'
    assert record['evidence_refs'] == [{'kind': 'transcript_segments', 'conversation_id': 'conv1'}]
    assert record['status'] == 'pending_consolidation'
    assert record['allowed_uses'] == ['retrieval', 'consolidation']
    assert record['capture_confidence'] is not None
    assert record['veracity'] is not None


def test_retrievable_memories_unions_long_and_short_term(monkeypatch):
    monkeypatch.setattr(memory_reads.memories_db, 'get_memories', lambda uid, limit, offset: [{'id': 'lt1'}])
    monkeypatch.setattr(
        memory_reads.short_term_db,
        'get_short_term_memories',
        lambda uid, status, limit: (
            [{'id': 'st1', 'content': 'same day fact', 'evidence': [], 'allowed_uses': ['retrieval']}]
            if status == 'pending_consolidation'
            else []
        ),
    )

    records = memory_reads.get_retrievable_memories('uid-1')

    assert [record['source'] for record in records] == ['long_term', 'short_term']
    assert records[1]['status'] == 'pending_consolidation'


def test_retrievable_memories_includes_pending_review_short_term(monkeypatch):
    monkeypatch.setattr(memory_reads.memories_db, 'get_memories', lambda uid, limit, offset: [])
    monkeypatch.setattr(
        memory_reads.short_term_db,
        'get_short_term_memories',
        lambda uid, status, limit: (
            [{'id': 'review1', 'content': 'needs review', 'status': status, 'evidence': []}]
            if status == 'pending_review'
            else []
        ),
    )

    records = memory_reads.get_retrievable_memories('uid-1')

    assert [record['status'] for record in records] == ['pending_review']


def test_candidate_retrieval_metric_reports_miss():
    metric = worker.candidate_recall_metric({'id': 'st1'}, [{'id': 'other'}], expected_candidate_id='expected')

    assert metric.failure == 'candidate_retrieval_fail'


def test_high_recall_short_term_extractor_schema_removes_legacy_cap():
    capped_schema = Memories.model_json_schema()['properties']['facts']
    high_recall_schema = HighRecallMemories.model_json_schema()['properties']['facts']

    assert capped_schema['maxItems'] == 2
    assert 'maxItems' not in high_recall_schema


def test_consolidation_rerun_is_idempotent_through_deterministic_memory_id(monkeypatch):
    pending = [
        {
            'id': 'st1',
            'content': 'Lives in NYC',
            'category': 'system',
            'evidence': [],
            'source_signal': 'transcription',
            'subject_entity_id': 'user',
        }
    ]
    saved_ids = []

    monkeypatch.setattr(worker.short_term_db, 'get_short_term_memories', lambda uid, status, limit: pending)
    monkeypatch.setattr(worker, 'retrieve_candidates', lambda uid, short_term: [])

    def fake_save(uid, memories):
        saved_ids.append(memories[0]['id'])
        return {'commit': {'commit_id': f"commit-{len(saved_ids)}"}}

    monkeypatch.setattr(worker.memories_db, 'save_memories', fake_save)
    monkeypatch.setattr(worker.short_term_db, 'mark_consolidated', lambda uid, short_term_id, commit_id: None)

    worker.consolidate_pending_window('uid-1', apply_to_head=True)
    worker.consolidate_pending_window('uid-1', apply_to_head=True)

    assert len(set(saved_ids)) == 1


def test_consolidation_shadow_mode_does_not_write_head(monkeypatch):
    pending = [{'id': 'st1', 'content': 'Lives in NYC', 'category': 'system', 'evidence': []}]
    save_mock = MagicMock()
    monkeypatch.setattr(worker.short_term_db, 'get_short_term_memories', lambda uid, status, limit: pending)
    monkeypatch.setattr(worker, 'retrieve_candidates', lambda uid, short_term: [])
    monkeypatch.setattr(worker.memories_db, 'save_memories', save_mock)

    result = worker.consolidate_pending_window('uid-1')

    save_mock.assert_not_called()
    assert result.shadow_mutations
    assert result.committed == 0


def test_window_resolver_supersedes_considering_with_decided():
    pending = [
        {
            'id': 'st1',
            'content': 'Considering Deepgram',
            'category': 'system',
            'evidence': [],
            'created_at': datetime(2026, 6, 1, 10, tzinfo=timezone.utc),
        },
        {
            'id': 'st2',
            'content': 'Decided AssemblyAI',
            'category': 'system',
            'evidence': [],
            'created_at': datetime(2026, 6, 1, 16, tzinfo=timezone.utc),
        },
    ]

    mutations, review_conflicts = worker.resolve_window_mutations('uid-1', pending)

    assert any(item['type'] == 'supersede_fact' for item in mutations)
    assert review_conflicts == []
    assert [item['id'] for item in worker._active_short_terms_after_window_resolution(pending)] == ['st2']


def test_apply_mode_marks_superseded_short_term_records_before_rerun(monkeypatch):
    pending = [
        {
            'id': 'st1',
            'content': 'Considering Deepgram',
            'category': 'system',
            'evidence': [],
            'created_at': datetime(2026, 6, 1, 10, tzinfo=timezone.utc),
        },
        {
            'id': 'st2',
            'content': 'Decided AssemblyAI',
            'category': 'system',
            'evidence': [],
            'created_at': datetime(2026, 6, 1, 16, tzinfo=timezone.utc),
        },
    ]
    marked = set()
    saved_batches = []

    def fake_get_short_term_memories(uid, status, limit):
        return [item for item in pending if item['id'] not in marked]

    def fake_save(uid, memories):
        saved_batches.append(memories)
        return {'commit': {'commit_id': 'commit-window'}}

    def fake_mark(uid, short_term_id, commit_id):
        assert commit_id == 'commit-window'
        marked.add(short_term_id)

    monkeypatch.setattr(worker.short_term_db, 'get_short_term_memories', fake_get_short_term_memories)
    monkeypatch.setattr(worker, 'retrieve_candidates', lambda uid, short_term: [])
    monkeypatch.setattr(worker.memories_db, 'save_memories', fake_save)
    monkeypatch.setattr(worker.short_term_db, 'mark_consolidated', fake_mark)

    first = worker.consolidate_pending_window('uid-1', apply_to_head=True)
    second = worker.consolidate_pending_window('uid-1', apply_to_head=True)

    assert first.committed == 1
    assert second.committed == 0
    assert marked == {'st1', 'st2'}
    assert [[memory['content'] for memory in batch] for batch in saved_batches] == [['Decided AssemblyAI']]


def test_typed_resolver_contradict_emits_add_and_supersede():
    new_fact = _fact('new-sf', 'Lives in San Francisco', predicate='resides_in', arguments={'location': 'SF'})
    old_fact = _fact('old-nyc', 'Lives in New York City', predicate='resides_in', arguments={'location': 'NYC'})

    resolution = resolve_typed_relationship(new_fact, [old_fact])
    mutations = mutations_for_typed_resolution(new_fact, resolution)

    assert resolution.relationship == 'contradict'
    assert [mutation['type'] for mutation in mutations] == ['add_fact', 'supersede_fact']
    assert mutations[1]['kind'] == 'contradict'
    assert mutations[1]['fact_id'] == 'old-nyc'
    assert mutations[1]['by'] == 'new-sf'


def test_typed_resolver_refine_emits_argument_changes():
    old_fact = _fact(
        'old-sf',
        'Lives in San Francisco',
        predicate='resides_in',
        arguments={'city': 'San Francisco'},
    )
    new_fact = _fact(
        'new-mission',
        'Lives in the Mission in San Francisco',
        predicate='resides_in',
        arguments={'city': 'San Francisco', 'neighborhood': 'Mission'},
    )

    resolution = resolve_typed_relationship(new_fact, [old_fact])
    mutations = mutations_for_typed_resolution(new_fact, resolution)

    assert resolution.relationship == 'refine'
    assert mutations == [
        {
            'type': 'refine_fact',
            'fact_id': 'old-sf',
            'arg_changes': {
                'neighborhood': {'to': 'Mission'},
                'content': {'to': 'Lives in the Mission in San Francisco'},
            },
        }
    ]


def test_typed_resolver_extend_and_coexist_add_without_supersession():
    extend_fact = _fact('hobby', 'Likes tennis', predicate='likes', arguments={'activity': 'tennis'})
    coexist_fact = _fact('visited', 'Visited San Francisco', predicate='visited', arguments={'location': 'SF'})
    old_fact = _fact('lives', 'Lives in New York City', predicate='resides_in', arguments={'location': 'NYC'})

    extend_resolution = resolve_typed_relationship(extend_fact, [])
    coexist_resolution = resolve_typed_relationship(coexist_fact, [old_fact])

    assert extend_resolution.relationship == 'extend'
    assert coexist_resolution.relationship == 'coexist'
    assert [item['type'] for item in mutations_for_typed_resolution(extend_fact, extend_resolution)] == ['add_fact']
    assert [item['type'] for item in mutations_for_typed_resolution(coexist_fact, coexist_resolution)] == ['add_fact']


def test_low_veracity_contradiction_routes_to_pending_review():
    old_fact = _fact(
        'old-nyc',
        'Lives in New York City',
        predicate='resides_in',
        arguments={'location': 'NYC'},
        veracity=0.9,
    )
    noisy_new = _fact(
        'new-sf',
        'Lives in San Francisco',
        predicate='resides_in',
        arguments={'location': 'SF'},
        veracity=0.4,
    )

    resolution = resolve_typed_relationship(noisy_new, [old_fact])
    pending = pending_review_fact(noisy_new, resolution)
    record = short_term_memories.to_retrieval_record(pending)

    assert resolution.relationship == 'review_conflict'
    assert resolution.review_required is True
    assert mutations_for_typed_resolution(noisy_new, resolution) == []
    assert pending['status'] == 'pending_review'
    assert record['status'] == 'pending_review'


def test_apply_mode_routes_low_veracity_contradiction_to_review(monkeypatch):
    pending = [
        _fact(
            'st-new-sf',
            'Lives in San Francisco',
            predicate='resides_in',
            arguments={'location': 'SF'},
            veracity=0.4,
        )
    ]
    pending[0]['evidence'] = []
    old_fact = _fact(
        'old-nyc',
        'Lives in New York City',
        predicate='resides_in',
        arguments={'location': 'NYC'},
        veracity=0.9,
    )
    saved = MagicMock()
    pending_review = []
    queued = []

    monkeypatch.setattr(worker.short_term_db, 'get_short_term_memories', lambda uid, status, limit: pending)
    monkeypatch.setattr(worker, 'retrieve_candidates', lambda uid, short_term: [old_fact])
    monkeypatch.setattr(worker.memories_db, 'save_memories', saved)
    monkeypatch.setattr(
        worker.short_term_db,
        'mark_pending_review',
        lambda uid, short_term_id, conflict: pending_review.append((short_term_id, conflict)),
    )
    monkeypatch.setattr(
        worker.review_queue,
        'create_review_conflict',
        lambda uid, **kwargs: queued.append((uid, kwargs)) or {'review_id': 'review1'},
    )

    result = worker.consolidate_pending_window('uid-1', apply_to_head=True)

    saved.assert_not_called()
    assert result.committed == 0
    assert result.review_conflicts[0]['short_term_id'] == 'st-new-sf'
    assert pending_review[0][0] == 'st-new-sf'
    assert queued[0][1]['conflict_with'] == ['old-nyc']


def test_apply_mode_skips_review_queue_for_low_impact_ambiguity(monkeypatch):
    pending = [
        _fact(
            'st-new-sf',
            'Lives in San Francisco',
            predicate='resides_in',
            arguments={'location': 'SF'},
            veracity=0.4,
        )
    ]
    pending[0]['qualifiers'] = {'importance': 0.05}
    pending[0]['evidence'] = []
    old_fact = _fact(
        'old-nyc',
        'Lives in New York City',
        predicate='resides_in',
        arguments={'location': 'NYC'},
        veracity=0.9,
    )
    queued = []
    pending_review = []

    monkeypatch.setattr(worker.short_term_db, 'get_short_term_memories', lambda uid, status, limit: pending)
    monkeypatch.setattr(worker, 'retrieve_candidates', lambda uid, short_term: [old_fact])
    monkeypatch.setattr(worker.memories_db, 'save_memories', MagicMock())
    monkeypatch.setattr(
        worker.short_term_db,
        'mark_pending_review',
        lambda uid, short_term_id, conflict: pending_review.append(short_term_id),
    )
    monkeypatch.setattr(
        worker.short_term_db,
        'mark_consolidated',
        lambda uid, short_term_id, commit_id: (_ for _ in ()).throw(AssertionError('should not consolidate')),
    )
    monkeypatch.setattr(
        worker.review_queue,
        'create_review_conflict',
        lambda uid, **kwargs: queued.append((uid, kwargs)) or {'review_id': 'review1'},
    )

    result = worker.consolidate_pending_window('uid-1', apply_to_head=True)

    assert result.committed == 0
    assert queued == []
    assert pending_review == []


def test_projection_update_for_refine_changes_arguments_and_content():
    updated_at = datetime(2026, 6, 2, tzinfo=timezone.utc)

    update = worker.memories_db.projection_update_for_refine(
        {'content': 'Lives in San Francisco', 'arguments': {'city': 'San Francisco'}},
        {'neighborhood': {'to': 'Mission'}, 'content': {'to': 'Lives in the Mission'}},
        updated_at,
    )

    assert update == {
        'updated_at': updated_at,
        'content': 'Lives in the Mission',
        'arguments': {'city': 'San Francisco', 'neighborhood': 'Mission'},
    }


def test_apply_mode_refine_uses_projection_safe_database_helper(monkeypatch):
    pending = [
        _fact(
            'st-mission',
            'Lives in the Mission in San Francisco',
            predicate='resides_in',
            arguments={'city': 'San Francisco', 'neighborhood': 'Mission'},
        )
    ]
    pending[0]['evidence'] = []
    old_fact = _fact(
        'old-sf',
        'Lives in San Francisco',
        predicate='resides_in',
        arguments={'city': 'San Francisco'},
    )
    saved = MagicMock()
    refined = []

    monkeypatch.setattr(worker.short_term_db, 'get_short_term_memories', lambda uid, status, limit: pending)
    monkeypatch.setattr(worker, 'retrieve_candidates', lambda uid, short_term: [old_fact])
    monkeypatch.setattr(worker.memories_db, 'save_memories', saved)
    monkeypatch.setattr(
        worker.memories_db,
        'refine_memory',
        lambda uid, memory_id, arg_changes: refined.append((memory_id, arg_changes))
        or {'commit': {'commit_id': 'commit-refine'}},
    )
    monkeypatch.setattr(worker.short_term_db, 'mark_consolidated', lambda uid, short_term_id, commit_id: None)

    result = worker.consolidate_pending_window('uid-1', apply_to_head=True)

    saved.assert_not_called()
    assert result.commit_ids == ['commit-refine']
    assert refined[0][0] == 'old-sf'
    assert refined[0][1]['neighborhood'] == {'to': 'Mission'}


def test_review_policy_blocks_pending_irreversible_actions():
    assert review_queue.can_use_for_action('accepted', 'irreversible') is True
    assert review_queue.can_use_for_action('pending_review', 'irreversible') is False
    assert review_queue.can_use_for_action('pending_review', 'answer') is True
    assert review_queue.permitted_uses('tombstoned') == set()


def test_review_economics_escalates_only_ambiguous_high_impact_conflicts():
    high_veracity_new = _fact('new', 'Lives in SF', arguments={'location': 'SF'}, veracity=0.9)
    weak_new = _fact('weak', 'Lives in SF', arguments={'location': 'SF'}, veracity=0.4)
    weak_new['qualifiers'] = {'importance': 0.8}
    low_impact = _fact('low', 'Lives in SF', arguments={'location': 'SF'}, veracity=0.4)
    low_impact['qualifiers'] = {'importance': 0.05}
    old = _fact('old', 'Lives in NYC', arguments={'location': 'NYC'}, veracity=0.9)

    assert review_queue.should_escalate_conflict(high_veracity_new, old) is False
    assert review_queue.should_escalate_conflict(low_impact, old) is False
    assert review_queue.should_escalate_conflict(weak_new, old) is True


def test_pending_timeout_resolves_by_evidence_not_fixed_outcome():
    assert review_queue.timeout_decision({'review_id': 'r1'}, current_veracity=0.8) == 'accept'
    assert review_queue.timeout_decision({'review_id': 'r1'}, current_veracity=0.5) == 'drop'


def test_review_resolution_mutations_and_correction_record():
    item = {
        'review_id': 'review1',
        'fact_id': 'new',
        'candidate': _fact('new', 'Lives in SF', arguments={'location': 'SF'}, veracity=0.4),
        'conflict_with': ['old'],
    }

    accept = review_queue.resolution_mutations(item, 'accept')
    reject = review_queue.resolution_mutations(item, 'reject')
    correct = review_queue.resolution_mutations(
        item,
        'correct',
        correction={'target_fact_id': 'new', 'arg_changes': {'location': {'to': 'Oakland'}}},
    )
    record = review_queue.record_correction(
        'uid-1',
        item=item,
        decision='correct',
        prior_head_diff=[{'type': 'supersede_fact'}],
        final_correction={'location': 'Oakland'},
        reason='user corrected city',
    )

    assert [mutation['type'] for mutation in accept] == ['add_fact', 'supersede_fact']
    assert accept[0]['fact']['status'] == 'accepted'
    assert accept[0]['fact']['qualifiers']['epistemic_status'] == 'accepted'
    assert reject[0]['type'] == 'retract_fact'
    assert correct[0]['type'] == 'refine_fact'
    assert record['candidate']['id'] == 'new'
    assert record['prior_head_state'] == [{'type': 'supersede_fact'}]
    assert record['final_correction'] == {'location': 'Oakland'}


def test_review_queue_lists_pending_items_by_impact(monkeypatch):
    class FakeDoc:
        def __init__(self, doc_id, data):
            self.id = doc_id
            self._data = data

        def to_dict(self):
            return self._data

    queue_ref = MagicMock()
    queue_ref.stream.return_value = [
        FakeDoc('low', {'status': 'pending', 'impact': 0.2}),
        FakeDoc('done', {'status': 'accepted', 'impact': 1.0}),
        FakeDoc('high', {'status': 'pending', 'impact': 0.8}),
    ]
    user_ref = MagicMock()
    user_ref.collection.return_value = queue_ref
    users_ref = MagicMock()
    users_ref.document.return_value = user_ref
    monkeypatch.setattr(review_queue, 'db', MagicMock(collection=MagicMock(return_value=users_ref)))

    items = review_queue.list_review_conflicts('uid-1', limit=10)

    assert [item['review_id'] for item in items] == ['high', 'low']


def test_review_queue_resolve_accept_appends_commit_updates_queue_and_records_correction(monkeypatch):
    item = {
        'review_id': 'review1',
        'fact_id': 'new',
        'candidate': _fact('new', 'Lives in SF', arguments={'location': 'SF'}, veracity=0.4),
        'conflict_with': ['old'],
        'source_short_term_id': 'st-new',
        'status': 'pending',
    }
    updates = []
    doc_ref = MagicMock()
    doc_ref.update.side_effect = lambda payload: updates.append(payload)
    queue_ref = MagicMock()
    queue_ref.document.return_value = doc_ref
    user_ref = MagicMock()
    user_ref.collection.return_value = queue_ref
    users_ref = MagicMock()
    users_ref.document.return_value = user_ref
    merges = []
    corrections = []
    marked_short_term = []

    monkeypatch.setattr(review_queue, 'get_review_conflict', lambda uid, review_id: item)
    monkeypatch.setattr(review_queue, 'db', MagicMock(collection=MagicMock(return_value=users_ref)))
    monkeypatch.setattr(
        review_queue.memories_db,
        'merge_contradict_memory',
        lambda uid, new_memory, superseded_ids: merges.append((new_memory, superseded_ids))
        or {'commit': {'commit_id': 'commit-review'}},
    )
    monkeypatch.setattr(
        review_queue,
        'record_correction',
        lambda uid, **kwargs: corrections.append(kwargs) or {'correction_id': 'correction-review'},
    )
    monkeypatch.setattr(
        review_queue.short_term_db,
        'mark_consolidated',
        lambda uid, short_term_id, commit_id: marked_short_term.append((short_term_id, commit_id)),
    )

    result = review_queue.resolve_review_conflict('uid-1', 'review1', 'accept', reason='looks right')

    assert result['status'] == 'resolved'
    assert result['decision'] == 'accept'
    assert merges[0][0]['status'] == 'accepted'
    assert merges[0][0]['qualifiers']['epistemic_status'] == 'accepted'
    assert merges[0][1] == ['old']
    assert updates[0]['status'] == 'accepted'
    assert updates[0]['resolution_commit_id'] == 'commit-review'
    assert corrections[0]['decision'] == 'accept'
    assert marked_short_term == [('st-new', 'commit-review')]


def test_review_queue_reject_uses_projection_writer(monkeypatch):
    item = {
        'review_id': 'review1',
        'fact_id': 'new',
        'candidate': _fact('new', 'Lives in SF', arguments={'location': 'SF'}, veracity=0.4),
        'conflict_with': ['old'],
        'source_short_term_id': 'st-new',
        'status': 'pending',
    }
    doc_ref = MagicMock()
    queue_ref = MagicMock()
    queue_ref.document.return_value = doc_ref
    user_ref = MagicMock()
    user_ref.collection.return_value = queue_ref
    users_ref = MagicMock()
    users_ref.document.return_value = user_ref
    projection_updates = []
    marked_short_term = []

    class Snapshot:
        exists = True

    class Transaction:
        def update(self, ref, payload):
            projection_updates.append((ref, payload))

    monkeypatch.setattr(review_queue, 'get_review_conflict', lambda uid, review_id: item)
    monkeypatch.setattr(review_queue, 'db', MagicMock(collection=MagicMock(return_value=users_ref)))
    monkeypatch.setattr(review_queue, 'record_correction', lambda uid, **kwargs: {'correction_id': 'correction-review'})
    monkeypatch.setattr(
        review_queue.short_term_db,
        'mark_consolidated',
        lambda uid, short_term_id, commit_id: marked_short_term.append((short_term_id, commit_id)),
    )

    def fake_append_commit(uid, parent, mutations, **kwargs):
        kwargs['projection_writer'](Transaction())
        return {'commit': {'commit_id': 'commit-review'}}

    monkeypatch.setattr(review_queue.memory_ledger, 'append_commit', fake_append_commit)
    queue_ref.document.return_value.get.return_value = Snapshot()

    result = review_queue.resolve_review_conflict('uid-1', 'review1', 'reject')

    assert result['decision'] == 'reject'
    assert result['item']['status'] == 'rejected'
    assert projection_updates[0][1]['review_status'] == 'rejected'
    assert marked_short_term == [('st-new', 'commit-review')]


def test_review_queue_timeout_accepts_or_drops_by_current_evidence(monkeypatch):
    expired = datetime(2026, 6, 1, tzinfo=timezone.utc)
    items = [
        {'review_id': 'review-accept', 'fact_id': 'fact-accept', 'status': 'pending', 'expires_at': expired},
        {'review_id': 'review-drop', 'fact_id': 'fact-drop', 'status': 'pending', 'expires_at': expired},
    ]
    resolved = []

    monkeypatch.setattr(review_queue, 'list_review_conflicts', lambda uid, status, limit: items)
    monkeypatch.setattr(
        review_queue,
        'resolve_review_conflict',
        lambda uid, review_id, decision, **kwargs: resolved.append((review_id, kwargs['current_veracity']))
        or {'decision': review_queue.timeout_decision({}, kwargs['current_veracity'])},
    )

    result = review_queue.resolve_expired_review_conflicts(
        'uid-1',
        now=datetime(2026, 6, 2, tzinfo=timezone.utc),
        current_veracity_by_fact={'fact-accept': 0.8, 'fact-drop': 0.5},
    )

    assert [item['decision'] for item in result] == ['accept', 'drop']
    assert resolved == [('review-accept', 0.8), ('review-drop', 0.5)]


def test_apply_mode_contradict_uses_atomic_merge_helper(monkeypatch):
    pending = [
        _fact(
            'st-new-sf',
            'Lives in San Francisco',
            predicate='resides_in',
            arguments={'location': 'SF'},
            veracity=0.9,
        )
    ]
    pending[0]['evidence'] = []
    old_fact = _fact(
        'old-nyc',
        'Lives in New York City',
        predicate='resides_in',
        arguments={'location': 'NYC'},
        veracity=0.8,
    )
    saved = MagicMock()
    merged = []
    marked = []

    monkeypatch.setattr(worker.short_term_db, 'get_short_term_memories', lambda uid, status, limit: pending)
    monkeypatch.setattr(worker, 'retrieve_candidates', lambda uid, short_term: [old_fact])
    monkeypatch.setattr(worker.memories_db, 'save_memories', saved)
    monkeypatch.setattr(
        worker.memories_db,
        'merge_contradict_memory',
        lambda uid, new_memory, superseded_ids, valid_interval=None: merged.append(
            (new_memory['id'], superseded_ids, valid_interval)
        )
        or {'commit': {'commit_id': 'commit-contradict'}},
    )
    monkeypatch.setattr(
        worker.short_term_db,
        'mark_consolidated',
        lambda uid, short_term_id, commit_id: marked.append((short_term_id, commit_id)),
    )

    result = worker.consolidate_pending_window('uid-1', apply_to_head=True)

    saved.assert_not_called()
    assert result.commit_ids == ['commit-contradict']
    assert result.committed == 1
    assert merged[0][1] == ['old-nyc']
    assert 'valid_to' in merged[0][2]
    assert marked == [('st-new-sf', 'commit-contradict')]


def _fact(
    fact_id,
    content,
    *,
    predicate='resides_in',
    arguments=None,
    subject_entity_id='user',
    veracity=0.8,
):
    return {
        'id': fact_id,
        'content': content,
        'predicate': predicate,
        'arguments': arguments or {},
        'subject_entity_id': subject_entity_id,
        'category': 'system',
        'veracity': veracity,
        'qualifiers': {},
    }
