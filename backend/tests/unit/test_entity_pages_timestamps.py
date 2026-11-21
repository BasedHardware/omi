from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]
ENTITY_PAGES_PATH = BACKEND_DIR / 'utils' / 'entity_pages.py'


def _module(name: str, **attributes) -> ModuleType:
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def _package(name: str, **attributes) -> ModuleType:
    package = _module(name, **attributes)
    package.__path__ = []
    return package


@pytest.fixture
def entity_pages():
    store_stub = AutoMockModule('database.review_store')
    store_stub.decode_doc = lambda _uid, doc: doc
    store_stub.list_proposals = lambda _uid: []
    store_stub.user = lambda _uid: SimpleNamespace(
        collection=lambda _name: SimpleNamespace(
            document=lambda _doc_id: SimpleNamespace(get=lambda: SimpleNamespace(to_dict=lambda: {}))
        )
    )

    conversations_stub = AutoMockModule('database.conversations')
    conversations_stub.is_visible_conversation = lambda conv: not conv.get('discarded', False)
    conversations_stub.get_mcp_conversations_by_id = lambda *_args, **_kwargs: []

    knowledge_graph_stub = AutoMockModule('database.knowledge_graph')
    knowledge_graph_stub.get_knowledge_node = lambda _uid, entity_id: {
        'id': entity_id,
        'node_type': 'organization',
        'label': 'Acme Corp',
        'conversation_ids': ['conv-naive-start', 'conv-iso-strings', 'conv-aware'],
    }
    knowledge_graph_stub.get_knowledge_edges = lambda _uid: []

    database_pkg = _package(
        'database',
        action_items=AutoMockModule('database.action_items'),
        conversations=conversations_stub,
        knowledge_graph=knowledge_graph_stub,
        review_queries=AutoMockModule('database.review_queries'),
        review_store=store_stub,
        users=AutoMockModule('database.users'),
    )

    stubs = {
        'database': database_pkg,
        'database.action_items': database_pkg.action_items,
        'database.conversations': conversations_stub,
        'database.knowledge_graph': knowledge_graph_stub,
        'database.review_queries': database_pkg.review_queries,
        'database.review_store': store_stub,
        'database.users': database_pkg.users,
    }

    with stub_modules(stubs):
        module = load_module_fresh('utils.entity_pages', str(ENTITY_PAGES_PATH))
        yield module


def test_get_entity_page_normalizes_mixed_naive_aware_and_iso_conversation_timestamps(entity_pages, monkeypatch):
    conversation_cache = {
        'conv-naive-start': {
            'id': 'conv-naive-start',
            'user_title': 'Naive Start With Aware Finish',
            'started_at': datetime(2026, 10, 10, 9, 0, 0),
            'finished_at': datetime(2026, 10, 10, 9, 15, 0, tzinfo=timezone.utc),
        },
        'conv-iso-strings': {
            'id': 'conv-iso-strings',
            'user_title': 'ISO String Timestamps',
            'started_at': '2026-10-12T14:00:00',
            'finished_at': '2026-10-12T14:05:30Z',
        },
        'conv-aware': {
            'id': 'conv-aware',
            'user_title': 'Aware Timestamps',
            'started_at': datetime(2026, 10, 11, 12, 0, 0, tzinfo=timezone.utc),
            'finished_at': datetime(2026, 10, 11, 12, 10, 0, tzinfo=timezone.utc),
        },
    }
    monkeypatch.setattr(entity_pages, '_entity_page_conversation_page', lambda _uid: dict(conversation_cache))
    monkeypatch.setattr(entity_pages, '_facts', lambda _uid, _ids, _cache: ([], [], set()))

    page = entity_pages.get_entity_page('uid-1', 'org:acme')

    assert [c.conversation_id for c in page.recent_conversations] == [
        'conv-iso-strings',
        'conv-aware',
        'conv-naive-start',
    ]
    assert [c.duration_seconds for c in page.recent_conversations] == [330, 600, 900]
    assert all(c.started_at.tzinfo is not None for c in page.recent_conversations)
