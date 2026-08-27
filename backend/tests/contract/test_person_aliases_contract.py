"""Dual-backend contract for the stable person rename (ADR-0044 facade + ADR-0002 store port).

`database/person_aliases.py` arrived with upstream in the +30 merge and was found by the post-merge
audit (ADR-0030), not by a conflict: it is a NEW file, so it merged cleanly and only the coverage
ratchet noticed it had no dual-backend cover. Its single at-risk shape is the whole module:

    transaction   `update_person_name_transaction` READS the person document inside the transaction
                  and computes the new alias list from what it read. The read is the point: the alias
                  history is derived by appending the PRIOR name, so a rename that computes from a
                  stale copy silently drops or duplicates an alias — and a person's alias list is what
                  speaker attribution matches against, so losing one un-names past transcript segments.

                  The write is `transaction.update`, not `set`: the patch names three fields, and a
                  replacing write would erase everything else the person document carries.

What this suite does NOT hold, measured rather than assumed: it cannot prove the read is inside the
transaction. Catching that needs a genuine concurrent write between read and commit, and the two
backends deliberately disagree about what happens then (Firestore locks its read set, Mongo snapshots
and takes no read lock — ADR-0070). A contract suite asserts the intersection, so what is held is that
the new state is computed from what was READ, plus the translation the facade has to get right:
`transaction.update` on a missing document, the returned booleans, and the 24-alias bound.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid

import pytest


def _client():
    """The client this backend deploys, resolved through the accessor ``bind_store`` patched."""
    from database import _client as client_module

    return client_module.get_firestore_client()


@pytest.fixture
def person(bind_store):
    run = uuid.uuid4().hex[:8]
    uid, person_id = f'uid-{run}', f'person-{run}'

    yield {'uid': uid, 'person_id': person_id, 'store': bind_store}

    bind_store.delete(f'users/{uid}/people/{person_id}')
    bind_store.delete(f'users/{uid}')


def _seed(person, **fields):
    person['store'].set(f"users/{person['uid']}/people/{person['person_id']}", fields)


def _rename(person, name):
    import database.person_aliases as person_aliases

    return person_aliases.rename_person_retaining_aliases(_client(), person['uid'], person['person_id'], name)


def _stored(person):
    stored = person['store'].get(f"users/{person['uid']}/people/{person['person_id']}")
    return stored.data if stored is not None and stored.exists else None


# --- transaction: the rename is computed from what the transaction read ----------------------------


def test_the_prior_name_becomes_an_alias(person):
    _seed(person, name='Anna Rossi', speech_samples=['sample-1'])

    assert _rename(person, 'Anna Bianchi') is True

    stored = _stored(person)
    assert stored['name'] == 'Anna Bianchi'
    assert stored['aliases'] == ['Anna Rossi']
    # `update`, not `set`: everything else on the document survives.
    assert stored['speech_samples'] == ['sample-1']


def test_renaming_back_does_not_duplicate_an_alias(person):
    """The alias list is a SET by casefolded value, and the current name is never in it.

    This is what proves the new state is derived from the stored one rather than appended blindly:
    after A -> B -> A, 'Anna Rossi' is the name again and must not also sit in its own alias list.
    """
    _seed(person, name='Anna Rossi')

    assert _rename(person, 'Anna Bianchi') is True
    assert _rename(person, 'Anna Rossi') is True

    stored = _stored(person)
    assert stored['name'] == 'Anna Rossi'
    assert stored['aliases'] == ['Anna Bianchi']


def test_a_case_only_rename_keeps_one_alias_entry(person):
    _seed(person, name='anna rossi')

    assert _rename(person, 'Anna Rossi') is True

    stored = _stored(person)
    assert stored['name'] == 'Anna Rossi'
    assert stored['aliases'] == []


def test_stored_aliases_are_carried_forward_and_bounded_at_24(person):
    """The bound is `aliases[-24:]`, i.e. the OLDEST are dropped. A person renamed many times keeps a
    recent history, not an unbounded one — and the document must not grow without limit."""
    _seed(person, name='name-30', aliases=[f'name-{index}' for index in range(30)])

    assert _rename(person, 'name-31') is True

    stored = _stored(person)
    assert len(stored['aliases']) == 24
    # 'name-30' was the prior name and is appended last; the window keeps the newest.
    assert stored['aliases'][-1] == 'name-30'
    assert stored['aliases'][0] == 'name-7'


def test_a_rejected_name_leaves_the_document_untouched(person):
    """`normalized_person_alias` refuses blank and over-128-character names, and the refusal must
    happen with NOTHING written — the transaction returns False before `update`."""
    _seed(person, name='Anna Rossi', aliases=['Anna Verdi'])

    for rejected in ('   ', 'x' * 129):
        assert _rename(person, rejected) is False

    stored = _stored(person)
    assert stored['name'] == 'Anna Rossi'
    assert stored['aliases'] == ['Anna Verdi']
    assert 'updated_at' not in stored


def test_a_missing_person_is_false_not_an_error(person):
    """Nothing is seeded: the in-transaction read finds no document.

    Both backends must report this the same way — False, not an exception and not a document created
    by the update. A rename racing a delete is ordinary, and the router turns False into a 404.
    """
    assert _rename(person, 'Anna Rossi') is False
    assert _stored(person) is None
