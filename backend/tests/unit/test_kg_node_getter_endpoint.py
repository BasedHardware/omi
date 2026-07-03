"""GET /v1/knowledge-graph/nodes/{node_id} fetches a single knowledge-graph node.

The full-graph endpoint returns every node and edge; there was no way to fetch one node by
id. This reuses the existing get_knowledge_node helper and returns 404 when it is missing.

Test isolation: routers.knowledge_graph imports cleanly, so the test imports it normally,
patches the import-cheap kg_db helper with monkeypatch.setattr, and calls the handler
directly (no sys.modules mutation, no TestClient).
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from routers import knowledge_graph as kg  # noqa: E402


def test_get_node_returns_node(monkeypatch):
    node = {'id': 'n1', 'label': 'Guitar', 'node_type': 'concept'}
    monkeypatch.setattr(kg.kg_db, 'get_knowledge_node', lambda uid, node_id: node)
    assert kg.get_knowledge_graph_node(node_id='n1', uid='u1') == node


def test_get_node_404_when_missing(monkeypatch):
    monkeypatch.setattr(kg.kg_db, 'get_knowledge_node', lambda uid, node_id: None)
    with pytest.raises(HTTPException) as ei:
        kg.get_knowledge_graph_node(node_id='nope', uid='u1')
    assert ei.value.status_code == 404


def test_get_node_scopes_to_caller_uid(monkeypatch):
    seen = {}

    def fake(uid, node_id):
        seen['args'] = (uid, node_id)
        return {'id': node_id}

    monkeypatch.setattr(kg.kg_db, 'get_knowledge_node', fake)
    kg.get_knowledge_graph_node(node_id='n9', uid='user-7')
    assert seen['args'] == ('user-7', 'n9')
