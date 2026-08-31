"""Dual-backend contract for entity merge/split/reassign (ADR-0044 facade + ADR-0002 store port).

`database/entities.py` is how the knowledge graph is corrected: two cards that turned out to be the
same person are merged, one card that turned out to be two people is split, and a remembered fact is
moved from one subject to another. One at-risk shape carries all three:

    transaction   every correction is a PROJECTION WRITE handed to the memory ledger, which runs it
                  inside the same transaction that reads the ledger head, refuses a stale parent,
                  writes the commit and advances the head. The graph the user sees and the commit log
                  the graph is replayed from are written together or not at all.

                  The failure is not an error, it is a graph that disagrees with its own history. Half
                  a merge leaves the duplicate person still on screen while the log says they were
                  merged, so every later replay re-derives the duplicate and the user "fixes" the same
                  thing forever. Half a split leaves one person's facts attributed to another — the
                  visible form of that is a memory about somebody else shown as if it were about you.
                  And a head that advances on a projection that never landed makes every subsequent
                  correction build on a state that does not exist.

Atomicity is proven from BOTH sides, because the two backends fail at different moments and a single
test would only exercise one of them:

  * `test_a_reassignment_that_cannot_apply_rolls_the_whole_commit_back` targets Firestore's shape: the
    update is STAGED and the transaction only fails at commit, after the commit document and the head
    write are staged behind it. Nothing may survive.
  * `test_a_split_that_fails_halfway_leaves_the_graph_untouched` targets Mongo's: the facade applies
    each write to the open session IMMEDIATELY, so by the time the bad write raises, the deletion and
    the first replacement have already hit the session. Only a real session rollback puts them back.
    On the Firestore leg that same test is nearly vacuous (the id is rejected before any RPC) — said
    plainly here rather than left to look like more than it is.

`resolve_entity_id` is not a transaction; it is covered at the end because it is the door every
correction comes through, and an id that is not stable makes a merge point at a card that does not
exist.

Two mutations SURVIVE this suite, reported here rather than left to be rediscovered:

  * dropping ``transaction=`` from the merge's two snapshot reads (``entity_a_ref.get(transaction=
    transaction)`` -> ``entity_a_ref.get()``). A read that leaves the transaction only differs under
    CONCURRENCY — it would see a card another writer changed mid-correction — and this rig drives one
    caller at a time, so both spellings return the same bytes. Holding it would need a second writer
    racing the transaction, which belongs to a contention test, not a translation contract.
  * moving the reassignment's write out of the transaction (``transaction.update(memory_ref, ...)``
    -> ``memory_ref.update(...)``). The only failure inducible on that path is the missing memory
    document, and it fails AT that very write, so an early-applied write and a transactional one are
    indistinguishable from outside. The same defect on the split path IS caught, because the split
    issues a write that succeeds before the one that fails — which is why that test is written the
    way it is.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid

import pytest

# The subcollections one user's ledger + graph touches. Teardown sweeps exactly these, under a uid
# that exists only for this run — never a collection wholesale, the rig is shared.
OWNED_COLLECTIONS = ('knowledge_nodes', 'memory_state', 'memory_commits', 'memories', 'projection_repairs')


def _node(entity_id: str, label: str, aliases: list[str]):
    return {
        'id': entity_id,
        'label': label,
        'label_lower': label.lower(),
        'aliases': aliases,
        'aliases_lower': [alias.lower() for alias in aliases],
        'node_type': 'person',
        'memory_ids': [],
    }


@pytest.fixture
def graph(bind_store):
    """Three knowledge-graph cards for one user, two of which are the same person under two names."""
    run = uuid.uuid4().hex[:8]
    uid = f'ent-{run}'
    ada, lovelace, grace = f'entity:ada-{run}', f'entity:lovelace-{run}', f'entity:grace-{run}'

    bind_store.set(f'users/{uid}/knowledge_nodes/{ada}', _node(ada, 'Ada', ['A.']))
    bind_store.set(f'users/{uid}/knowledge_nodes/{lovelace}', _node(lovelace, 'Ada Lovelace', ['Countess']))
    bind_store.set(f'users/{uid}/knowledge_nodes/{grace}', _node(grace, 'Grace', []))

    yield {'uid': uid, 'run': run, 'ada': ada, 'lovelace': lovelace, 'grace': grace, 'store': bind_store}

    for collection in OWNED_COLLECTIONS:
        for stored in bind_store.query(f'users/{uid}/{collection}'):
            bind_store.delete(stored.path)


def _doc(graph, path):
    stored = graph['store'].get(f"users/{graph['uid']}/{path}")
    return stored.data if stored is not None and stored.exists else None


def _head(graph):
    state = _doc(graph, 'memory_state/head')
    return (state or {}).get('current_head_commit_id')


def _commit_ids(graph):
    return {stored.id for stored in graph['store'].query(f"users/{graph['uid']}/memory_commits")}


# --- transaction: the merge -------------------------------------------------------------------------


def test_a_merge_folds_the_duplicate_into_the_survivor(graph):
    """The correction the user asked for: one card, carrying both names. The loser's label and aliases
    have to arrive on the survivor — a merge that only deleted would lose the name the user searches
    by, and one that only kept would leave the duplicate on screen."""
    import database.entities as entities_db

    entities_db.merge_entities(graph['uid'], graph['ada'], graph['lovelace'])

    survivor = _doc(graph, f"knowledge_nodes/{graph['ada']}")
    assert survivor['label'] == 'Ada'
    assert sorted(survivor['aliases']) == ['A.', 'Ada Lovelace', 'Countess']
    assert survivor['merged_entity_ids'] == [graph['lovelace']]
    assert _doc(graph, f"knowledge_nodes/{graph['lovelace']}") is None, 'the duplicate is gone'


def test_the_merge_and_its_ledger_commit_land_together(graph):
    """The projection and the history are one write. If the commit could land without the merge, every
    later replay would re-derive the duplicate; if the merge could land without the commit, the
    correction disappears the next time the graph is rebuilt from the log."""
    import database.entities as entities_db

    result = entities_db.merge_entities(graph['uid'], graph['ada'], graph['lovelace'])

    assert result['applied'] is True
    commit_id = result['commit']['commit_id']
    assert _head(graph) == commit_id, 'the head points at the commit that did the merge'

    commit = _doc(graph, f'memory_commits/{commit_id}')
    assert commit is not None, 'the merge is in the log, not only in the graph'
    (recorded,) = commit['mutations']
    assert recorded['type'] == 'merge_entities'
    assert (recorded['entity_a'], recorded['entity_b']) == (graph['ada'], graph['lovelace'])
    assert _doc(graph, f"knowledge_nodes/{graph['lovelace']}") is None


def test_a_second_correction_follows_the_head_instead_of_restarting_from_nothing(graph):
    """Corrections chain. The second merge reads the head the first one wrote and parents itself on it;
    a transaction that read a stale head would refuse the second correction outright — the user clicks
    merge, nothing happens, and no error explains why."""
    import database.entities as entities_db

    first = entities_db.merge_entities(graph['uid'], graph['ada'], graph['lovelace'])
    second = entities_db.merge_entities(graph['uid'], graph['ada'], graph['grace'])

    assert second['applied'] is True
    assert second['commit']['parent_commit_id'] == first['commit']['commit_id']
    assert _head(graph) == second['commit']['commit_id']
    assert _commit_ids(graph) == {first['commit']['commit_id'], second['commit']['commit_id']}

    survivor = _doc(graph, f"knowledge_nodes/{graph['ada']}")
    assert sorted(survivor['merged_entity_ids']) == sorted([graph['lovelace'], graph['grace']])
    assert _doc(graph, f"knowledge_nodes/{graph['grace']}") is None


def test_merging_against_a_card_that_is_already_gone_touches_no_card(graph):
    """Both sides are read INSIDE the transaction and the projection bails if either is missing, so a
    double-clicked merge cannot corrupt the survivor. The ledger still records the attempt — stated
    because the assertion below deliberately does not claim otherwise."""
    import database.entities as entities_db

    entities_db.merge_entities(graph['uid'], graph['ada'], f"entity:ghost-{graph['run']}")

    survivor = _doc(graph, f"knowledge_nodes/{graph['ada']}")
    assert 'merged_entity_ids' not in survivor
    assert sorted(survivor['aliases']) == ['A.'], 'nothing was folded in from a card that does not exist'
    assert _doc(graph, f"knowledge_nodes/{graph['lovelace']}") is not None


# --- transaction: the split -------------------------------------------------------------------------


def test_a_split_replaces_one_card_with_its_parts(graph):
    """The inverse correction: one card was two people all along. The original must go and both parts
    must arrive in the same commit, or the user is left with three cards where they asked for two."""
    import database.entities as entities_db

    first, second = f"entity:p1-{graph['run']}", f"entity:p2-{graph['run']}"
    parts = [_node(first, 'Ada B', []), _node(second, 'Ada C', [])]

    result = entities_db.split_entity(graph['uid'], graph['ada'], parts, reason='two people')

    assert result['applied'] is True
    assert _doc(graph, f"knowledge_nodes/{graph['ada']}") is None
    assert _doc(graph, f'knowledge_nodes/{first}')['label'] == 'Ada B'
    assert _doc(graph, f'knowledge_nodes/{second}')['label'] == 'Ada C'
    assert _head(graph) == result['commit']['commit_id']


def test_a_split_that_fails_halfway_leaves_the_graph_untouched(graph):
    """Rollback, aimed at the Mongo leg. The facade writes each transactional op into the open session
    AS IT IS ISSUED, so when the second replacement is rejected the deletion of the original and the
    first replacement have already been applied there. Only a real session abort puts them back.

    On the Firestore leg this is close to vacuous — the id is refused client-side before any RPC — and
    that is written down rather than dressed up. The Firestore side of atomicity is held by
    `test_a_reassignment_that_cannot_apply_rolls_the_whole_commit_back`, where the write is staged and
    the transaction only fails at commit.
    """
    import database.entities as entities_db

    good = f"entity:good-{graph['run']}"
    parts = [_node(good, 'Kept', []), _node('bad/id', 'Rejected', [])]

    with pytest.raises(ValueError):
        entities_db.split_entity(graph['uid'], graph['ada'], parts)

    assert _doc(graph, f"knowledge_nodes/{graph['ada']}") is not None, 'the original must come back'
    assert _doc(graph, f'knowledge_nodes/{good}') is None, 'and the half-written replacement must not'
    assert _head(graph) is None, 'a correction that did not happen must not advance the head'
    assert _commit_ids(graph) == set()


# --- transaction: reassigning the subject of a fact -------------------------------------------------


@pytest.fixture
def fact(graph):
    """One remembered fact, currently attributed to the user."""
    fact_id = f"fact-{graph['run']}"
    graph['store'].set(
        f"users/{graph['uid']}/memories/{fact_id}",
        {
            'id': fact_id,
            'content': 'prefers oat milk',
            'subject_entity_id': 'user',
            'subject_attribution': 'user',
            'visibility': 'private',
        },
    )
    return fact_id


def test_reassigning_a_fact_moves_it_to_the_new_subject(graph, fact):
    """The user says "that is not about me, that is about Ada". The memory document and the ledger have
    to agree afterwards, or the next replay re-attributes the fact back to the user and the correction
    quietly undoes itself."""
    import database.entities as entities_db

    target = f"person:ada-{graph['run']}"

    result = entities_db.reassign_fact_subject(graph['uid'], fact, 'user', target)

    stored = _doc(graph, f'memories/{fact}')
    assert stored['subject_entity_id'] == target
    assert stored['subject_attribution'] == 'third_party'
    assert stored['content'] == 'prefers oat milk', 'an update, not a replacement — the fact survives'
    assert stored['updated_at'] is not None

    assert _head(graph) == result['commit']['commit_id']
    (recorded,) = _doc(graph, f"memory_commits/{result['commit']['commit_id']}")['mutations']
    assert recorded == {'type': 'reassign_fact_subject', 'fact_id': fact, 'old': 'user', 'new': target}


def test_reassigning_a_fact_back_to_the_user_marks_it_as_their_own(graph, fact):
    """The other direction, and the one with a privacy edge: a fact about the user that stayed marked
    third-party is a fact the product will not treat as theirs."""
    import database.entities as entities_db

    graph['store'].set(
        f"users/{graph['uid']}/memories/{fact}",
        {
            'id': fact,
            'content': 'prefers oat milk',
            'subject_entity_id': 'person:x',
            'subject_attribution': 'third_party',
        },
    )

    entities_db.reassign_fact_subject(graph['uid'], fact, 'person:x', entities_db.USER_ENTITY_ID)

    stored = _doc(graph, f'memories/{fact}')
    assert stored['subject_entity_id'] == 'user'
    assert stored['subject_attribution'] == 'user'


def test_reassigning_to_nobody_leaves_the_subject_unknown(graph, fact):
    import database.entities as entities_db

    entities_db.reassign_fact_subject(graph['uid'], fact, 'user', None)

    stored = _doc(graph, f'memories/{fact}')
    assert stored['subject_entity_id'] is None
    assert stored['subject_attribution'] == 'unknown'


def test_a_reassignment_that_cannot_apply_rolls_the_whole_commit_back(graph, fact):
    """Rollback, aimed at the Firestore leg. The projection updates a memory that does not exist; on
    Firestore that update is STAGED and only rejected at commit — by which time the commit document and
    the head write are staged behind it, so the server has to discard all three together.

    What must not happen is the head advancing over a correction that never landed: every later
    correction would then parent itself on a state the projection never reached.
    """
    from google.api_core.exceptions import NotFound

    import database.entities as entities_db

    settled = entities_db.reassign_fact_subject(graph['uid'], fact, 'user', 'person:one')
    head_before, commits_before = _head(graph), _commit_ids(graph)
    assert head_before == settled['commit']['commit_id']

    with pytest.raises(NotFound):
        entities_db.reassign_fact_subject(graph['uid'], f"missing-{graph['run']}", None, 'person:two')

    assert _head(graph) == head_before, 'the head must not move for a commit that was rolled back'
    assert _commit_ids(graph) == commits_before, 'and the rolled-back commit must not be in the log'


# --- the door every correction comes through --------------------------------------------------------


def test_a_person_resolves_to_a_stable_id_and_gets_a_card(graph):
    """Derived from the person id, not allocated, so two callers naming the same person converge on one
    card instead of creating a second one to merge away later."""
    import database.entities as entities_db

    person_id = f"p-{graph['run']}"

    first = entities_db.resolve_entity_id(graph['uid'], person_id=person_id, label='Bob')
    second = entities_db.resolve_entity_id(graph['uid'], person_id=person_id, label='Bob')

    assert first == second == f'person:{person_id}'
    assert _doc(graph, f'knowledge_nodes/{first}')['label'] == 'Bob'


def test_a_label_resolves_to_the_card_that_already_carries_it(graph):
    """The lookup that stops the graph filling up with duplicates. Miss the existing card and every
    mention of the same name creates a new one."""
    import database.entities as entities_db

    assert entities_db.resolve_entity_id(graph['uid'], label='Ada') == graph['ada']
    assert entities_db.resolve_entity_id(graph['uid'], label='Countess') == graph['lovelace'], 'aliases count too'


def test_an_unknown_label_gets_a_new_card_under_a_deterministic_id(graph):
    import database.entities as entities_db

    entity_id = entities_db.resolve_entity_id(graph['uid'], label='Hopper', entity_type='concept')

    assert entity_id == entities_db.stable_entity_id('Hopper', 'concept')
    assert _doc(graph, f'knowledge_nodes/{entity_id}')['label'] == 'Hopper'


def test_resolving_nothing_resolves_to_nothing(graph):
    import database.entities as entities_db

    assert entities_db.resolve_entity_id(graph['uid']) is None
