"""Pure KG extract helper is return-only and assigns client-stable ids."""

from __future__ import annotations

import json
from contextlib import nullcontext
from unittest.mock import MagicMock

import pytest

from utils.llm import knowledge_graph as kg
from utils.llm.knowledge_graph import ExtractedEdge, ExtractedNode, KnowledgeGraphExtraction


def test_extraction_to_client_graph_assigns_stable_ids_and_skips_self_edges():
    extraction = KnowledgeGraphExtraction(
        nodes=[
            ExtractedNode(label='Neo', node_type='person', aliases=['Thomas']),
            ExtractedNode(label='Zion', node_type='place', aliases=[]),
        ],
        edges=[
            ExtractedEdge(source_label='Neo', target_label='Zion', label='lives in'),
            ExtractedEdge(source_label='Neo', target_label='Neo', label='is'),
        ],
    )
    graph = kg.extraction_to_client_graph(extraction)
    assert len(graph['nodes']) == 2
    assert len(graph['edges']) == 1
    assert graph['edges'][0]['source_id'] == graph['nodes'][0]['id']
    assert graph['edges'][0]['target_id'] == graph['nodes'][1]['id']
    assert 'id' in graph['edges'][0]


def test_extract_kg_from_text_uses_knowledge_graph_feature(monkeypatch):
    seen: dict[str, object] = {}

    def fake_get_llm(feature: str):
        seen['feature'] = feature
        client = MagicMock()
        client.invoke.side_effect = lambda prompt: MagicMock(
            content=json.dumps(
                {
                    'nodes': [{'label': 'Coffee', 'node_type': 'thing', 'aliases': []}],
                    'edges': [],
                }
            )
        )
        return client

    monkeypatch.setattr(kg, 'get_llm', fake_get_llm)
    monkeypatch.setattr(kg, 'track_usage', lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(kg.kg_db, 'get_knowledge_nodes', MagicMock(side_effect=AssertionError('should not load db')))

    extraction = kg.extract_kg_from_text('uid-1', 'User likes coffee', user_name='User')
    assert extraction is not None
    assert seen['feature'] == 'knowledge_graph'
    assert [node.label for node in extraction.nodes] == ['Coffee']
