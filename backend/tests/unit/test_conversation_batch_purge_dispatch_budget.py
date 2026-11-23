import asyncio
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import ServiceUnavailable
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1.types import Document, RunQueryResponse

from database import conversation_purge_budget as budget, rpc_deadline
from routers import users


def test_read_limit_precharges_requests_and_settlement_has_its_own_reserve():
    ledger = budget.Dispatch()
    query = SimpleNamespace(limit=100, offset=0)
    run_query = Mock()
    get = Mock()
    client = SimpleNamespace(_firestore_api=SimpleNamespace(run_query=run_query, get_document=get))
    rpc_deadline.bind_firestore_client(client)

    with budget.activate(ledger):
        for _ in range(40):
            client._firestore_api.run_query(request={'structured_query': query})
        for _ in range(96):
            client._firestore_api.get_document(request={})
        with pytest.raises(budget.WorkLimit):
            client._firestore_api.get_document(request={})
        with budget.settling():
            for _ in range(512):
                client._firestore_api.get_document(request={})
            with pytest.raises(TimeoutError):
                client._firestore_api.get_document(request={})

    assert run_query.call_count == 40
    assert get.call_count == 608
    assert all(call.kwargs['retry'] is None for call in run_query.call_args_list)


def test_interrupted_query_never_restarts_at_the_query_layer(monkeypatch):
    client = firestore.Client(project='synthetic', credentials=AnonymousCredentials())
    row = RunQueryResponse(document=Document(name='projects/synthetic/databases/(default)/documents/test/first'))

    def partial_stream():
        yield row
        raise ServiceUnavailable('stream interrupted')

    run_query = Mock(side_effect=lambda **_: partial_stream())
    monkeypatch.setattr(client, '_firestore_api_internal', SimpleNamespace(run_query=run_query))
    rpc_deadline.bind_firestore_client(client)
    ledger = budget.Dispatch()
    with budget.activate(ledger), pytest.raises(ServiceUnavailable):
        list(client.collection('test').limit(100).stream(**budget.stream_options()))
    assert run_query.call_count == 1
    assert ledger.reads == budget.WORK_READS - 100


def test_transaction_factory_uses_one_attempt_only_inside_batch_purge():
    transaction = Mock()
    client = SimpleNamespace(_firestore_api=SimpleNamespace(), transaction=transaction)
    rpc_deadline.bind_firestore_client(client)

    client.transaction()
    with budget.activate(budget.Dispatch()):
        client.transaction()
    assert transaction.call_args_list[0].kwargs == {}
    assert transaction.call_args_list[1].kwargs == {'max_attempts': 1}


def test_executor_callback_expired_before_start_cannot_enter_worker(monkeypatch):
    entered = Mock()
    captured = {}

    async def delay(_pool, callback):
        captured['callback'] = callback
        await asyncio.Future()

    monkeypatch.setattr(users, 'run_blocking', delay)
    ledger = budget.Dispatch(started=time.monotonic() - budget.WORK_SECONDS + 0.01)
    with pytest.raises(TimeoutError, match='expired while queued'):
        asyncio.run(users._run_bounded_batch_purge(entered, 'job', 1, ledger))
    with pytest.raises(budget.WorkLimit):
        captured['callback']()
    entered.assert_not_called()


def test_failed_begin_sends_no_transaction_body_commit_or_rollback(monkeypatch):
    from google.api_core.exceptions import DeadlineExceeded

    from database.batch_pipeline_conversation_purge_scans import _in_transaction

    client = firestore.Client(project='synthetic', credentials=AnonymousCredentials())
    begin = Mock(side_effect=DeadlineExceeded('synthetic begin deadline'))
    commit, rollback = Mock(), Mock()
    api = SimpleNamespace(begin_transaction=begin, commit=commit, rollback=rollback)
    monkeypatch.setattr(client, '_firestore_api_internal', api)
    rpc_deadline.bind_firestore_client(client)
    body = Mock()

    with budget.activate(budget.Dispatch()), pytest.raises((DeadlineExceeded, ValueError)) as error:
        _in_transaction(client, body)
    if isinstance(error.value, ValueError):
        assert isinstance(error.value.__context__, DeadlineExceeded)  # SDK 2.20 masks the error before SCA-2625
    begin.assert_called_once()
    commit.assert_not_called()
    rollback.assert_not_called()
    body.assert_not_called()
