"""Regression tests for hybrid (keyword + vector) conversation search (#5072).

AI Chat could not find conversations by participant/speaker names: search_conversations_tool
and search_conversations_text used Pinecone vector search only, and embeddings rank proper
names poorly — so "when did I talk to Steph?" returned the k nearest (wrong) conversations
even when "Steph" was literally in a conversation summary. The fix merges the existing
Typesense keyword search (titles/overviews) with the vector results, keyword hits first.

These tests cover the merge ordering/dedup, the fail-open behavior of the keyword helper,
and structurally guard that both chat retrieval call sites use the hybrid path.
"""

import os
import sys
from types import ModuleType
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]

os.environ.setdefault('TYPESENSE_HOST', 'localhost')
os.environ.setdefault('TYPESENSE_HOST_PORT', '8108')
os.environ.setdefault('TYPESENSE_API_KEY', 'test-key-not-real')

_REAL_PACKAGE_DIRS = {
    "utils": BACKEND_DIR / "utils",
    "utils.conversations": BACKEND_DIR / "utils" / "conversations",
}


def _remove_module(name: str) -> None:
    module = sys.modules.pop(name, None)
    if module is None or "." not in name:
        return

    parent_name, attr = name.rsplit(".", 1)
    parent = sys.modules.get(parent_name)
    if parent is not None and getattr(parent, attr, None) is module:
        delattr(parent, attr)


def _restore_real_backend_package(package_name: str) -> None:
    """Discard empty package stubs left by earlier collected unit tests."""
    backend_path = str(BACKEND_DIR)
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)

    package = sys.modules.get(package_name)
    if package is None:
        return

    expected_dir = _REAL_PACKAGE_DIRS[package_name].resolve()
    package_paths = getattr(package, "__path__", None)
    if not package_paths:
        _remove_module(package_name)
        return

    try:
        has_real_path = any(Path(path).resolve() == expected_dir for path in package_paths)
    except (OSError, TypeError):
        has_real_path = False
    if not has_real_path:
        _remove_module(package_name)


typesense_mod = sys.modules.get('typesense')
if typesense_mod is None:
    typesense_mod = ModuleType('typesense')
    sys.modules['typesense'] = typesense_mod
if not hasattr(typesense_mod, 'Client'):
    typesense_mod.Client = MagicMock

_restore_real_backend_package("utils")
_restore_real_backend_package("utils.conversations")

import utils.conversations.search as search_module
from utils.conversations.search import keyword_search_conversation_ids, merge_conversation_search_ids


class TestMergeConversationSearchIds:
    def test_keyword_hits_first_then_vector_deduplicated(self):
        assert merge_conversation_search_ids(['k1', 'k2'], ['v1', 'k2', 'v2']) == ['k1', 'k2', 'v1', 'v2']

    def test_empty_keyword_returns_vector_only(self):
        assert merge_conversation_search_ids([], ['v1', 'v2']) == ['v1', 'v2']

    def test_empty_vector_returns_keyword_only(self):
        assert merge_conversation_search_ids(['k1'], []) == ['k1']

    def test_both_empty(self):
        assert merge_conversation_search_ids([], []) == []

    def test_does_not_mutate_inputs(self):
        keyword_ids = ['k1']
        vector_ids = ['v1']
        merged = merge_conversation_search_ids(keyword_ids, vector_ids)
        merged.append('x')
        assert keyword_ids == ['k1']
        assert vector_ids == ['v1']


class TestKeywordSearchConversationIds:
    def test_returns_ids_from_search_items(self):
        with patch.object(search_module, 'search_conversations') as mock_search:
            mock_search.return_value = {'items': [{'id': 'c1'}, {'id': 'c2'}]}
            assert keyword_search_conversation_ids('uid1', 'Steph', limit=5) == ['c1', 'c2']

    def test_skips_items_without_id(self):
        with patch.object(search_module, 'search_conversations') as mock_search:
            mock_search.return_value = {'items': [{'id': 'c1'}, {'foo': 'bar'}, {'id': None}]}
            assert keyword_search_conversation_ids('uid1', 'Steph') == ['c1']

    def test_fails_open_to_empty_list_on_search_error(self):
        with patch.object(search_module, 'search_conversations') as mock_search:
            mock_search.side_effect = Exception('typesense unreachable')
            assert keyword_search_conversation_ids('uid1', 'Steph') == []

    def test_passes_filters_and_excludes_discarded(self):
        with patch.object(search_module, 'search_conversations') as mock_search:
            mock_search.return_value = {'items': []}
            keyword_search_conversation_ids('uid1', 'Steph', limit=7, start_date=100, end_date=200)
            mock_search.assert_called_once_with(
                uid='uid1',
                query='Steph',
                per_page=7,
                include_discarded=False,
                start_date=100,
                end_date=200,
            )


class TestCallSitesUseHybridSearch:
    """Structural guards: both chat retrieval paths must merge keyword + vector results."""

    @pytest.mark.parametrize(
        'rel_path',
        [
            'utils/retrieval/tools/conversation_tools.py',
            'utils/retrieval/tool_services/conversations.py',
        ],
    )
    def test_call_site_merges_keyword_and_vector(self, rel_path):
        source = (BACKEND_DIR / rel_path).read_text(encoding='utf-8')
        assert 'keyword_search_conversation_ids(' in source, f'{rel_path} lost the keyword search half of #5072'
        assert 'merge_conversation_search_ids(' in source, f'{rel_path} lost the hybrid merge of #5072'
