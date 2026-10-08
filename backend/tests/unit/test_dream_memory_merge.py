"""Duplicate merge uses canonical supersede; undo keeps two direct-user tails."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from database import review_memory_merges as merges, review_store
from models.product_memory import MemoryItem
from models.review import ReviewChange
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

NOW = datetime(2026, 10, 8, tzinfo=timezone.utc)
UID = 'synthetic-memory-owner'


def memory(key, content):
    return MemoryItem(
        memory_id=key,
        uid=UID,
        version=1,
        tier='long_term',
        status='active',
        processing_state='processed',
        content=content,
        source_state='active',
        sensitivity_labels=[],
        visibility='private',
        user_asserted=False,
        captured_at=NOW,
        updated_at=NOW,
        ledger_schema_version='knowledge_ledger.v1',
        kind='fact',
        intent_backed=True,
        ledger_commit_id="synthetic-ledger-commit",
    )


def test_merge_supersedes_both_original_facts_with_evidence(monkeypatch):
    first, second = memory('one', 'Synthetic fact'), memory('two', 'Duplicate synthetic fact')
    captured = []
    monkeypatch.setattr(merges.store, 'client', lambda: object())
    monkeypatch.setattr(
        merges, 'save_ledger_write', lambda uid, write, **kw: captured.append((uid, write, kw)) or 'merged'
    )
    assert (
        merges._merge(UID, [first.model_dump(), second.model_dump()], 'Synthetic combined fact', 'stable-action')
        == 'merged'
    )
    write = captured[0][1]
    assert write.supersedes == ['one', 'two']
    assert write.provenance.action_id == 'stable-action'
    assert captured[0][2]['required_source_item'] == first


def test_undo_appends_two_tails_and_blocks_reapply(monkeypatch):
    originals = [memory('one', 'First synthetic fact'), memory('two', 'Second synthetic fact')]
    current = memory('merged', 'Synthetic merged fact')
    change = ReviewChange(change_id='synthetic-change', kind='merge_memories', title='Merge duplicates', created_at=NOW)
    data = {
        'change': change.model_dump(mode='python'),
        'created_at': NOW,
        'memory_merge': True,
        'edit_key': 'dream:merge_memories:stable',
        'memory_edit': {'content': current.content},
        'phase': 'applied',
        'before': [row.model_dump() for row in originals],
        'active_memory_ids': ['merged'],
    }
    ref_key = ('users', UID, 'review_changes', review_store.safe_id(change.change_id))
    database = StrictFirestore(
        {ref_key: review_store.encode_doc(UID, data), ('users', UID, 'memory_items', 'merged'): current.model_dump()}
    )
    monkeypatch.setattr(review_store, 'client', lambda: database)
    monkeypatch.setattr(merges.firestore, 'transactional', lambda fn: fn)
    # Direct journal update delegates to the strict fixture's supported update
    # operation. It adds no query, retry, delete or contention fake semantics.
    original_user = review_store.user

    class DirectUpdates:
        def __init__(self, ref):
            self.ref = ref

        def get(self, **kw):
            return self.ref.get(**kw)

        def update(self, patch):
            database.transaction().update(self.ref, patch)

    def user(uid):
        real = original_user(uid)

        def collection(name):
            coll = real.collection(name)
            return SimpleNamespace(
                document=lambda key: (
                    DirectUpdates(coll.document(key)) if name == 'review_changes' else coll.document(key)
                )
            )

        return SimpleNamespace(collection=collection)

    monkeypatch.setattr(review_store, 'user', user)
    # Transaction reads/updates must receive the actual strict reference;
    # expose its required ownership/path interface on the direct-update proxy.
    DirectUpdates._database = property(lambda self: self.ref._database)
    DirectUpdates.path = property(lambda self: self.ref.path)
    captured = []
    monkeypatch.setattr(
        merges, 'amend_user_fact', lambda *a, **kw: captured.append(('first', a, kw)) or 'restored-first'
    )
    monkeypatch.setattr(merges, 'save_fact', lambda *a, **kw: captured.append(('second', a, kw)) or 'restored-second')
    result = merges.set_undone(UID, change.change_id, True, data)
    assert result.undone
    assert captured[0][1][2] == originals[0].content
    assert captured[1][1][1] == originals[1].content
    assert captured[0][2]['write_reason'].value == 'direct_user_statement'
    assert captured[1][2]['write_reason'].value == 'direct_user_statement'
    assert captured[1][2]['user_asserted'] is True
    journal = review_store.decode_doc(UID, database.rows[ref_key])
    assert journal['active_memory_ids'] == ['restored-first', 'restored-second']
    assert ('users', UID, 'review_do_not_redo', review_store.safe_id(data['edit_key'])) in database.rows
    # Repeating the completed request performs no additional canonical writes.
    merges.set_undone(UID, change.change_id, True, journal)
    assert len(captured) == 2
