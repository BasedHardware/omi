"""Exercise the calendar HTTP route with real Firestore 2.20 transaction encoding."""

from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.api_core.exceptions import Aborted, DeadlineExceeded, InvalidArgument
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1 import _helpers, types

from database import calendar_meetings as calendar_db
from database import firestore_transaction_retry
from database.document_ids import calendar_meeting_doc_id
from routers.calendar_meetings import auth, router


class MeetingFirestoreRPCs:
    def __init__(self):
        self.rows = {}
        self.active = set()
        self.started = []
        self.begin_error = None
        self.read_error = None
        self.commit_error = None
        self.rollback_error = None
        self.lose_commit_response = False

    def begin_transaction(self, *, request, metadata, retry, timeout):
        assert retry is None and 0 < timeout <= 5
        if self.begin_error:
            error, self.begin_error = self.begin_error, None
            raise error
        transaction = str(len(self.started)).encode()
        self.started.append(transaction)
        self.active.add(transaction)
        return types.BeginTransactionResponse(transaction=transaction)

    def batch_get_documents(self, *, request, metadata, retry, timeout):
        assert retry is None and 0 < timeout <= 5
        assert request['transaction'] in self.active
        if self.read_error:
            raise self.read_error
        (name,) = request['documents']
        if name in self.rows:
            return iter([types.BatchGetDocumentsResponse(found=types.Document(name=name, fields=self.rows[name]))])
        return iter([types.BatchGetDocumentsResponse(missing=name)])

    def commit(self, *, request, metadata, retry, timeout):
        assert retry is None and 0 < timeout <= 5
        assert request['transaction'] in self.active
        if self.commit_error:
            error, self.commit_error = self.commit_error, None
            raise error
        (write,) = request['writes']
        assert write.update_mask.field_paths
        self.rows.setdefault(write.update.name, {}).update(write.update.fields)
        if self.lose_commit_response:
            self.lose_commit_response = False
            raise DeadlineExceeded('commit response lost')
        self.active.remove(request['transaction'])
        return types.CommitResponse()

    def rollback(self, *, request, metadata, retry, timeout):
        assert retry is None and 0 < timeout <= 0.25
        self.active.remove(request['transaction'])
        if self.rollback_error:
            raise self.rollback_error


@pytest.fixture
def calendar_client(monkeypatch):
    db = firestore.Client(project='calendar-test', credentials=AnonymousCredentials())
    rpcs = MeetingFirestoreRPCs()
    monkeypatch.setattr(db, '_firestore_api_internal', rpcs)
    monkeypatch.setattr(calendar_db, 'db', db)
    # Force the lookup to see a miss on both calls, as with concurrent submissions
    # that both looked up a new event before either entered the transaction.
    monkeypatch.setattr(calendar_db, 'get_meeting_id_by_calendar_event', lambda *args: None)
    monkeypatch.setattr(firestore_transaction_retry, 'equal_jitter_delay', lambda *args: 0)
    app = FastAPI()
    app.dependency_overrides[auth.get_current_user_uid] = lambda: 'test-user'
    app.include_router(router)
    return TestClient(app), rpcs


def post(client, **updates):
    return client.post(
        '/v1/calendar/meetings',
        json={
            'calendar_source': 'google_calendar',
            'calendar_event_id': 'event-1',
            'title': 'First title',
            'start_time': '2026-11-23T08:00:00Z',
            'end_time': '2026-11-23T08:30:00Z',
            **updates,
        },
    )


def test_calendar_meeting_persists_and_duplicate_merges(calendar_client):
    client, rpcs = calendar_client
    first = post(client)
    assert first.status_code == 200
    meeting_id = calendar_meeting_doc_id('test-user', 'google_calendar', 'event-1')
    assert first.json()['meeting_id'] == meeting_id
    (name,) = rpcs.rows
    first_fields = _helpers.decode_dict(rpcs.rows[name], calendar_db.db)
    assert first_fields['title'] == 'First title'
    rpcs.rows[name]['server_owned'] = types.Value(string_value='keep')
    duplicate = post(client, title='Updated title')
    assert duplicate.status_code == 200
    assert duplicate.json()['meeting_id'] == meeting_id
    assert list(rpcs.rows) == [name]
    fields = _helpers.decode_dict(rpcs.rows[name], calendar_db.db)
    assert fields['created_at'] == first_fields['created_at']
    assert fields['server_owned'] == 'keep'
    assert fields['title'] == 'Updated title'


@pytest.mark.parametrize('stage', ['begin', 'read', 'commit'])
def test_calendar_meeting_retries_a_fresh_transaction(calendar_client, monkeypatch, stage):
    client, rpcs = calendar_client
    expired = InvalidArgument('The referenced transaction has expired or is no longer valid.')
    rpcs.rollback_error = expired
    if stage == 'begin':
        rpcs.begin_error = Aborted('begin contention')
    elif stage == 'read':
        read = rpcs.batch_get_documents

        def fail_first_read(**kwargs):
            if kwargs['request']['transaction'] == b'0':
                raise Aborted('read contention')
            return read(**kwargs)

        monkeypatch.setattr(rpcs, 'batch_get_documents', fail_first_read)
    else:
        rpcs.commit_error = expired
    response = post(client)
    assert response.status_code == 200
    assert rpcs.started == ([b'0'] if stage == 'begin' else [b'0', b'1'])
    assert len(rpcs.rows) == 1
    assert not rpcs.active


def test_calendar_meeting_defers_when_attempts_are_exhausted(calendar_client):
    client, rpcs = calendar_client
    rpcs.read_error = Aborted('read contention')
    response = post(client)
    assert response.status_code == 503
    assert response.headers['Retry-After'] == '1'
    assert rpcs.started == [b'0', b'1', b'2']
    assert not rpcs.rows
    assert not rpcs.active


def test_calendar_meeting_defers_when_elapsed_budget_is_exhausted(calendar_client, monkeypatch):
    client, rpcs = calendar_client
    clock = [100.0]
    monkeypatch.setattr(calendar_db, 'time', Mock(monotonic=lambda: clock[0]))
    begin = rpcs.begin_transaction

    def slow_begin(**kwargs):
        response = begin(**kwargs)
        clock[0] += 5.0
        return response

    monkeypatch.setattr(rpcs, 'begin_transaction', slow_begin)
    response = post(client)
    assert response.status_code == 503
    assert rpcs.started == [b'0']
    assert not rpcs.rows


def test_calendar_meeting_duplicate_after_ambiguous_commit(calendar_client):
    client, rpcs = calendar_client
    rpcs.lose_commit_response = True
    response = post(client)
    assert response.status_code == 503
    assert rpcs.started == [b'0']
    (name,) = rpcs.rows
    created_at = rpcs.rows[name]['created_at']
    duplicate = post(client)
    assert duplicate.status_code == 200
    assert list(rpcs.rows) == [name]
    assert rpcs.rows[name]['created_at'] == created_at
