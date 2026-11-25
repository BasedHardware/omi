"""Contract tests for the narrow strict Firestore transaction fixture."""

from __future__ import annotations

import pytest

from tests.unit.fixtures.strict_firestore_transaction import (
    ForeignTransactionError,
    ReadAfterWriteError,
    StrictFirestore,
    UnsupportedFirestoreOperationError,
)


def _record(database: StrictFirestore):
    return database.collection('users').document('user-1').collection('records').document('record')


@pytest.mark.parametrize('write_method', ['set', 'update', 'delete'])
def test_transaction_rejects_reads_after_any_write(write_method):
    database = StrictFirestore(
        {
            ('users', 'user-1', 'records', 'source'): {'value': 'source'},
            ('users', 'user-1', 'records', 'target'): {'value': 'target'},
        }
    )
    source = database.collection('users').document('user-1').collection('records').document('source')
    target = database.collection('users').document('user-1').collection('records').document('target')
    transaction = database.transaction()

    source.get(transaction=transaction)
    if write_method == 'set':
        transaction.set(target, {'value': 'updated'})
    elif write_method == 'update':
        transaction.update(target, {'value': 'updated'})
    else:
        transaction.delete(target)

    with pytest.raises(ReadAfterWriteError, match='complete all reads'):
        source.get(transaction=transaction)


def test_transaction_ordering_state_is_local_to_each_transaction():
    database = StrictFirestore(
        {
            ('users', 'user-1', 'records', 'source'): {'value': 'source'},
            ('users', 'user-1', 'records', 'target'): {'value': 'target'},
        }
    )
    source = database.collection('users').document('user-1').collection('records').document('source')
    target = database.collection('users').document('user-1').collection('records').document('target')

    first = database.transaction()
    first.set(target, {'value': 'updated'})

    assert source.get(transaction=database.transaction()).to_dict() == {'value': 'source'}


def test_named_opt_out_allows_reads_after_writes():
    database = StrictFirestore(
        {('users', 'user-1', 'records', 'record'): {'value': 'before'}},
        allow_reads_after_writes=True,
    )
    record = database.collection('users').document('user-1').collection('records').document('record')
    transaction = database.transaction()

    transaction.set(record, {'value': 'after'})

    assert record.get(transaction=transaction).to_dict() == {'value': 'after'}


def test_app_review_config_merge_stores_the_updated_fields_and_preserves_other_fields():
    path = ('app_review_config', 'ios')
    database = StrictFirestore({path: {'hidden_versions': ['2.1.0'], 'other': 'kept'}})
    reference = database.collection('app_review_config').document('ios')
    transaction = database.transaction()

    transaction.set(reference, {'hidden_versions': ['3.0.0'], 'reviewer_uids': ['reviewer']}, merge=True)

    assert database.rows[path] == {
        'hidden_versions': ['3.0.0'],
        'reviewer_uids': ['reviewer'],
        'other': 'kept',
    }


@pytest.mark.parametrize('write_method', ['set', 'update', 'delete'])
def test_transaction_rejects_writes_to_a_different_store(write_method):
    database = StrictFirestore({('users', 'user-1', 'records', 'record'): {'value': 'before'}})
    foreign_database = StrictFirestore({('users', 'user-1', 'records', 'record'): {'value': 'before'}})
    transaction = database.transaction()
    record = _record(foreign_database)

    with pytest.raises(ForeignTransactionError, match='same store'):
        if write_method == 'delete':
            transaction.delete(record)
        else:
            getattr(transaction, write_method)(record, {'value': 'after'})


def test_transaction_rejects_reads_from_a_different_store():
    database = StrictFirestore()
    foreign_database = StrictFirestore({('users', 'user-1', 'records', 'record'): {'value': 'before'}})

    with pytest.raises(ForeignTransactionError, match='same store'):
        _record(foreign_database).get(transaction=database.transaction())


@pytest.mark.parametrize(
    'operation',
    [
        pytest.param(lambda database, record: database.transaction().get(record), id='transaction-get'),
        pytest.param(lambda database, record: database.transaction().get_all([record]), id='transaction-get-all'),
        pytest.param(lambda _database, record: record.delete(), id='document-delete'),
        pytest.param(
            lambda database, _record: database.collection('users').where('id', '==', 'user-1'), id='collection-query'
        ),
        pytest.param(lambda database, _record: database.collection('users').stream(), id='collection-stream'),
    ],
)
def test_unsupported_operations_fail_loudly(operation):
    database = StrictFirestore({('users', 'user-1', 'records', 'record'): {'value': 'before'}})
    record = _record(database)

    with pytest.raises(UnsupportedFirestoreOperationError, match='supports only'):
        operation(database, record)


def test_transaction_create_inserts_a_new_document_and_rejects_an_existing_one():
    database = StrictFirestore()
    record = _record(database)
    transaction = database.transaction()

    transaction.create(record, {'value': 'after'})
    assert transaction.has_written is True
    assert transaction.creates == [(record.path, {'value': 'after'})]
    # read-after-write is forbidden within the same transaction; verify via a fresh one
    assert record.get(transaction=database.transaction()).to_dict() == {'value': 'after'}

    with pytest.raises(RuntimeError, match='document already exists'):
        transaction.create(record, {'value': 'again'})


def test_transaction_delete_removes_document_and_is_idempotent():
    database = StrictFirestore({('users', 'user-1', 'records', 'record'): {'value': 'before'}})
    record = _record(database)
    transaction = database.transaction()
    transaction.delete(record)
    transaction.delete(record)
    assert transaction.has_written and transaction.deletes == [record.path, record.path]
    assert not record.get().exists


def test_bounded_equality_id_query_filters_and_enforces_transaction_ordering():
    from google.cloud.firestore_v1.base_query import FieldFilter

    database = StrictFirestore(
        {
            ('fences', 'a'): {'uid': 'u', 'window': 'one'},
            ('fences', 'b'): {'uid': 'u', 'window': 'two'},
            ('fences', 'c'): {'uid': 'u', 'window': 'one'},
            ('fences', 'd', 'nested', 'e'): {'uid': 'u', 'window': 'one'},
        }
    )
    query = database.collection('fences').where(filter=FieldFilter('uid', '==', 'u'))
    query = query.where(filter=FieldFilter('window', '==', 'one')).select(()).limit(1)
    transaction = database.transaction()
    assert [row.to_dict() for row in query.stream(transaction=transaction)] == [{}]
    assert len(list(query.limit(10).stream(transaction=transaction))) == 2
    with pytest.raises(ForeignTransactionError):
        list(query.stream(transaction=StrictFirestore().transaction()))
    transaction.set(database.document('fences/new'), {'uid': 'u', 'window': 'one'})
    with pytest.raises(ReadAfterWriteError):
        list(query.stream(transaction=transaction))


def test_folder_batch_get_projects_membership_and_does_not_promise_order():
    database = StrictFirestore({('records', 'one'): {'folder_id': 'folder', 'private': 'not returned'}})
    references = [database.document('records/one'), database.document('records/missing')]
    transaction = database.transaction()
    rows = database.get_all(references, field_paths=['folder_id'], transaction=transaction)
    assert [row.reference.path for row in rows] == [('records', 'missing'), ('records', 'one')]
    assert rows[0].exists is False
    assert rows[1].to_dict() == {'folder_id': 'folder'}
    transaction.update(references[0], {'folder_id': None})
    with pytest.raises(ReadAfterWriteError):
        database.get_all(references, field_paths=['folder_id'], transaction=transaction)


def test_folder_batch_get_rejects_foreign_store_and_unsupported_projection():
    database = StrictFirestore()
    with pytest.raises(ForeignTransactionError):
        database.get_all(
            [StrictFirestore().document('records/one')], field_paths=['folder_id'], transaction=database.transaction()
        )
    with pytest.raises(UnsupportedFirestoreOperationError):
        database.get_all(
            [database.document('records/one')], field_paths=['private'], transaction=database.transaction()
        )


def test_parent_navigation_preserves_owner_store_and_read_ordering():
    database = StrictFirestore()
    source = _record(database)
    owner = source.parent.parent
    assert owner is not None
    assert owner.path == ('users', 'user-1')
    assert owner.parent.parent is None
    sibling = owner.collection('processing_attention_items').document('item')
    transaction = database.transaction()
    assert not sibling.get(transaction=transaction).exists
    transaction.set(sibling, {'active': True})
    assert database.rows[('users', 'user-1', 'processing_attention_items', 'item')] == {'active': True}
    with pytest.raises(ReadAfterWriteError):
        sibling.get(transaction=transaction)


@pytest.mark.parametrize('parent', [None, 42, {}, {'kept': 'old'}])
def test_nested_update_matches_emulator_nonmap_replacement(parent):
    # Proven against the real emulator in the phase 2a integration proof.
    path = ('users', 'user-1', 'records', 'record')
    database = StrictFirestore({path: {'nested': parent}})
    transaction = database.transaction()
    transaction.update(_record(database), {'nested.child': 2, '`literal.dot`.value': 3})
    nested = {'child': 2, **({'kept': 'old'} if isinstance(parent, dict) and parent else {})}
    assert database.rows[path] == {'nested': nested, 'literal.dot': {'value': 3}}


def test_photo_probe_finds_a_child_and_enforces_transaction_ordering():
    conversation = ('users', 'user-1', 'conversations', 'c')
    database = StrictFirestore({conversation: {}, (*conversation, 'photos', 'p'): {'id': 'p'}})
    photos = database.document('/'.join(conversation)).collection('photos')
    empty = database.document('users/user-1/conversations/other').collection('photos')

    assert [row.to_dict() for row in photos.limit(1).stream(transaction=database.transaction())] == [{'id': 'p'}]
    assert list(empty.limit(1).stream(transaction=database.transaction())) == []

    transaction = database.transaction()
    transaction.update(database.document('/'.join(conversation)), {'status': 'processing'})
    with pytest.raises(ReadAfterWriteError, match='before the first write'):
        photos.limit(1).stream(transaction=transaction)
    with pytest.raises(ForeignTransactionError, match='same store'):
        photos.limit(1).stream(transaction=StrictFirestore().transaction())


@pytest.mark.parametrize(
    'probe',
    [
        pytest.param(lambda photos, _records: photos.limit(1).stream(), id='outside-a-transaction'),
        pytest.param(lambda photos, _records: photos.limit(2), id='wider-limit'),
        pytest.param(lambda _photos, records: records.limit(1), id='another-subcollection'),
    ],
)
def test_photo_probe_models_nothing_else(probe):
    database = StrictFirestore({('users', 'user-1', 'conversations', 'c'): {}})
    conversation = database.document('users/user-1/conversations/c')

    with pytest.raises(UnsupportedFirestoreOperationError, match='supports only'):
        probe(conversation.collection('photos'), conversation.collection('records'))
