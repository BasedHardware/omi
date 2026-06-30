"""Unit tests for the temporal-memory "constantly updated brain" + hybrid retrieval.

Covers the deterministic pieces that don't need Firestore/Pinecone/LLM:
  - BM25 + Reciprocal Rank Fusion (hybrid retrieval, point #2)
  - MemoryDB temporal lifecycle fields (valid_at / invalid_at / is_active, point #3)
"""

import importlib
import os
import sys
from types import ModuleType
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_test_secret_key_for_unit_tests_only_000000000000000000')

# Stub database._client only while this module's tests run (see fixture below).
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

_ISOLATED_MODULE_NAMES = (
    'database',
    'database._client',
    'utils.retrieval.hybrid',
    'models.memories',
)

_TEMPORAL_BRAIN_EXPORTS = (
    'bm25_scores',
    'rrf_rerank',
    'Evidence',
    'Memory',
    'MemoryDB',
    'MemoryCategory',
    'SubjectAttribution',
    'confidence_band',
    'compute_veracity',
    'merge_evidence_sets',
    'render_memory',
    'structurally_conflicts',
)


class _AutoMockModule(ModuleType):
    """Import-complete stub: missing attributes resolve to MagicMock (no cross-test leak)."""

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


def _drop_stale_module(module_name, expected_file):
    module = sys.modules.get(module_name)
    if module is None:
        return
    module_file = getattr(module, '__file__', None)
    if isinstance(module_file, str) and os.path.abspath(module_file) == expected_file:
        return
    sys.modules.pop(module_name, None)
    parent_name, child_name = module_name.rsplit('.', 1)
    parent = sys.modules.get(parent_name)
    if isinstance(parent, ModuleType) and getattr(parent, child_name, None) is module:
        delattr(parent, child_name)


@pytest.fixture(scope='module', autouse=True)
def _temporal_brain_import_isolation():
    """Install import stubs only for this file's tests; restore before other modules run."""
    original_modules = {name: sys.modules.get(name) for name in _ISOLATED_MODULE_NAMES}

    _drop_stale_module(
        'utils.retrieval.hybrid',
        os.path.join(_BACKEND_DIR, 'utils', 'retrieval', 'hybrid.py'),
    )
    _drop_stale_module('models.memories', os.path.join(_BACKEND_DIR, 'models', 'memories.py'))
    sys.modules.pop('models.memories', None)

    client_stub = _AutoMockModule('database._client')
    client_stub.document_id_from_seed = lambda seed: 'id-' + str(abs(hash(seed)) % (10**12))
    sys.modules['database._client'] = client_stub
    database_pkg = sys.modules.get('database')
    if isinstance(database_pkg, ModuleType):
        setattr(database_pkg, '_client', client_stub)

    hybrid_mod = importlib.import_module('utils.retrieval.hybrid')
    memories_mod = importlib.import_module('models.memories')
    module_globals = globals()
    module_globals['bm25_scores'] = hybrid_mod.bm25_scores
    module_globals['rrf_rerank'] = hybrid_mod.rrf_rerank
    module_globals['Evidence'] = memories_mod.Evidence
    module_globals['Memory'] = memories_mod.Memory
    module_globals['MemoryDB'] = memories_mod.MemoryDB
    module_globals['MemoryCategory'] = memories_mod.MemoryCategory
    module_globals['SubjectAttribution'] = memories_mod.SubjectAttribution
    module_globals['confidence_band'] = memories_mod.confidence_band
    module_globals['compute_veracity'] = memories_mod.compute_veracity
    module_globals['merge_evidence_sets'] = memories_mod.merge_evidence_sets
    module_globals['render_memory'] = memories_mod.render_memory
    module_globals['structurally_conflicts'] = memories_mod.structurally_conflicts

    yield

    for name, original in original_modules.items():
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original
    database_pkg_after = sys.modules.get('database')
    if (
        isinstance(database_pkg_after, ModuleType)
        and original_modules.get('database._client') is not client_stub
        and getattr(database_pkg_after, '_client', None) is client_stub
    ):
        if original_modules.get('database._client') is None:
            delattr(database_pkg_after, '_client')
        else:
            setattr(database_pkg_after, '_client', original_modules['database._client'])

    for export_name in _TEMPORAL_BRAIN_EXPORTS:
        module_globals.pop(export_name, None)


class TestBM25:
    def test_exact_keyword_match_scores_highest(self):
        docs = [
            "the user phone number is 12345",
            "the user likes hiking",
            "favorite food is pizza",
        ]
        scores = bm25_scores("phone number", docs)
        assert len(scores) == 3
        assert scores[0] == max(scores) > 0
        assert scores[1] == 0.0 and scores[2] == 0.0

    def test_empty_docs(self):
        assert bm25_scores("anything", []) == []

    def test_no_query_term_match(self):
        assert bm25_scores("zzz", ["hello world"]) == [0.0]


class TestRRF:
    def test_keyword_lifts_buried_vector_hit(self):
        # Vector order is a, b, c (c last). The keyword query matches only c, so fusion
        # must lift c above b — proof the keyword signal is actually applied.
        candidates = [
            {'id': 'a', 'content': 'user enjoys hiking and trails'},
            {'id': 'b', 'content': 'user likes pizza'},
            {'id': 'c', 'content': 'user phone number is 415 555 1234'},
        ]
        out = rrf_rerank("phone number", candidates, limit=3)
        ids = [o['id'] for o in out]
        assert ids.index('c') < ids.index('b')
        assert all('_hybrid_score' in o for o in out)

    def test_limit_truncates(self):
        cands = [{'id': str(i), 'content': f'memory number {i}'} for i in range(10)]
        assert len(rrf_rerank("memory", cands, limit=3)) == 3

    def test_does_not_mutate_input(self):
        cands = [{'id': 'a', 'content': 'x'}]
        rrf_rerank("x", cands, 1)
        assert '_hybrid_score' not in cands[0]

    def test_empty(self):
        assert rrf_rerank("q", [], 5) == []


class TestMemoryLifecycle:
    def _bare(self, **over):
        base = dict(
            id='x',
            uid='u',
            content='c',
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        base.update(over)
        return MemoryDB(**base)

    def test_new_memory_defaults_to_active(self):
        m = self._bare()
        assert m.invalid_at is None
        assert m.superseded_by is None
        assert m.is_active is True

    def test_from_memory_sets_valid_at_and_active(self):
        mem = Memory(content='Loves ice cream', category=MemoryCategory.system)
        db = MemoryDB.from_memory(mem, uid='u', conversation_id='conv1', manually_added=False)
        assert db.valid_at is not None
        assert db.invalid_at is None
        assert db.is_active is True

    def test_from_memory_seeds_conversation_evidence(self):
        mem = Memory(content='Loves ice cream', category=MemoryCategory.system)
        db = MemoryDB.from_memory(mem, uid='u', conversation_id='conv1', manually_added=False)

        assert len(db.evidence) == 1
        evidence = db.evidence[0]
        assert evidence.source_id == 'conv1'
        assert evidence.source_type == 'conversation'
        assert evidence.source_signal == 'transcription'
        assert evidence.independence_group == 'conv1'
        assert evidence.redaction_status == 'active'

    def test_from_memory_seeds_manual_api_evidence(self):
        mem = Memory(content='Prefers aisle seats', category=MemoryCategory.manual)
        db = MemoryDB.from_memory(mem, uid='u', conversation_id=None, manually_added=True)

        assert len(db.evidence) == 1
        evidence = db.evidence[0]
        assert evidence.source_id == f'external:{db.id}'
        assert evidence.independence_group == f'external:{db.id}'
        assert evidence.source_type == 'developer_api'
        assert evidence.source_signal == 'manual'
        assert evidence.capture_confidence == 0.95

    def test_from_memory_accepts_integration_evidence_context(self):
        mem = Memory(content='Uses Linear for issue tracking', category=MemoryCategory.system)
        db = MemoryDB.from_memory(
            mem,
            uid='u',
            conversation_id=None,
            manually_added=False,
            source_id='linear',
            source_type='integration:linear',
            source_signal='integration',
            artifact_ref={'kind': 'integration_text', 'external_id': 'issue-1'},
            extractor_id='extract_memories_from_text',
        )

        evidence = db.evidence[0]
        assert evidence.source_id == 'linear'
        assert evidence.source_type == 'integration:linear'
        assert evidence.source_signal == 'integration'
        assert evidence.artifact_ref == {'kind': 'integration_text', 'external_id': 'issue-1'}
        assert evidence.extractor_id == 'extract_memories_from_text'

    def test_invalidated_memory_is_not_active(self):
        m = self._bare(invalid_at=datetime.now(timezone.utc), superseded_by='y')
        assert m.is_active is False
        assert m.superseded_by == 'y'

    def test_evidence_from_same_source_shares_independence_group(self):
        first = Evidence.from_source(
            source_id='conv1',
            source_type='conversation',
            source_signal='transcription',
            extractor_id='extractor',
            extractor_version='v1',
            artifact_ref={'kind': 'span', 'segment_id': 's1'},
        )
        second = Evidence.from_source(
            source_id='conv1',
            source_type='conversation',
            source_signal='transcription',
            extractor_id='extractor',
            extractor_version='v1',
            artifact_ref={'kind': 'span', 'segment_id': 's2'},
        )

        assert first.independence_group == second.independence_group == 'conv1'
        assert first.evidence_id != second.evidence_id

    def test_merge_evidence_sets_appends_without_duplicates(self):
        existing = [
            {'evidence_id': 'ev1', 'source_id': 'conv1'},
            {'evidence_id': 'ev2', 'source_id': 'gmail:msg1'},
        ]
        incoming = [
            {'evidence_id': 'ev2', 'source_id': 'gmail:msg1'},
            {'evidence_id': 'ev3', 'source_id': 'linear:issue1'},
        ]

        merged = merge_evidence_sets(existing, incoming)

        assert [item['evidence_id'] for item in merged] == ['ev1', 'ev2', 'ev3']

    def test_merge_evidence_sets_reactivates_matching_tombstoned_evidence(self):
        existing = [
            {'evidence_id': 'ev1', 'source_id': 'conv1', 'redaction_status': 'tombstoned'},
        ]
        incoming = [
            {'evidence_id': 'ev1', 'source_id': 'conv1', 'redaction_status': 'active', 'quote': 'same fact'},
        ]

        merged = merge_evidence_sets(existing, incoming)

        assert len(merged) == 1
        assert merged[0]['redaction_status'] == 'active'
        assert merged[0]['quote'] == 'same fact'

    def test_veracity_counts_independent_groups_not_raw_rows(self):
        one_group = [
            {'evidence_id': 'ev1', 'independence_group': 'conv1', 'capture_confidence': 0.8},
            {'evidence_id': 'ev2', 'independence_group': 'conv1', 'capture_confidence': 0.8},
        ]
        two_groups = one_group + [{'evidence_id': 'ev3', 'independence_group': 'ocr1', 'capture_confidence': 0.45}]

        assert compute_veracity(two_groups) > compute_veracity(one_group)
        assert compute_veracity(one_group) == compute_veracity(one_group[:1])

    def test_confidence_band_uses_configured_thresholds(self):
        assert confidence_band(0.91) == 'certain'

    def test_from_memory_propositionizes_common_prose_fact(self):
        mem = Memory(content='Lives in NYC', category=MemoryCategory.system)
        db = MemoryDB.from_memory(mem, uid='u', conversation_id='conv1', manually_added=False)

        assert db.predicate == 'resides_in'
        assert db.arguments == {'location': 'NYC'}
        assert db.subject_entity_id == 'user'
        assert db.subject_attribution == SubjectAttribution.user
        assert db.render() == 'Lives in NYC'

    def test_from_memory_accepts_third_party_subject_context(self):
        mem = Memory(content='Lives in NYC', category=MemoryCategory.system)
        db = MemoryDB.from_memory(
            mem,
            uid='u',
            conversation_id='conv1',
            manually_added=False,
            subject_entity_id='person:p1',
            subject_attribution=SubjectAttribution.third_party,
        )

        assert db.subject_entity_id == 'person:p1'
        assert db.subject_attribution == SubjectAttribution.third_party

    def test_from_memory_preserves_extractor_structured_proposition(self):
        mem = Memory(
            content='Works at OpenAI as engineer',
            category=MemoryCategory.system,
            predicate='works_at',
            arguments={'organization': 'OpenAI', 'role': 'engineer'},
            subject_entity_id='user',
        )
        db = MemoryDB.from_memory(mem, uid='u', conversation_id='conv1', manually_added=False)

        assert db.predicate == 'works_at'
        assert db.arguments == {'organization': 'OpenAI', 'role': 'engineer'}
        assert render_memory(db) == 'Works at OpenAI as engineer'

    def test_structural_conflict_detects_same_subject_predicate_different_arg(self):
        nyc = Memory(content='Lives in NYC', category=MemoryCategory.system)
        sf = Memory(content='Lives in SF', category=MemoryCategory.system)

        assert structurally_conflicts(nyc, sf) is True

    def test_structural_conflict_ignores_distinct_predicates(self):
        location = Memory(content='Lives in NYC', category=MemoryCategory.system)
        preference = Memory(content='Likes tennis', category=MemoryCategory.system)

        assert structurally_conflicts(location, preference) is False
