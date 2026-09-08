"""A legacy graph rebuild must not destroy the stored graph before the new one exists.

`rebuild_knowledge_graph` used to delete the account's graph as its first statement and
then upsert row by row as each memory's LLM round-trip returned — up to 500 memories at
concurrency 4. `_rebuild_graph_task` drives it from FastAPI `BackgroundTasks`, in the
serving process, with no retry: a deploy, restart or eviction inside that multi-minute
window left the account with whatever partial subset had been written and no copy of the
graph it replaced.

These run the production function against an in-memory stand-in for
`database.knowledge_graph` that mirrors the merge semantics of the real
`upsert_knowledge_node` / `upsert_knowledge_edge`, so ordering and the rebuilt graph are
both observed through the same seam production writes through.
"""

from __future__ import annotations

import json
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import nullcontext
from typing import Any, Dict, List, Optional

import pytest

from utils.llm import knowledge_graph as kg


class _FakeKgStore:
    """Mirrors the merge/identity rules of `database.knowledge_graph`."""

    def __init__(self, nodes: Optional[List[Dict[str, Any]]] = None) -> None:
        self.nodes: Dict[str, Dict[str, Any]] = {node['id']: dict(node) for node in (nodes or [])}
        self.edges: Dict[str, Dict[str, Any]] = {}
        self.calls: List[str] = []

    def get_knowledge_nodes(self, uid: str, *, db_client: Any = None, **_: Any) -> List[Dict[str, Any]]:
        self.calls.append('get_knowledge_nodes')
        return [dict(node) for node in self.nodes.values()]

    def delete_knowledge_graph(self, uid: str, *, db_client: Any = None) -> None:
        self.calls.append('delete_knowledge_graph')
        self.nodes.clear()
        self.edges.clear()

    def _find_by_label_or_alias(self, label: str) -> Optional[str]:
        wanted = label.lower()
        for node in self.nodes.values():
            if node.get('label', '').lower() == wanted:
                return node['id']
        for node in self.nodes.values():
            if wanted in {alias.lower() for alias in node.get('aliases', [])}:
                return node['id']
        return None

    def upsert_knowledge_node(self, uid: str, node_data: Dict[str, Any], *, db_client: Any = None) -> Dict[str, Any]:
        self.calls.append('upsert_knowledge_node')
        node_id = node_data['id']
        if node_id not in self.nodes:
            # The real upsert re-resolves a node it cannot find by id.
            node_id = self._find_by_label_or_alias(node_data.get('label', '')) or node_id
        node_data = {**node_data, 'id': node_id}
        existing = self.nodes.get(node_id, {})
        merged = dict(node_data)
        merged['memory_ids'] = sorted(set(existing.get('memory_ids', [])) | set(node_data.get('memory_ids', [])))
        merged['aliases'] = sorted(set(existing.get('aliases', [])) | set(node_data.get('aliases', [])))
        self.nodes[node_id] = merged
        return merged

    def upsert_knowledge_edge(self, uid: str, edge_data: Dict[str, Any], *, db_client: Any = None) -> Dict[str, Any]:
        self.calls.append('upsert_knowledge_edge')
        edge_id = f"{edge_data['source_id']}_{edge_data['label']}_{edge_data['target_id']}".replace('/', '_')
        existing = self.edges.get(edge_id, {})
        merged = dict(edge_data)
        merged['id'] = edge_id
        merged['memory_ids'] = sorted(set(existing.get('memory_ids', [])) | set(edge_data.get('memory_ids', [])))
        self.edges[edge_id] = merged
        return merged

    def get_knowledge_graph(self, uid: str, *, db_client: Any = None) -> Dict[str, Any]:
        self.calls.append('get_knowledge_graph')
        return {'nodes': list(self.nodes.values()), 'edges': list(self.edges.values())}


class _InlineExecutor:
    """Runs each memory inline, in submission order.

    A worker thread left running past the end of a test calls `kg.get_llm` again
    after the next test has repatched it, so its extraction lands in that test's
    recorder — order-dependent, and only on a loaded runner. Nothing here needs
    real concurrency, so nothing here starts a thread.
    """

    def submit(self, fn: Any, *args: Any, **kwargs: Any) -> "Future[Any]":
        future: Future[Any] = Future()
        future.set_result(fn(*args, **kwargs))
        return future


def _response(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> Any:
    class _Response:
        content = json.dumps({'nodes': nodes, 'edges': edges})

    return _Response()


@pytest.fixture
def rebuild_harness(monkeypatch: pytest.MonkeyPatch):
    """Production `rebuild_knowledge_graph` wired to a fake store and a scripted LLM."""
    store = _FakeKgStore(
        nodes=[
            {
                'id': 'pre-existing-node',
                'label': 'Trinity',
                'node_type': 'person',
                'aliases': [],
                'memory_ids': ['old-memory'],
            }
        ]
    )
    monkeypatch.setattr(kg, 'kg_db', store)
    monkeypatch.setattr(kg, 'track_usage', lambda *args, **kwargs: nullcontext())

    executor = ThreadPoolExecutor(max_workers=2)
    monkeypatch.setattr(kg, 'llm_executor', executor)
    try:
        yield store, monkeypatch
    finally:
        executor.shutdown(wait=True)


def test_stored_graph_survives_until_every_extraction_has_finished(rebuild_harness):
    """The delete must not precede the LLM work it depends on."""
    store, monkeypatch = rebuild_harness

    def invoke(_prompt: str) -> Any:
        store.calls.append('llm_invoke')
        return _response([{'label': 'Neo', 'node_type': 'person', 'aliases': ['The One']}], [])

    monkeypatch.setattr(kg, 'get_llm', lambda *_args, **_kwargs: type('LLM', (), {'invoke': staticmethod(invoke)}))

    kg.rebuild_knowledge_graph(
        'uid-1',
        [{'id': 'm1', 'content': 'Neo woke up.'}, {'id': 'm2', 'content': 'Neo flew.'}],
    )

    delete_at = store.calls.index('delete_knowledge_graph')
    last_invoke_at = len(store.calls) - 1 - store.calls[::-1].index('llm_invoke')
    assert last_invoke_at < delete_at, store.calls
    assert store.calls.count('llm_invoke') == 2
    # And the write burst follows the delete, so the swap is delete-then-write.
    assert store.calls.index('upsert_knowledge_node') > delete_at


def test_rebuild_interrupted_before_the_swap_leaves_the_old_graph_intact(rebuild_harness):
    """A driver that dies mid-rebuild must not have destroyed anything yet."""
    store, monkeypatch = rebuild_harness

    def invoke(_prompt: str) -> Any:
        store.calls.append('llm_invoke')
        return _response([{'label': 'Neo', 'node_type': 'person', 'aliases': []}], [])

    monkeypatch.setattr(kg, 'get_llm', lambda *_args, **_kwargs: type('LLM', (), {'invoke': staticmethod(invoke)}))

    class _DyingExecutor(_InlineExecutor):
        """Stands in for the serving process going away: submission stops working."""

        def __init__(self) -> None:
            self._submitted = 0

        def submit(self, fn: Any, *args: Any, **kwargs: Any) -> "Future[Any]":
            self._submitted += 1
            if self._submitted > 1:
                raise RuntimeError('cannot schedule new futures after shutdown')
            return super().submit(fn, *args, **kwargs)

    monkeypatch.setattr(kg, 'llm_executor', _DyingExecutor())

    with pytest.raises(RuntimeError):
        kg.rebuild_knowledge_graph(
            'uid-1',
            [{'id': 'm1', 'content': 'Neo woke up.'}, {'id': 'm2', 'content': 'Neo flew.'}],
        )

    assert 'delete_knowledge_graph' not in store.calls
    assert list(store.nodes) == ['pre-existing-node']
    assert store.nodes['pre-existing-node']['memory_ids'] == ['old-memory']


def test_rebuilt_graph_still_merges_entities_across_memories(rebuild_harness):
    """Staging in memory must resolve labels and aliases the way the store did."""
    store, monkeypatch = rebuild_harness
    scripted = {
        'm1': _response(
            [{'label': 'Neo', 'node_type': 'person', 'aliases': ['The One']}, {'label': 'Zion', 'node_type': 'place'}],
            [{'source_label': 'Neo', 'target_label': 'Zion', 'label': 'lives in'}],
        ),
        # Second memory names the same entity by its alias and repeats the edge.
        'm2': _response(
            [{'label': 'The One', 'node_type': 'person', 'aliases': ['Thomas']}, {'label': 'Zion'}],
            [{'source_label': 'The One', 'target_label': 'Zion', 'label': 'lives in'}],
        ),
    }
    order: List[str] = []

    def invoke(prompt: str) -> Any:
        # The prompt carries the staged nodes, so m2 can only reuse m1's ids if the
        # in-memory snapshot replaced the Firestore read faithfully.
        memory_id = 'm1' if 'Neo woke up.' in prompt else 'm2'
        order.append(memory_id)
        return scripted[memory_id]

    monkeypatch.setattr(kg, 'get_llm', lambda *_args, **_kwargs: type('LLM', (), {'invoke': staticmethod(invoke)}))

    # Serial so m2 observes m1's staged nodes, matching the ordering this asserts.
    monkeypatch.setattr(kg, 'llm_executor', _InlineExecutor())

    graph = kg.rebuild_knowledge_graph(
        'uid-1',
        [{'id': 'm1', 'content': 'Neo woke up.'}, {'id': 'm2', 'content': 'The One flew.'}],
    )

    assert order == ['m1', 'm2']
    assert len(graph['nodes']) == 2, graph['nodes']
    neo = next(node for node in graph['nodes'] if node['label'] in ('Neo', 'The One'))
    assert neo['memory_ids'] == ['m1', 'm2']
    assert set(neo['aliases']) == {'The One', 'Thomas'}

    assert len(graph['edges']) == 1, graph['edges']
    assert graph['edges'][0]['memory_ids'] == ['m1', 'm2']
    assert graph['edges'][0]['source_id'] == neo['id']

    # The pre-existing node is gone: a rebuild still replaces the graph.
    assert 'pre-existing-node' not in store.nodes


def test_edges_follow_the_ids_their_nodes_actually_landed_on(rebuild_harness):
    """Deferring the writes must not let an edge point at an id nothing was written under.

    `upsert_knowledge_node` re-resolves a node it cannot find by id against label and
    alias, so a staged node whose label another staged node later adopted as an alias
    lands under that other node's id. The per-memory loop wrote its edges from
    `saved_node['id']` and so never saw this; the write phase has to do the same.
    """
    store, monkeypatch = rebuild_harness
    scripted = {
        'm1': _response(
            [{'label': 'Neo', 'node_type': 'person'}, {'label': 'Trinity', 'node_type': 'person'}],
            [{'source_label': 'Trinity', 'target_label': 'Neo', 'label': 'knows'}],
        ),
        # Neo takes 'Trinity' as an alias, so the separately staged Trinity node
        # collides with it at write time and lands under Neo's id.
        'm2': _response([{'label': 'Neo', 'node_type': 'person', 'aliases': ['Trinity']}], []),
    }

    def invoke(prompt: str) -> Any:
        return scripted['m1' if 'Neo woke up.' in prompt else 'm2']

    monkeypatch.setattr(kg, 'get_llm', lambda *_args, **_kwargs: type('LLM', (), {'invoke': staticmethod(invoke)}))
    monkeypatch.setattr(kg, 'llm_executor', _InlineExecutor())

    graph = kg.rebuild_knowledge_graph(
        'uid-1',
        [{'id': 'm1', 'content': 'Neo woke up.'}, {'id': 'm2', 'content': 'Neo is Trinity.'}],
    )

    stored_ids = {node['id'] for node in graph['nodes']}
    assert graph['edges'], 'the rebuild dropped the edge entirely'
    for edge in graph['edges']:
        assert edge['source_id'] in stored_ids, (edge, stored_ids)
        assert edge['target_id'] in stored_ids, (edge, stored_ids)
