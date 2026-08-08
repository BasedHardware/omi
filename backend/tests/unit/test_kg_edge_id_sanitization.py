"""
Tests for issue #4929: Edge ID sanitization in knowledge graph.

Firestore document IDs cannot contain '/'. When the LLM generates edge labels
like 'works/with', the '/' in the constructed edge_id breaks the stored path.
Fix: replace '/' with '_' in edge_id before using it as a document id.

After the storage-port migration ``database.knowledge_graph`` addresses documents
by logical path through ``_store()``; these tests drive the real function through a
``FakeDocumentStore`` installed at that seam.
"""

import os
import sys

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import database.knowledge_graph as kg_mod
from database.knowledge_graph import upsert_knowledge_edge
from tests.store_fakes import FakeDocumentStore

_ORIG_STORE = kg_mod._store


class TestEdgeIdSanitization:
    """Tests for '/' sanitization in edge document IDs."""

    def setup_method(self):
        self.fake = FakeDocumentStore()
        kg_mod._store = lambda: self.fake

    def teardown_method(self):
        kg_mod._store = _ORIG_STORE

    def test_slash_in_label_replaced(self):
        """Edge label 'works/with' should produce edge_id with '_' not '/'."""
        edge_data = {
            'source_id': 'abc',
            'target_id': 'def',
            'label': 'works/with',
            'memory_ids': ['m1'],
        }
        result = upsert_knowledge_edge('uid-1', edge_data)
        edge_id = result['id']
        assert '/' not in edge_id
        assert edge_id == 'abc_works_with_def'

    def test_multiple_slashes_replaced(self):
        """Multiple '/' characters should all be replaced."""
        edge_data = {
            'source_id': 'a',
            'target_id': 'b',
            'label': 'is/was/related',
            'memory_ids': ['m1'],
        }
        result = upsert_knowledge_edge('uid-1', edge_data)
        assert '/' not in result['id']
        assert result['id'] == 'a_is_was_related_b'

    def test_caller_provided_id_with_slash_sanitized(self):
        """Even caller-provided edge IDs with '/' should be sanitized."""
        edge_data = {
            'id': 'custom/edge/id',
            'source_id': 'x',
            'target_id': 'y',
            'label': 'test',
            'memory_ids': ['m1'],
        }
        result = upsert_knowledge_edge('uid-1', edge_data)
        assert '/' not in result['id']
        assert result['id'] == 'custom_edge_id'

    def test_label_without_slash_unchanged(self):
        """Normal labels without '/' should produce correct edge IDs."""
        edge_data = {
            'source_id': 'abc',
            'target_id': 'def',
            'label': 'likes',
            'memory_ids': ['m1'],
        }
        result = upsert_knowledge_edge('uid-1', edge_data)
        assert result['id'] == 'abc_likes_def'

    def test_document_written_with_sanitized_id(self):
        """The stored document path must use the sanitized ID (no '/')."""
        edge_data = {
            'source_id': 'src',
            'target_id': 'tgt',
            'label': 'has/a',
            'memory_ids': ['m1'],
        }
        upsert_knowledge_edge('uid-1', edge_data)
        written = [p for p in self.fake._docs if p.startswith('users/uid-1/knowledge_edges/')]
        assert written == ['users/uid-1/knowledge_edges/src_has_a_tgt']
        doc_id = written[0].rsplit('/', 1)[-1]
        assert '/' not in doc_id
        assert doc_id == 'src_has_a_tgt'

    def test_empty_label_produces_valid_id(self):
        """Empty label should produce a valid edge_id with no slash."""
        edge_data = {
            'source_id': 'abc',
            'target_id': 'def',
            'label': '',
            'memory_ids': ['m1'],
        }
        result = upsert_knowledge_edge('uid-1', edge_data)
        assert '/' not in result['id']
        assert result['id'] == 'abc__def'

    def test_label_only_slash_produces_valid_id(self):
        """Label that is just '/' should be sanitized to '_'."""
        edge_data = {
            'source_id': 'abc',
            'target_id': 'def',
            'label': '/',
            'memory_ids': ['m1'],
        }
        result = upsert_knowledge_edge('uid-1', edge_data)
        assert '/' not in result['id']
        assert result['id'] == 'abc___def'

    def test_caller_provided_dotdot_id_unchanged(self):
        """Caller-provided edge_id '..' is not a slash issue — passes through.

        Note: '..' as a standalone doc ID is reserved, but in practice edge IDs are
        always '{uuid}_{label}_{uuid}' format so '..' cannot occur from normal
        construction. This test documents current behavior.
        """
        edge_data = {
            'id': '..',
            'source_id': 's',
            'target_id': 't',
            'label': 'x',
            'memory_ids': ['m1'],
        }
        result = upsert_knowledge_edge('uid-1', edge_data)
        assert result['id'] == '..'
