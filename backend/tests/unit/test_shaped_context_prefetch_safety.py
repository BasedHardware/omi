"""SDK error paths, per-RPC deadlines, at-use fences, and real executor isolation."""

import asyncio
import json
import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import ServiceUnavailable
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1.types import BatchGetDocumentsResponse, Document, Value

from database import chat as chat_db
from database.chat_context import ChatContextStore
from database import chat_context_prefetch as snapshots
from database.chat_context_reads import get_recent_activity
from utils.executors import db_executor, get_executor_metrics, run_blocking
from utils.messaging import context


@pytest.fixture
def sdk(monkeypatch):
    client = firestore.Client(project='demo-context-safety', credentials=AnonymousCredentials())
    prefix = 'projects/demo-context-safety/databases/(default)/documents/'
    rows = {
        'users/u': {'chat_context_generation': 0},
        'users/u/chat_sessions/s': {
            'id': 's',
            'channel_link_id': 'link',
            'link_generation': 1,
            'shaped_context_revision': 1,
            'shaped_context': 'ciphertext',
        },
        'channel_identities/link': {'active': True, 'uid': 'u', 'generation': 1},
    }
    created, calls = {}, []
    epoch = datetime(2026, 10, 16, tzinfo=timezone.utc)

    def batch_get(*, request, retry, timeout, **kwargs):
        calls.append((request, retry, timeout))
        assert 0 < timeout <= 1.0
        # Reverse response order to enforce the real BatchGet contract.
        for name in reversed(request['documents']):
            path = name.removeprefix(prefix)
            if path not in rows:
                yield BatchGetDocumentsResponse(missing=name, read_time=epoch)
                continue
            row = rows[path]
            mask = request.get('mask')
            fields = {}
            for key, value in row.items():
                if mask is not None and key not in mask.field_paths:
                    continue
                if isinstance(value, bool):
                    fields[key] = Value(boolean_value=value)
                elif isinstance(value, int):
                    fields[key] = Value(integer_value=value)
                else:
                    fields[key] = Value(string_value=value)
            yield BatchGetDocumentsResponse(
                found=Document(name=name, fields=fields, create_time=created.get(path, epoch), update_time=epoch),
                read_time=epoch,
            )

    api = MagicMock()
    api.batch_get_documents.side_effect = batch_get
    monkeypatch.setattr(client, '_firestore_api_internal', api)
    monkeypatch.setattr(snapshots.encryption, 'decrypt', lambda *args: json.dumps({'summary': 'Stored continuity'}))
    messaging = SimpleNamespace(db=client, user=lambda uid: client.collection('users').document(uid))
    yield SimpleNamespace(
        client=client, store=ChatContextStore(messaging=messaging), rows=rows, created=created, epoch=epoch, calls=calls
    )
    client.close()


def test_real_sdk_digest_google_api_error_preserves_original_without_retry(monkeypatch):
    client = firestore.Client(project='demo-context-safety', credentials=AnonymousCredentials())
    error = ServiceUnavailable('synthetic provider failure')

    def broken_stream(*args, **kwargs):
        yield from ()
        raise error

    api = MagicMock()
    api.run_query.side_effect = broken_stream
    monkeypatch.setattr(client, '_firestore_api_internal', api)
    monkeypatch.setattr(chat_db, 'db', client)
    try:
        with pytest.raises(ServiceUnavailable) as caught:
            get_recent_activity('u')
        assert caught.value is error
        api.run_query.assert_called_once()
        assert api.run_query.call_args.kwargs['timeout'] == 1.0
    finally:
        client.close()


def test_snapshot_and_projected_fence_have_explicit_rpc_deadlines(sdk):
    state = sdk.store.load_for_turn('u', 's')
    assert state['summary'] == 'Stored continuity'
    assert len(sdk.calls) == 2
    sdk.store.validate_for_turn('u', 's', state, 0.15)
    assert len(sdk.calls) == 3
    assert sdk.calls[-1][2] == 0.15
    assert set(sdk.calls[-1][0]['mask'].field_paths) == set(snapshots.FENCE_FIELDS)


@pytest.fixture
def shaped():
    from utils.retrieval import agentic, shaped_chat

    return agentic, shaped_chat


@pytest.mark.parametrize(
    'mutation',
    [
        'revoke',
        'delete_session',
        'delete_account',
        'deletion_marker',
        'generation',
        'revision',
        'replace_session',
        'replace_account',
        'replace_link',
    ],
)
def test_mutation_during_setup_cannot_inject_prefetched_summary(monkeypatch, sdk, shaped, mutation):
    agentic, runner = shaped
    outcomes, captured = [], []
    monkeypatch.setattr(context, 'ChatContextStore', lambda: sdk.store)
    monkeypatch.setattr(context, 'recent_activity', lambda *args: [])
    monkeypatch.setattr(context, 'schedule_refresh', lambda *args: None)
    monkeypatch.setattr(context, 'record_fallback', lambda **kw: None)
    monkeypatch.setattr(
        context,
        'CONTEXT_TURNS',
        SimpleNamespace(labels=lambda surface, outcome: SimpleNamespace(inc=lambda: outcomes.append(outcome))),
    )

    class Model:
        model_name = 'gpt-5.6'

        def bind(self, **kwargs):
            return self

        async def astream(self, messages):
            captured.append(str(messages))
            yield SimpleNamespace(content='Answer', tool_calls=[], tool_call_chunks=[], additional_kwargs={})

    monkeypatch.setattr(agentic, 'get_llm', lambda *args, **kwargs: Model())
    monkeypatch.setattr(agentic, 'gpt56_explicit_cache_enabled', lambda: False)

    async def run():
        async with context.preparation_scope('u', 's', ['m']) as pending:
            await asyncio.gather(*pending.tasks)
            if mutation == 'revoke':
                sdk.rows['channel_identities/link']['active'] = False
            elif mutation == 'delete_session':
                del sdk.rows['users/u/chat_sessions/s']
            elif mutation == 'delete_account':
                del sdk.rows['users/u']
            elif mutation == 'deletion_marker':
                sdk.rows['account_deletions/u'] = {'wipe_status': 'queued'}
            elif mutation == 'generation':
                sdk.rows['users/u']['chat_context_generation'] = 1
            elif mutation == 'revision':
                sdk.rows['users/u/chat_sessions/s']['shaped_context_revision'] = 2
            else:
                path = {
                    'replace_session': 'users/u/chat_sessions/s',
                    'replace_account': 'users/u',
                    'replace_link': 'channel_identities/link',
                }[mutation]
                sdk.created[path] = sdk.epoch + timedelta(seconds=1)
            output = []
            # The production agentic runner creates a child task with copied ContextVars.
            await asyncio.create_task(
                runner.run_shaped_chat_stream(
                    '',
                    [{'role': 'user', 'content': 'Request'}],
                    [],
                    {},
                    agentic.AsyncStreamingCallback(),
                    output,
                    agentic.AgentSafetyGuard(),
                    {'user_id': 'u', 'chat_session_id': 's', 'context_message_ids': ['m']},
                )
            )
            assert output == ['Answer'] and 'Stored continuity' not in captured[0]
            assert outcomes == ['degraded']
            assert len(sdk.calls) == 3

    asyncio.run(run())


def test_cancelled_saturated_prefetch_never_queues_or_delays_setup(monkeypatch):
    async def run():
        release = threading.Event()
        entered = asyncio.Event()
        finished = asyncio.Event()
        loop = asyncio.get_running_loop()
        started, ended = [], []
        outcomes = []

        def blocked(*args):
            started.append(True)
            if len(started) == 4:
                loop.call_soon_threadsafe(entered.set)
            try:
                assert release.wait(5), 'test cleanup failed'
                return {'summary': 'Late continuity'}
            finally:
                ended.append(True)
                if len(ended) == 4:
                    loop.call_soon_threadsafe(finished.set)

        store = SimpleNamespace(load_for_turn=blocked)
        monkeypatch.setattr(context, 'recent_activity', blocked)
        monkeypatch.setattr(context, 'record_fallback', lambda **kw: None)
        monkeypatch.setattr(
            context,
            'CONTEXT_TURNS',
            SimpleNamespace(labels=lambda surface, outcome: SimpleNamespace(inc=lambda: outcomes.append(outcome))),
        )
        pending = [context.ContextPreparation('u', 's', ['m'], store=store) for _ in range(32)]
        try:
            await asyncio.wait_for(entered.wait(), 1)
            # A regression using db_executor would occupy all 24 setup workers.
            assert await asyncio.wait_for(run_blocking(db_executor, lambda: 'setup done'), 0.3) == 'setup done'
            for _ in range(12):
                await asyncio.sleep(0)
            metric = next(row for row in get_executor_metrics() if row['name'] == 'context')
            assert metric['active_count'] == 4 and metric['queue_depth'] == 0
            assert metric['queue_capacity'] == 0 and len(started) == 4
            assert pending[-1].take() == {'summary': '', 'digest': ''}
            assert outcomes[-1] == 'summary_pending'
            await asyncio.gather(*(item.close() for item in pending))
            metric = next(row for row in get_executor_metrics() if row['name'] == 'context')
            assert metric['active_count'] == 4  # Cancelling callers does not release running workers.
        finally:
            release.set()
            await asyncio.gather(*(item.close() for item in pending))
            await asyncio.wait_for(finished.wait(), 1)

    asyncio.run(run())


def test_legacy_account_without_generation_survives_an_empty_projection(sdk):
    sdk.rows['users/u'] = {'display_name': 'Synthetic user'}
    state = sdk.store.load_for_turn('u', 's')
    assert state['generation'] == 0
    sdk.store.validate_for_turn('u', 's', state, 0.15)
    assert 'display_name' not in sdk.calls[-1][0]['mask'].field_paths


@pytest.mark.parametrize('path', ['users/u', 'users/u/chat_sessions/s'])
def test_initial_empty_records_keep_the_existing_access_rejection(sdk, path):
    sdk.rows[path] = {}
    with pytest.raises(PermissionError):
        sdk.store.load_for_turn('u', 's')
