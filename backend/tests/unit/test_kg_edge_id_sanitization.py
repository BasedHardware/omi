"""
Tests for issue #4929: Edge ID sanitization in knowledge graph.

Firestore document IDs cannot contain '/'. When the LLM generates edge labels
like 'works/with', the '/' in the constructed edge_id breaks the Firestore path.
Fix: replace '/' with '_' in edge_id before using as document ID.

The module under test (``database.knowledge_graph``) binds ``db`` at import via
``from database._client import db``, but ``database._client.db`` is a lazy proxy
that defers client construction to first use, so the import is pure and no
``sys.modules`` stubbing is required.
"""

import os
import sys
from unittest.mock import MagicMock

import pytest

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from database.knowledge_graph import upsert_knowledge_edge

mock_db = MagicMock()


class TestEdgeIdSanitization:
    """Tests for '/' sanitization in edge document IDs."""

    def setup_method(self):
        mock_db.reset_mock()
        # database.knowledge_graph imports a module-level db object; point it at
        # this test's mock so the Firestore document() call is observable.
        upsert_knowledge_edge.__globals__['db'] = mock_db
        # Set up document chain: db.collection().document().collection().document()
        self.mock_edge_ref = MagicMock()
        self.mock_edge_ref.get.return_value = MagicMock(exists=False)

        mock_edges_coll = MagicMock()
        mock_edges_coll.document.return_value = self.mock_edge_ref

        mock_user_ref = MagicMock()
        mock_user_ref.collection.return_value = mock_edges_coll

        mock_db.collection.return_value.document.return_value = mock_user_ref
        self.mock_edges_coll = mock_edges_coll

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

    def test_document_called_with_sanitized_id(self):
        """The Firestore document() call must use the sanitized ID."""
        edge_data = {
            'source_id': 'src',
            'target_id': 'tgt',
            'label': 'has/a',
            'memory_ids': ['m1'],
        }
        upsert_knowledge_edge('uid-1', edge_data)
        # Verify the document ID passed to Firestore has no '/'
        doc_id = self.mock_edges_coll.document.call_args[0][0]
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

        Note: '..' as a standalone Firestore doc ID is reserved, but in practice
        edge IDs are always '{uuid}_{label}_{uuid}' format so '..' cannot occur
        from normal construction. This test documents current behavior.
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
