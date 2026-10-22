"""Entity pages accept legacy timestamp shapes from both conversation readers."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import review as review_router
from utils import entity_pages as pages
from utils.memory import memory_service, product_memory_read_service


@pytest.fixture
def entity_store(monkeypatch):
    owner = MagicMock()
    owner.collection.return_value.document.return_value.get.return_value.to_dict.return_value = {}
    monkeypatch.setattr(pages.store, 'user', lambda uid: owner)
    monkeypatch.setattr(pages.store, 'client', lambda: object())
    monkeypatch.setattr(pages.store, 'decode_doc', lambda uid, data: data)
    monkeypatch.setattr(pages.store, 'list_proposals', lambda uid: [])
    monkeypatch.setattr(pages.knowledge_graph, 'get_knowledge_edges', lambda uid: [])
    monkeypatch.setattr(pages.conversations, 'is_visible_conversation', lambda row: not row.get('deleted'))
    return owner


def test_recent_conversations_normalize_before_duration_and_sort(entity_store, monkeypatch):
    rows = [
        dict(id='naive', started_at=datetime(2026, 10, 1, 12), finished_at='2026-10-01T12:02:00Z'),
        dict(
            id='aware',
            started_at=datetime(2026, 10, 1, 13, tzinfo=timezone.utc),
            finished_at=datetime(2026, 10, 1, 13, 3),
        ),
        dict(id='iso', started_at='2026-10-01T15:00:00+01:00', finished_at='2026-10-01T14:04:00Z'),
        dict(id='fallback', started_at='bad', created_at='2026-10-01T15:00:00', finished_at='bad'),
        dict(id='negative', started_at='2026-10-01T11:00:00Z', finished_at='2026-10-01T10:00:00'),
        dict(id='invalid', started_at='bad'),
        dict(id='hidden', started_at='2026-10-01T16:00:00Z', deleted=True),
    ]
    monkeypatch.setattr(
        pages,
        'resolve_entity',
        lambda *args: dict(entity_id='org', type='organization', name='Team', conversation_ids=[r['id'] for r in rows]),
    )
    monkeypatch.setattr(pages, '_facts', lambda *args: ([], [], set()))
    # Exercise both the initial page and the fact/graph conversation hydration path.
    monkeypatch.setattr(pages, '_entity_page_conversation_page', lambda uid: {r['id']: r for r in rows[:2]})
    monkeypatch.setattr(pages.conversations, 'get_mcp_conversations_by_id', lambda *args, **kwargs: rows[2:])

    recent = pages.get_entity_page('u', 'org').recent_conversations

    assert [row.conversation_id for row in recent] == ['fallback', 'iso', 'aware', 'naive', 'negative']
    assert [row.duration_seconds for row in recent] == [0, 240, 180, 120, 0]
    assert all(row.started_at.tzinfo is timezone.utc for row in recent)
    assert recent[1].started_at == datetime(2026, 10, 1, 14, tzinfo=timezone.utc)

    monkeypatch.setenv('REVIEW_SURFACE_MODE', 'on')
    app = FastAPI()
    app.include_router(review_router.router)
    app.dependency_overrides[review_router.ReadUser.dependency] = lambda: 'u'
    with TestClient(app) as client:
        response = client.get('/v1/entities/org/page')
    assert response.status_code == 200
    assert [row['duration_seconds'] for row in response.json()['recent_conversations']] == [0, 240, 180, 120, 0]


@pytest.mark.parametrize('started_at', [datetime(2026, 10, 1, 12), '2026-10-01T13:00:00+01:00', 'bad', None])
@pytest.mark.parametrize('conversation_source', [True, False])
def test_fact_sources_normalize_timestamp_and_created_at_fallback(
    entity_store, monkeypatch, started_at, conversation_source
):
    query = MagicMock()
    query.order_by.return_value.limit.return_value.stream.return_value = [SimpleNamespace(id='fact')]
    spec = SimpleNamespace(collection_group='memories', build=lambda *args, **kwargs: query)
    monkeypatch.setattr(pages, 'review_queries', SimpleNamespace(ENTITY_FACTS=spec, CANONICAL_FACTS=spec))
    source_id = 'conversation' if conversation_source else None
    row = SimpleNamespace(
        conversation_id=source_id,
        created_at=datetime(2026, 10, 1, 12),
        user_review=None,
        is_locked=False,
        subject_entity_id='org',
        content='Saved fact',
        manually_added=True,
        model_dump=lambda **kwargs: {'conversation_id': source_id},
    )
    monkeypatch.setattr(
        product_memory_read_service, 'fetch_authoritative_product_memory_items_by_ids', lambda *args, **kwargs: []
    )
    monkeypatch.setattr(memory_service, 'MemoryService', lambda **kwargs: SimpleNamespace(fetch=lambda *args: row))
    conversation = dict(id='conversation', started_at=started_at)

    facts, _, _ = pages._facts('u', ['org'], {'conversation': conversation})

    assert facts[0].source.at == datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    assert facts[0].source.at.tzinfo is timezone.utc
