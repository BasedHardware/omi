"""Hermetic membership guard; contention/atomic commits live in the emulator proof."""

from unittest.mock import Mock

import pytest

from database import folders
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore


@pytest.mark.parametrize('target', ['target', None])
def test_rehome_uses_current_membership_and_preserves_other_fields(target):
    rows = {
        ('conversations', 'still_source'): {'folder_id': 'source', 'title': 'Keep title', 'folder_user_set': True},
        ('conversations', 'moved'): {'folder_id': 'chosen'},
        ('conversations', 'unfiled'): {'folder_id': None},
        ('conversations', 'legacy'): {'title': 'No folder'},
    }
    client = StrictFirestore(rows)
    references = [
        client.document(f'conversations/{name}') for name in ('still_source', 'moved', 'unfiled', 'legacy', 'gone')
    ]

    folders._rehome_folder_conversations(client, references, 'source', target)

    assert client.rows[('conversations', 'still_source')] == {
        'folder_id': target,
        'title': 'Keep title',
        'folder_user_set': True,
    }
    for name in ('moved', 'unfiled', 'legacy'):
        assert client.rows[('conversations', name)] == rows[('conversations', name)]
    assert ('conversations', 'gone') not in client.rows
    assert client.transactions[0].updates == [(('conversations', 'still_source'), {'folder_id': target})]


def test_rehome_materializes_all_reads_before_the_first_write(monkeypatch):
    client = StrictFirestore({('conversations', name): {'folder_id': 'source'} for name in ('one', 'two', 'three')})
    refs = [client.document(f'conversations/{name}') for name in ('one', 'two', 'three')]

    # The SDK returns a lazy iterator. A write inside the read loop would make
    # the shared fixture reject the next read, including for missing documents.
    def lazy_get_all(references, *, field_paths, transaction):
        assert field_paths == ['folder_id']
        for reference in reversed(references):
            snapshot = reference.get(transaction=transaction, field_paths=field_paths)
            snapshot.reference = reference
            yield snapshot

    monkeypatch.setattr(client, 'get_all', lazy_get_all)
    folders._rehome_folder_conversations(client, refs, 'source', 'target')
    assert len(client.transactions[0].updates) == 3


def test_unknown_read_failure_does_not_replay_or_stage_a_write(monkeypatch):
    client = StrictFirestore({('conversations', 'one'): {'folder_id': 'source'}})
    read = Mock(side_effect=RuntimeError('synthetic read rejection'))
    monkeypatch.setattr(client, 'get_all', read)
    with pytest.raises(RuntimeError, match='synthetic read rejection'):
        folders._rehome_folder_conversations(client, [client.document('conversations/one')], 'source', 'target')
    assert len(client.transactions) == 1
    assert client.transactions[0].updates == []
    assert client.rows[('conversations', 'one')]['folder_id'] == 'source'
