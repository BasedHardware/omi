"""Consent commits before physical cleanup, and scheduled retries resume safely."""

from collections import Counter
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.api_core.exceptions import DeadlineExceeded
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1.types import firestore as firestore_pb

from database import (
    conversations,
    recurring_voice_privacy as scrub,
    recurring_voices,
    rpc_deadline,
    speaker_auto_enroll,
)
from tests.support.dream_firestore import DreamFirestore
from utils.other.timeout import TimeoutMiddleware

UID = 'synthetic-owner'
OWNER = ('users', UID)
TRACE_ID = '1234567890abcdef1234567890abcdef'
CONVERSATIONS = ('a', 'b', 'c', 'd')


def conversation_path(cid):
    return (*OWNER, 'conversations', cid)


@pytest.fixture
def clock(monkeypatch):
    state = SimpleNamespace(now=100.0)
    monkeypatch.setattr(rpc_deadline, 'now', lambda: state.now)
    return state


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setattr(speaker_auto_enroll, 'account_authority_writer_enabled', lambda: False)
    monkeypatch.delenv('PRIVACY_SCRUB_BUDGET_SECONDS', raising=False)
    fake = DreamFirestore()
    fake.rows[OWNER] = {'private_cloud_sync_enabled': True, recurring_voices.INDEX: {'revoked-id': 'token'}}
    for cid in CONVERSATIONS:
        fake.rows[conversation_path(cid)] = {
            'transcript_segments': [{'recurring_voice_id': 'revoked-id', 'text': 'synthetic words'}],
        }
    return fake


def toggle(store, value=False):
    speaker_auto_enroll.update_privacy(
        UID,
        {'private_cloud_sync_enabled': value},
        firestore_client=store,
        request_deadline=rpc_deadline.now() + 20,
        trace_id=TRACE_ID,
    )


def read_segments(store, cid):
    row = store.rows[conversation_path(cid)]
    return conversations.decode_transcript_segments_blob(
        UID,
        row['transcript_segments'],
        bool(row.get('transcript_segments_compressed')),
        require_decryption=True,
    )


def test_privacy_scrub_defers_after_commit_and_readers_hide_revoked_links(store, caplog):
    caplog.set_level('INFO', logger=scrub.__name__)
    toggle(store)
    assert store.rows[OWNER]['private_cloud_sync_enabled'] is False
    assert store.rows[OWNER][scrub.SCRUB_FIELD]['cursor'] is None
    assert not any(len(path) == 4 and path[2] == 'conversations' for path in store.reads)
    assert read_segments(store, 'a')[0]['recurring_voice_id'] == 'revoked-id'
    for reenabled in (False, True):
        if reenabled:
            toggle(store, value=True)
        response_segments = read_segments(store, 'a')
        scrub.filter_segments(UID, response_segments, firestore_client=store)
        assert response_segments == [{'text': 'synthetic words'}]
    lines = [record.getMessage() for record in caplog.records if record.name == scrub.__name__]
    assert [line.split(' phase=')[1].split()[0] for line in lines[:3]] == ['start', 'committed', 'scrub_exhausted']
    assert lines[2].endswith('reason=deferred')
    for line in lines:
        assert f'trace_id={TRACE_ID}' in line
        assert 'elapsed_ms=' in line and 'pages=0 documents=0' in line
        assert all(value not in line for value in (UID, 'revoked-id', 'synthetic words'))


@pytest.mark.parametrize('legacy_index', [False, True])
def test_privacy_scrub_skips_empty_index(store, legacy_index, monkeypatch, caplog):
    caplog.set_level('INFO', logger=scrub.__name__)
    del store.rows[OWNER][recurring_voices.INDEX]
    if legacy_index:
        store.rows[OWNER][recurring_voices.INDEX] = {}
    never_scrub = Mock(side_effect=AssertionError('empty index started a sweep'))
    monkeypatch.setattr(scrub, 'scrub_transcripts', never_scrub)
    toggle(store)
    never_scrub.assert_not_called()
    assert scrub.SCRUB_FIELD not in store.rows[OWNER]
    assert (recurring_voices.INDEX in store.rows[OWNER]) == legacy_index
    assert 'phase=scrub_done' in caplog.text and 'reason=skipped' in caplog.text


def test_privacy_scrub_resumes_after_budget_and_replayed_toggle(store, clock, monkeypatch, caplog):
    caplog.set_level('INFO', logger=scrub.__name__)
    monkeypatch.setenv('PRIVACY_SCRUB_BUDGET_SECONDS', '5')
    monkeypatch.setattr(scrub, 'SCRUB_PAGE_SIZE', 2)
    toggle(store)
    scrub_document = scrub._scrub_document

    def expire_at_second_document(client, user, reference, expected_job):
        if reference.id == 'b':
            clock.now += 5.1
            assert rpc_deadline.remaining() < 0
            raise rpc_deadline.RpcDeadlineExceeded()
        return scrub_document(client, user, reference, expected_job)

    monkeypatch.setattr(scrub, '_scrub_document', expire_at_second_document)
    assert scrub.resume_pending_scrubs(firestore_client=store) == {'visited': 1, 'completed': 0}
    pending = store.rows[OWNER][scrub.SCRUB_FIELD].copy()
    assert pending['cursor'] == 'a'
    toggle(store)
    assert store.rows[OWNER][scrub.SCRUB_FIELD] == pending

    # The cursor is an identity, so a delete of the last processed row cannot
    # derail start_after on the next tick.
    del store.rows[conversation_path('a')]
    monkeypatch.setattr(scrub, '_scrub_document', scrub_document)
    assert scrub.resume_pending_scrubs(firestore_client=store) == {'visited': 1, 'completed': 0}
    assert store.rows[OWNER][scrub.SCRUB_FIELD]['cursor'] == 'c'
    assert scrub.resume_pending_scrubs(firestore_client=store) == {'visited': 1, 'completed': 1}
    assert scrub.resume_pending_scrubs(firestore_client=store) == {'visited': 0, 'completed': 0}
    assert scrub.SCRUB_FIELD not in store.rows[OWNER]
    assert all(read_segments(store, cid) == [{'text': 'synthetic words'}] for cid in ('b', 'c', 'd'))
    writes = Counter(path for tx in store.transactions for path, _ in tx.updates if len(path) == 4)
    assert writes == {conversation_path(cid): 1 for cid in CONVERSATIONS}
    assert 'phase=scrub_exhausted elapsed_ms=5100 pages=1 documents=2' in caplog.text
    assert 'phase=scrub_done elapsed_ms=0 pages=1 documents=1' in caplog.text


def test_privacy_scrub_rollback_switch_runs_inline(store, monkeypatch):
    monkeypatch.setenv('PRIVACY_SCRUB_BUDGET_SECONDS', '0')
    toggle(store)
    assert scrub.SCRUB_FIELD not in store.rows[OWNER]
    assert all(read_segments(store, cid) == [{'text': 'synthetic words'}] for cid in CONVERSATIONS)


def test_privacy_scrub_superseded_cursor_cannot_advance_new_revocations(store):
    toggle(store)
    previous = store.rows[OWNER][scrub.SCRUB_FIELD].copy()
    toggle(store, value=True)
    store.rows[OWNER][recurring_voices.INDEX] = {'second-revocation': 'token'}
    toggle(store)
    pending = store.rows[OWNER][scrub.SCRUB_FIELD].copy()
    assert pending['version'] > previous['version'] and pending['cursor'] is None

    assert scrub._resume(store, store.collection('users').document(UID), previous, rpc_deadline.now() + 10) is False
    assert store.rows[OWNER][scrub.SCRUB_FIELD] == pending
    assert read_segments(store, 'a')[0]['recurring_voice_id'] == 'revoked-id'
    assert scrub.resume_pending_scrubs(firestore_client=store) == {'visited': 1, 'completed': 1}


def privacy_http_client(monkeypatch, store):
    from routers import users as users_router

    monkeypatch.setattr(speaker_auto_enroll._client, 'get_data_plane_firestore_client', lambda: store)
    app = FastAPI()
    app.include_router(users_router.router)
    app.add_middleware(TimeoutMiddleware, methods_timeout={'POST': 600})
    app.dependency_overrides[users_router.auth.get_current_user_uid] = lambda: UID
    return TestClient(app)


def test_private_cloud_sync_returns_200_before_scrub(store, monkeypatch):
    client = privacy_http_client(monkeypatch, store)
    response = client.post('/v1/users/private-cloud-sync', params={'value': 'false'})
    assert response.status_code == 200
    assert response.json() == {'status': 'ok', 'message': None}
    assert store.rows[OWNER]['private_cloud_sync_enabled'] is False
    assert store.rows[OWNER][scrub.SCRUB_FIELD]['cursor'] is None
    assert read_segments(store, 'a')[0]['recurring_voice_id'] == 'revoked-id'


@pytest.mark.parametrize('expiry', ['before_begin', 'begin', 'before_commit', 'commit'])
def test_privacy_write_deadline_returns_typed_503(expiry, monkeypatch, clock, caplog):
    caplog.set_level('INFO', logger=scrub.__name__)
    monkeypatch.setattr(speaker_auto_enroll, 'account_authority_writer_enabled', lambda: False)
    sdk = firestore.Client(project='synthetic-deadline-project', credentials=AnonymousCredentials())

    def read(request, **_kwargs):
        name = request['documents'][0]
        if expiry == 'before_commit' and name.endswith(f'/users/{UID}'):
            clock.now += 21
        return iter([firestore_pb.BatchGetDocumentsResponse(missing=name)])

    calls = {
        'begin_transaction': Mock(return_value=firestore_pb.BeginTransactionResponse(transaction=b'txn')),
        'batch_get_documents': Mock(side_effect=read),
        'commit': Mock(side_effect=DeadlineExceeded('synthetic provider timeout')),
        'rollback': Mock(),
    }
    if expiry == 'begin':
        calls['begin_transaction'].side_effect = DeadlineExceeded('synthetic begin timeout')
    sdk._firestore_api_internal = SimpleNamespace(**calls)
    client = privacy_http_client(monkeypatch, sdk)

    if expiry == 'before_begin':

        def resolve_after_deadline():
            clock.now += 21
            return sdk

        monkeypatch.setattr(speaker_auto_enroll._client, 'get_data_plane_firestore_client', resolve_after_deadline)
    # The handler and middleware share the same monotonic clock.
    monkeypatch.setattr('utils.other.timeout.time', SimpleNamespace(monotonic=lambda: clock.now, time=lambda: 0.0))
    result = client.post(
        '/v1/users/private-cloud-sync',
        params={'value': 'false'},
        headers={'X-Cloud-Trace-Context': f'{TRACE_ID}/42;o=1'},
    )
    assert result.status_code == 503
    assert result.json() == {'detail': {'code': 'privacy_write_unavailable', 'retryable': True}}
    assert result.headers['Retry-After'] == '1'
    if expiry == 'before_begin':
        calls['begin_transaction'].assert_not_called()
    else:
        assert calls['begin_transaction'].call_args.kwargs['timeout'] == 20
    assert all(call.kwargs['retry'] is None for call in calls['batch_get_documents'].call_args_list)
    if expiry == 'commit':
        calls['commit'].assert_called_once()
        assert calls['commit'].call_args.kwargs['timeout'] == 20
    else:
        calls['commit'].assert_not_called()
    if expiry == 'before_commit':
        assert calls['rollback'].call_args.kwargs['timeout'] == rpc_deadline.ROLLBACK_GRACE_SECONDS
    assert 'phase=start' in caplog.text and f'trace_id={TRACE_ID}' in caplog.text
    assert 'phase=committed' not in caplog.text and 'phase=scrub_done' not in caplog.text
