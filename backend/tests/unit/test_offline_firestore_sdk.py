from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.cloud.firestore_v1 import Client
from google.cloud.firestore_v1.query import Query
from google.cloud.firestore_v1.transaction import Transaction

from tests.unit.fixtures.offline_firestore_sdk import OfflineFirestoreClient


def test_offline_client_is_not_a_genuine_client():
    client = OfflineFirestoreClient(project='p')
    assert not isinstance(client, Client)


def test_offline_client_builds_real_sdk_query_and_reference_cursor():
    client = OfflineFirestoreClient(project='p')
    ref = client.document('users/u/conversations/c1')
    assert ref.path == 'users/u/conversations/c1'
    query = client.collection('users/u/conversations').order_by('__name__').start_after({'__name__': ref})
    assert isinstance(query, Query)
    wire = query._to_protobuf()
    assert wire.start_at.values[0].reference_value.endswith('/users/u/conversations/c1')


def test_offline_client_without_api_denies_rpc():
    client = OfflineFirestoreClient(project='p')
    with pytest.raises(AssertionError):
        client.document('users/u').get()
    with pytest.raises(AssertionError):
        list(client.collection('users').limit(1).stream())


def test_injected_api_serves_transaction_begin_and_rollback():
    api = MagicMock()
    api.begin_transaction.return_value = SimpleNamespace(transaction=b'txn-1')
    client = OfflineFirestoreClient(project='p', api=api)
    txn = client.transaction()
    assert isinstance(txn, Transaction)
    txn._begin()
    txn._rollback()
    api.begin_transaction.assert_called_once()
    api.rollback.assert_called_once()
    assert not api.commit.called
