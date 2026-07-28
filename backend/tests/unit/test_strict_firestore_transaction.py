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


@pytest.mark.parametrize('write_method', ['set', 'update'])
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
    else:
        transaction.update(target, {'value': 'updated'})

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


@pytest.mark.parametrize('write_method', ['set', 'update'])
def test_transaction_rejects_writes_to_a_different_store(write_method):
    database = StrictFirestore({('users', 'user-1', 'records', 'record'): {'value': 'before'}})
    foreign_database = StrictFirestore({('users', 'user-1', 'records', 'record'): {'value': 'before'}})
    transaction = database.transaction()
    record = _record(foreign_database)

    with pytest.raises(ForeignTransactionError, match='same store'):
        getattr(transaction, write_method)(record, {'value': 'after'})


def test_transaction_rejects_reads_from_a_different_store():
    database = StrictFirestore()
    foreign_database = StrictFirestore({('users', 'user-1', 'records', 'record'): {'value': 'before'}})

    with pytest.raises(ForeignTransactionError, match='same store'):
        _record(foreign_database).get(transaction=database.transaction())


@pytest.mark.parametrize(
    'operation',
    [
        pytest.param(lambda database, record: database.transaction().delete(record), id='transaction-delete'),
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
