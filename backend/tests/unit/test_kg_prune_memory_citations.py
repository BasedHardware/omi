"""Tests for KG citation pruning and dangling-edge cleanup."""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import database.knowledge_graph as kg_mod  # noqa: E402
from tests.store_fakes import FakeDocumentStore  # noqa: E402


@pytest.fixture
def kg_module(monkeypatch):
    """The real ``database.knowledge_graph`` driven through a ``FakeDocumentStore`` at ``_store``."""
    fake = FakeDocumentStore()
    monkeypatch.setattr(kg_mod, "_store", lambda: fake)
    return kg_mod, fake


def test_prune_memory_citations_removes_dangling_edges_when_node_deleted(kg_module):
    kg_mod, fake = kg_module
    uid = "uid-kg-prune"
    node_path = f"users/{uid}/knowledge_nodes/node_a"
    edge_path = f"users/{uid}/knowledge_edges/edge_ab"
    fake._docs.update(
        {
            node_path: {
                "id": "node_a",
                "label": "Entity A",
                "memory_ids": ["mem_old"],
            },
            edge_path: {
                "id": "edge_ab",
                "source_id": "node_a",
                "target_id": "node_b",
                "label": "related_to",
                "memory_ids": ["mem_old", "mem_other"],
            },
        }
    )

    pruned = kg_mod.prune_memory_citations_from_kg(uid, ["mem_old"])

    assert node_path not in fake._docs
    assert edge_path not in fake._docs
    assert pruned >= 2
