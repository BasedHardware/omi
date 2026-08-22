"""Dual-backend contract for the knowledge graph (ADR-0044 facade + ADR-0002 store port).

`database/knowledge_graph.py` stores the entity graph that `GET /v1/knowledge-graph` renders. One
construct in it is a shape the facade has to re-express rather than pass through:

    batch   `delete_knowledge_graph` is the account's "forget this graph" sweep. It pages each
            collection with `limit(500).stream()`, fills a `client.batch()` from the page, commits,
            and loops until the page comes back empty — twice, once over `knowledge_nodes` and once
            over `knowledge_edges`. It backs `DELETE /v1/knowledge-graph`, the rebuild in
            `utils/llm/knowledge_graph.py` (which deletes and then re-extracts, so a survivor is
            merged into the replacement graph and looks authoritative), and the account-level graph
            wipe in `utils/memory/canonical_memory_adapter.py`. Everything it can get wrong is
            silent: it returns `None` and the route answers `status="deleted"` either way. An entity
            it leaves behind is a person, place or claim the user asked to have deleted that
            `GET /v1/knowledge-graph` keeps handing back to them, and — after a rebuild — keeps
            citing memories that no longer support it.

What this suite holds, and what it does not
-------------------------------------------
It holds COMPLETENESS and TERMINATION of that sweep, and it holds them at a size that crosses the
page boundary. Unlike the folders and memories batches, the 500 here is not only a write-chunk size:
it also caps the *read* (`coll_ref.limit(500).stream()`), so a build that does a single pass instead
of looping measurably leaves rows behind and this suite says so (mutation-proven below).

It does NOT hold per-commit atomicity. Replacing the batch with a per-document `doc.reference.delete()`
loop passes here too — neither the emulator nor Mongo exposes a half-applied commit for a test to
observe, and Firestore's 500-writes-per-commit ceiling is not enforced by either. That limitation is
the same one recorded in the folders and memories suites, and it is reported rather than hidden.

The surrounding reads (`get_knowledge_graph`, `upsert_knowledge_node`, `find_node_by_label_or_alias`,
`prune_memory_citations_from_kg`) are here because the sweep has to be observed through the module's
own control flow — asserting only through a store query would assert that the test agrees with the
seed, not that the product's read path agrees that the graph is gone. `prune_memory_citations_from_kg`
is the other, per-citation deletion route over the same two collections, and it is the one a user
triggers by retracting a single memory.

Fixtures deliberately carry no `memory_state/apply_control` document: that makes the user a
legacy-only account, which is exactly the branch `_authoritative_legacy_citation_ids` short-circuits,
so the graph read stays hermetic and the assertions above are about the graph, not about fencing.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

NOW = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)


def _node(node_id: str, label: str, *, memory_ids: list[str], aliases: list[str] | None = None) -> dict:
    aliases = aliases or []
    return {
        'id': node_id,
        'label': label,
        'label_lower': label.lower(),
        'node_type': 'person',
        'aliases': aliases,
        'aliases_lower': [alias.lower() for alias in aliases],
        'memory_ids': memory_ids,
        'created_at': NOW,
        'updated_at': NOW,
    }


def _edge(edge_id: str, source_id: str, target_id: str, *, memory_ids: list[str], label: str = 'knows') -> dict:
    return {
        'id': edge_id,
        'source_id': source_id,
        'target_id': target_id,
        'label': label,
        'memory_ids': memory_ids,
        'created_at': NOW,
    }


@pytest.fixture
def graph(bind_store):
    """Three nodes and two edges for one user, plus a second user whose graph must be untouched."""
    run = uuid.uuid4().hex[:8]
    uid, neighbour = f'kg-{run}', f'kg-other-{run}'
    nodes = [f'n{index}-{run}' for index in range(3)]
    edges = [f'e{index}-{run}' for index in range(2)]

    bind_store.set(
        f'users/{uid}/knowledge_nodes/{nodes[0]}', _node(nodes[0], 'Ada', memory_ids=['m1'], aliases=['Adi'])
    )
    bind_store.set(f'users/{uid}/knowledge_nodes/{nodes[1]}', _node(nodes[1], 'Grace', memory_ids=['m1', 'm2']))
    bind_store.set(f'users/{uid}/knowledge_nodes/{nodes[2]}', _node(nodes[2], 'Lovelace', memory_ids=['m2']))
    bind_store.set(f'users/{uid}/knowledge_edges/{edges[0]}', _edge(edges[0], nodes[0], nodes[1], memory_ids=['m1']))
    bind_store.set(f'users/{uid}/knowledge_edges/{edges[1]}', _edge(edges[1], nodes[1], nodes[2], memory_ids=['m2']))

    keeper = f'keep-{run}'
    bind_store.set(f'users/{neighbour}/knowledge_nodes/{keeper}', _node(keeper, 'Somebody Else', memory_ids=['m9']))
    bind_store.set(
        f'users/{neighbour}/knowledge_edges/{keeper}', _edge(keeper, keeper, keeper, memory_ids=['m9'], label='self')
    )

    yield {'uid': uid, 'neighbour': neighbour, 'nodes': nodes, 'edges': edges, 'run': run, 'store': bind_store}

    for owner in (uid, neighbour):
        for collection in ('knowledge_nodes', 'knowledge_edges'):
            for document in bind_store.query(f'users/{owner}/{collection}'):
                bind_store.delete(document.path)


def _stored_ids(store, uid: str, collection: str) -> set[str]:
    return {document.id for document in store.query(f'users/{uid}/{collection}')}


# --- the sweep, seen through the product's own read path ---------------------------------------------


def test_the_graph_reads_back_what_was_stored(graph):
    """The observation path the deletion tests use. Without this, "the graph is empty afterwards" would
    also be true of a read that never worked."""
    import database.knowledge_graph as kg_db

    snapshot = kg_db.get_knowledge_graph(graph['uid'])

    assert {node['id'] for node in snapshot['nodes']} == set(graph['nodes'])
    assert {edge['id'] for edge in snapshot['edges']} == set(graph['edges'])
    assert snapshot['node_count'] == 3 and snapshot['edge_count'] == 2
    assert snapshot['truncated'] is False


# --- batch --------------------------------------------------------------------------------------------


def test_deleting_the_graph_removes_every_node_and_every_edge(graph):
    """Both collections, in one call. The route answers `status="deleted"` whatever survives, so a
    collection the sweep skips is content the user believes is gone and the UI still draws."""
    import database.knowledge_graph as kg_db

    kg_db.delete_knowledge_graph(graph['uid'])

    assert _stored_ids(graph['store'], graph['uid'], 'knowledge_nodes') == set()
    assert _stored_ids(graph['store'], graph['uid'], 'knowledge_edges') == set()

    snapshot = kg_db.get_knowledge_graph(graph['uid'])
    assert snapshot['nodes'] == [] and snapshot['edges'] == []
    assert snapshot['node_count'] == 0 and snapshot['edge_count'] == 0


def test_deleting_one_account_graph_leaves_another_account_alone(graph):
    """The sweep is uid-scoped by the collection reference it is handed. A translation that widened it
    to the collection group would delete a stranger's graph on a single user's DELETE."""
    import database.knowledge_graph as kg_db

    kg_db.delete_knowledge_graph(graph['uid'])

    assert len(_stored_ids(graph['store'], graph['neighbour'], 'knowledge_nodes')) == 1
    assert len(_stored_ids(graph['store'], graph['neighbour'], 'knowledge_edges')) == 1


def test_deleting_an_empty_graph_terminates_without_raising(graph):
    """`while True` with an empty first page. The loop must exit on the empty page rather than commit an
    empty batch forever, and the second call after a successful sweep is the retry a client makes when
    the first response was lost."""
    import database.knowledge_graph as kg_db

    kg_db.delete_knowledge_graph(f"nobody-{graph['run']}")
    kg_db.delete_knowledge_graph(graph['uid'])
    kg_db.delete_knowledge_graph(graph['uid'])

    assert kg_db.get_knowledge_graph(graph['uid'])['node_count'] == 0


def test_a_graph_larger_than_one_page_is_deleted_completely(bind_store):
    """620 nodes, so the page read at `limit(500)` cannot see the graph in one pass.

    This is the part the folders and memories batch suites explicitly could NOT hold. There the 500 is
    only a write-chunk size and the emulator does not enforce Firestore's per-commit ceiling, so a build
    that never rolled over passed. Here the same constant also bounds the READ, so a single pass leaves
    120 nodes behind and the assertion below fails — verified by mutation.
    """
    import database.knowledge_graph as kg_db

    run = uuid.uuid4().hex[:8]
    uid = f'kg-bulk-{run}'
    total = 620
    for index in range(total):
        node_id = f'b{index}-{run}'
        bind_store.set(f'users/{uid}/knowledge_nodes/{node_id}', _node(node_id, f'Node {index}', memory_ids=['m1']))
    bind_store.set(
        f'users/{uid}/knowledge_edges/x-{run}', _edge(f'x-{run}', f'b0-{run}', f'b1-{run}', memory_ids=['m1'])
    )

    try:
        assert len(_stored_ids(bind_store, uid, 'knowledge_nodes')) == total, 'precondition'

        kg_db.delete_knowledge_graph(uid)

        survivors = _stored_ids(bind_store, uid, 'knowledge_nodes')
        assert survivors == set(), f'{len(survivors)} nodes survived the sweep'
        assert _stored_ids(bind_store, uid, 'knowledge_edges') == set()
    finally:
        for collection in ('knowledge_nodes', 'knowledge_edges'):
            for document in bind_store.query(f'users/{uid}/{collection}'):
                bind_store.delete(document.path)


# --- the per-citation deletion route over the same two collections -------------------------------------


def test_retracting_a_memory_strips_only_its_citations(graph):
    """`prune_memory_citations_from_kg` is what a single retracted memory triggers. A node still cited by
    another memory must survive with the retracted id removed — dropping the whole node would erase a
    belief the user never retracted."""
    import database.knowledge_graph as kg_db

    pruned = kg_db.prune_memory_citations_from_kg(graph['uid'], ['m1'])

    assert pruned >= 1
    grace = graph['store'].get(f"users/{graph['uid']}/knowledge_nodes/{graph['nodes'][1]}")
    assert grace.exists and grace.data['memory_ids'] == ['m2']


def test_retracting_the_last_citation_removes_the_entity_and_its_edges(graph):
    """A node whose only support is gone is deleted, and an edge that would then dangle goes with it —
    the referential closure `get_knowledge_graph` relies on to render anything at all."""
    import database.knowledge_graph as kg_db

    kg_db.prune_memory_citations_from_kg(graph['uid'], ['m1'])

    assert graph['nodes'][0] not in _stored_ids(graph['store'], graph['uid'], 'knowledge_nodes')
    assert graph['edges'][0] not in _stored_ids(graph['store'], graph['uid'], 'knowledge_edges')
    assert graph['edges'][1] in _stored_ids(graph['store'], graph['uid'], 'knowledge_edges')


# --- the write path the rebuild depends on --------------------------------------------------------------


def test_an_upsert_merges_citations_instead_of_replacing_them(graph):
    """`upsert_knowledge_node` reads the node before writing and unions `memory_ids` and `aliases`. A
    write that skipped the read would drop every earlier memory that supports the entity, so the graph
    would forget why it believes anything the moment a second memory mentions it."""
    import database.knowledge_graph as kg_db

    saved = kg_db.upsert_knowledge_node(
        graph['uid'], _node(graph['nodes'][0], 'Ada', memory_ids=['m7'], aliases=['A.L.'])
    )

    assert sorted(saved['memory_ids']) == ['m1', 'm7']
    assert sorted(saved['aliases']) == ['A.L.', 'Adi']
    stored = graph['store'].get(f"users/{graph['uid']}/knowledge_nodes/{graph['nodes'][0]}").data
    assert sorted(stored['memory_ids']) == ['m1', 'm7']


def test_a_node_is_found_by_alias_as_well_as_by_label(graph):
    """`array_contains` over `aliases_lower`, the second probe in `find_node_by_label_or_alias`. It is how
    the rebuild avoids minting a duplicate entity for a name it has already seen spelled differently; a
    backend that cannot answer it splits one person into two."""
    import database.knowledge_graph as kg_db

    by_label = kg_db.find_node_by_label_or_alias(graph['uid'], 'ada')
    by_alias = kg_db.find_node_by_label_or_alias(graph['uid'], 'ADI')

    assert by_label is not None and by_label['id'] == graph['nodes'][0]
    assert by_alias is not None and by_alias['id'] == graph['nodes'][0]
    assert kg_db.find_node_by_label_or_alias(graph['uid'], 'nobody at all') is None
