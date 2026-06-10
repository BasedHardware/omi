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
from models.memories import Memory, MemoryCategory, ShortTermMemory  # noqa: E402
from utils.consolidation import worker  # noqa: E402
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
        lambda uid, status, limit: [
            {'id': 'st1', 'content': 'same day fact', 'evidence': [], 'allowed_uses': ['retrieval']}
        ],
    )

    records = memory_reads.get_retrievable_memories('uid-1')

    assert [record['source'] for record in records] == ['long_term', 'short_term']
    assert records[1]['status'] == 'pending_consolidation'


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

    mutations = worker.resolve_window_mutations('uid-1', pending)

    assert any(item['type'] == 'supersede_fact' for item in mutations)
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
