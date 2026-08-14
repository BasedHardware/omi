"""Return-only knowledge-graph extract uses the managed knowledge_graph feature."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from routers import knowledge_graph as kg_router
from utils.llm.knowledge_graph import ExtractedEdge, ExtractedNode, KnowledgeGraphExtraction

UID = 'uid-kg-extract'


@pytest.fixture(autouse=True)
def _entitled(monkeypatch):
    """Default to an entitled account; the paywall gate has its own test."""
    monkeypatch.setattr(kg_router, 'is_trial_paywalled', lambda uid, platform: False)


async def test_extract_knowledge_graph_returns_client_graph_without_persisting(monkeypatch):
    calls: dict[str, object] = {}

    def fake_extract(uid, text, **kwargs):
        calls['uid'] = uid
        calls['text'] = text
        calls['kwargs'] = kwargs
        return KnowledgeGraphExtraction(
            nodes=[ExtractedNode(label='Neo', node_type='person', aliases=['Thomas'])],
            edges=[ExtractedEdge(source_label='Neo', target_label='Neo', label='is')],
        )

    def fake_to_client(extraction, *, uid):
        calls['client_graph_uid'] = uid
        return {
            'nodes': [{'id': 'n1', 'label': 'Neo', 'node_type': 'person', 'aliases': ['Thomas']}],
            'edges': [],
        }

    monkeypatch.setattr(
        kg_router,
        '_knowledge_graph_llm_module',
        lambda: SimpleNamespace(extract_kg_from_text=fake_extract, extraction_to_client_graph=fake_to_client),
    )
    monkeypatch.setattr(kg_router, 'get_user_name', lambda uid: 'Trinity')

    response = await kg_router.extract_knowledge_graph(
        kg_router.ExtractKnowledgeGraphRequest(text='Neo likes coffee', include_existing=False),
        uid=UID,
    )

    assert response.nodes == [{'id': 'n1', 'label': 'Neo', 'node_type': 'person', 'aliases': ['Thomas']}]
    assert response.edges == []
    assert calls['uid'] == UID
    assert calls['text'] == 'Neo likes coffee'
    assert calls['kwargs']['user_name'] == 'Trinity'
    assert calls['kwargs']['load_existing_from_db'] is False
    # A malformed model response must fail closed rather than look like "no entities".
    assert calls['kwargs']['strict_parse'] is True
    # Client ids are owner-scoped, so the uid must reach the id derivation.
    assert calls['client_graph_uid'] == UID


async def test_extract_knowledge_graph_fails_closed_when_extractor_returns_none(monkeypatch):
    monkeypatch.setattr(
        kg_router,
        '_knowledge_graph_llm_module',
        lambda: SimpleNamespace(
            extract_kg_from_text=lambda *args, **kwargs: None,
            extraction_to_client_graph=MagicMock(),
        ),
    )
    monkeypatch.setattr(kg_router, 'get_user_name', lambda uid: 'User')

    with pytest.raises(HTTPException) as exc:
        await kg_router.extract_knowledge_graph(
            kg_router.ExtractKnowledgeGraphRequest(text='something memorable'),
            uid=UID,
        )
    assert exc.value.status_code == 502


async def test_extract_knowledge_graph_blocks_a_trial_expired_account(monkeypatch):
    monkeypatch.setattr(kg_router, 'is_trial_paywalled', lambda uid, platform: True)
    monkeypatch.setattr(
        kg_router,
        '_knowledge_graph_llm_module',
        lambda: SimpleNamespace(extract_kg_from_text=MagicMock(), extraction_to_client_graph=MagicMock()),
    )

    with pytest.raises(HTTPException) as exc:
        await kg_router.extract_knowledge_graph(
            kg_router.ExtractKnowledgeGraphRequest(text='something memorable'),
            uid=UID,
        )
    assert exc.value.status_code == 402
