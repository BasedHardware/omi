"""KG extraction must keep the existing-node listing out of provider-rejection territory.

``extract_knowledge_from_memory`` embedded every node Firestore returned. A user with
5,788 nodes produced a ~641k-character prompt, the provider answered 400, and every
extraction for that user failed from then on — the richer the graph, the more certain
the failure.
"""

from __future__ import annotations

import json
import os
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from utils.llm import knowledge_graph as kg

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)


def _nodes(count: int) -> list[dict]:
    return [
        {
            'id': f'node-{index:05d}',
            'label': f'Entity {index}',
            'node_type': 'concept',
            'aliases': [f'alias-{index}'],
            'updated_at': NOW - timedelta(minutes=index),
        }
        for index in range(count)
    ]


@pytest.fixture
def captured_prompt(monkeypatch):
    """Run extraction against a stub LLM and hand back the prompt it received."""
    seen: dict[str, str] = {}

    def fake_get_llm(feature: str):
        client = MagicMock()

        def invoke(prompt: str):
            seen['prompt'] = prompt
            return MagicMock(content=json.dumps({'nodes': [], 'edges': []}))

        client.invoke.side_effect = invoke
        return client

    monkeypatch.setattr(kg, 'get_llm', fake_get_llm)
    monkeypatch.setattr(kg, 'track_usage', lambda *args, **kwargs: nullcontext())
    return seen


def _prompt_nodes(prompt: str) -> list[dict]:
    start = prompt.index('**EXISTING NODES IN USER\'S KNOWLEDGE GRAPH:**\n') + len(
        '**EXISTING NODES IN USER\'S KNOWLEDGE GRAPH:**\n'
    )
    return json.loads(prompt[start : prompt.index('\n', start)])


def test_prompt_node_listing_is_capped_for_large_graphs(monkeypatch, captured_prompt):
    monkeypatch.setattr(kg.kg_db, 'get_knowledge_nodes', lambda uid, db_client=None: _nodes(5788))

    kg.extract_knowledge_from_memory('uid-1', 'user likes coffee', 'memory-1')

    # 5,788 nodes rendered ~641k characters before the cap and the provider rejected it.
    assert len(captured_prompt['prompt']) < 200_000
    listed = _prompt_nodes(captured_prompt['prompt'])
    assert len(listed) == kg.MAX_PROMPT_EXISTING_NODES
    # Newest first, so the nodes the user is actively building on stay in the prompt.
    assert listed[0]['id'] == 'node-00000'


def test_small_graphs_are_listed_in_full(monkeypatch, captured_prompt):
    monkeypatch.setattr(kg.kg_db, 'get_knowledge_nodes', lambda uid, db_client=None: _nodes(12))

    kg.extract_knowledge_from_memory('uid-1', 'user likes coffee', 'memory-1')

    assert len(_prompt_nodes(captured_prompt['prompt'])) == 12


def test_node_omitted_from_prompt_still_merges_into_its_existing_id(monkeypatch):
    """Capping the listing must not create duplicates for the nodes it left out."""
    existing = _nodes(5788)
    oldest = existing[-1]
    monkeypatch.setattr(kg.kg_db, 'get_knowledge_nodes', lambda uid, db_client=None: existing)

    upserts: list[dict] = []
    monkeypatch.setattr(
        kg.kg_db,
        'upsert_knowledge_node',
        lambda uid, node_data, db_client=None: upserts.append(node_data) or node_data,
    )
    monkeypatch.setattr(kg, 'track_usage', lambda *args, **kwargs: nullcontext())

    extraction = json.dumps({'nodes': [{'label': oldest['label'], 'node_type': 'concept', 'aliases': []}], 'edges': []})
    client = MagicMock()
    client.invoke.return_value = MagicMock(content=extraction)
    monkeypatch.setattr(kg, 'get_llm', lambda feature: client)

    kg.extract_knowledge_from_memory('uid-1', 'user likes coffee', 'memory-1')

    assert [node['id'] for node in upserts] == [oldest['id']]
