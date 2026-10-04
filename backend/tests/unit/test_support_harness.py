"""Hermetic support authorization, HTTP, privacy, and audit contracts."""

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from models.support import SupportLookupResponse, SupportTraceResponse, SupportTraceRow
from models.users import PlanLimits, Subscription
from scripts import export_openapi
from utils.support_trace import project_support_trace

NOW = datetime(2026, 10, 4, tzinfo=timezone.utc)
EMAIL = 'customer@example.com'


class Snapshot:
    def __init__(self, data, document_id='recording'):
        self.exists, self.data, self.id = data is not None, data, document_id

    def to_dict(self):
        return self.data


class Firestore:
    def __init__(self):
        self.access = {'role': 'support:read'}
        self.subscription = {'plan': 'basic'}
        self.reads, self.writes, self.query_events, self.rows = [], [], [], []
        self.audit_fails = False

    def collection(self, name):
        return Reference(self, (name,))


class Reference:
    def __init__(self, store, path):
        self.store, self.path = store, path
        self.fields, self.query_limit = None, None

    def document(self, document_id='generated-audit-id'):
        return Reference(self.store, (*self.path, document_id))

    def collection(self, collection_id):
        return Reference(self.store, (*self.path, collection_id))

    def get(self, field_paths=None):
        self.store.reads.append((self.path, field_paths))
        if self.path == ('supportData', 'support-caller'):
            return Snapshot(self.store.access)
        if self.path == ('users', 'target-customer'):
            assert field_paths in (['subscription'], ['last_active_at', 'last_active_platform'])
            data = {
                'subscription': self.store.subscription,
                'last_active_at': NOW,
                'last_active_platform': 'macos',
                'phone': 'SECRET-PHONE',
                'memories': ['SECRET-MEMORY'],
            }
            if self.store.subscription is None:
                data.pop('subscription')
            return Snapshot({key: data[key] for key in field_paths if key in data})
        if self.path == ('users', 'target-customer', 'fair_use_state', 'current'):
            return Snapshot({'stage': 'none', 'events': ['SECRET-EVENT']})
        raise AssertionError(f'Unexpected Firestore read: {self.path}')

    def set(self, row, **kwargs):
        assert self.path[0] == 'support_audit_log', 'Customer writes are forbidden'
        if self.store.audit_fails:
            raise RuntimeError('SECRET-PROVIDER-ERROR')
        self.store.writes.append(row)

    def where(self, *, filter):
        self.store.query_events.append(('where', filter.field_path, filter.op_string, filter.value))
        return self

    def order_by(self, field, direction):
        self.store.query_events.append(('order_by', field, direction))
        return self

    def select(self, fields):
        self.fields = fields
        self.store.query_events.append(('select', fields))
        return self

    def limit(self, limit):
        self.query_limit = limit
        self.store.query_events.append(('limit', limit))
        return self

    def offset(self, offset):
        assert offset == 0
        return self

    def stream(self):
        assert self.path == ('users', 'target-customer', 'conversations')
        assert self.fields is not None and self.query_limit == 51
        rows = self.store.rows
        for event in self.store.query_events:
            if event[0] == 'where':
                _, field, operator, value = event
                if operator == '>=':
                    rows = [row for row in rows if row[field] >= value]
                elif operator == '<=':
                    rows = [row for row in rows if row[field] <= value]
                else:
                    raise AssertionError('Unexpected query filter')
        for row in sorted(rows, key=lambda row: row['started_at'], reverse=True)[: self.query_limit]:
            projected = {field: row[field] for field in self.fields if field in row}
            if 'postprocessing.status' in self.fields and 'postprocessing' in row:
                projected['postprocessing'] = {'status': row['postprocessing'].get('status')}
            yield Snapshot(projected, row['id'])


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.setenv('ENCRYPTION_SECRET', 'a' * 32)
    from database import _client
    from routers import support
    from utils import support_auth

    store = Firestore()
    monkeypatch.setattr(_client, '_firestore_client', store)
    verify = Mock(return_value={'uid': 'support-caller'})
    monkeypatch.setattr(support_auth.auth, 'verify_id_token', verify)
    resolve = Mock(return_value=SimpleNamespace(uid='target-customer'))
    monkeypatch.setattr(support.auth, 'get_user_by_email', resolve)
    usage = Mock(return_value={'transcription_seconds': 125, 'memories_created': 4})
    monkeypatch.setattr(support.user_usage, 'get_monthly_usage_stats', usage)
    app = FastAPI()
    app.include_router(support.router)
    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client, app=app, router=support, store=store, verify=verify, resolve=resolve, usage=usage
        )


def lookup(harness):
    return harness.client.get(
        '/v1/support/lookup', params={'email': EMAIL}, headers={'Authorization': 'Bearer firebase-token'}
    )


def trace(harness, **params):
    query = {'email': EMAIL, 'from': NOW.isoformat(), 'to': (NOW + timedelta(days=1)).isoformat(), **params}
    return harness.client.get('/v1/support/trace', params=query, headers={'Authorization': 'Bearer firebase-token'})


@pytest.mark.parametrize('authorization', [None, '', 'Basic firebase-token', 'Bearer', 'Bearer one two'])
def test_missing_or_malformed_token(harness, authorization):
    headers = {} if authorization is None else {'Authorization': authorization}
    response = harness.client.get('/v1/support/lookup', params={'email': EMAIL}, headers=headers)
    assert response.status_code == 401
    harness.verify.assert_not_called()
    assert harness.store.reads == harness.store.writes == []


@pytest.mark.parametrize(
    'access',
    [
        None,
        {},
        {'role': 'admin'},
        {'role': 'support:write'},
        {'role': 'support:read', 'expires_at': NOW - timedelta(days=1)},
        {'role': 'support:read', 'expires_at': datetime(2099, 1, 1)},
        {'role': 'support:read', 'expires_at': '2099-01-01T00:00:00Z'},
        {'role': 'support:read', 'expires_at': None},
    ],
)
def test_allowlist_denies_invalid_grants(harness, access):
    harness.store.access = access
    assert lookup(harness).status_code == 403
    harness.resolve.assert_not_called()
    assert harness.store.writes == []


def test_admin_impersonation_is_not_support_auth(harness, monkeypatch):
    monkeypatch.setenv('ADMIN_KEY', 'legacy-admin-key')
    harness.verify.side_effect = ValueError('Invalid Firebase token')
    response = harness.client.get(
        '/v1/support/lookup',
        params={'email': EMAIL},
        headers={
            'Authorization': 'Bearer legacy-admin-keytarget-customer',
            'X-Admin-Key': 'legacy-admin-key',
            'X-Admin-Uid': 'forged-admin',
        },
    )
    assert response.status_code == 401
    harness.verify.assert_called_once_with('legacy-admin-keytarget-customer')
    assert harness.store.reads == harness.store.writes == []


def test_admin_header_alone_cannot_authenticate(harness):
    assert (
        harness.client.get('/v1/support/lookup', params={'email': EMAIL}, headers={'X-Admin-Key': 'secret'}).status_code
        == 401
    )


def test_lookup_allowlist_and_hashed_audit(harness):
    harness.store.access['expires_at'] = datetime(2099, 1, 1, tzinfo=timezone.utc)
    response = harness.client.get(
        '/v1/support/lookup',
        params={'email': ' Customer@Example.com '},
        headers={'Authorization': 'Bearer firebase-token', 'X-Admin-Uid': 'forged-admin'},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert set(data) == set(SupportLookupResponse.model_fields)
    assert data['email'] == EMAIL and data['uid'] == 'target-customer'
    assert data['plan'] == 'basic' and data['transcription_seconds_used'] == 125
    assert data['transcription_seconds_remaining'] == max(0, data['transcription_seconds_limit'] - 125)
    for forbidden in ('phone', 'transcript', 'summary', 'audio_url', 'memories', 'stripe_subscription_id', 'events'):
        assert forbidden not in data
    assert 'SECRET' not in response.text
    harness.resolve.assert_called_once_with(EMAIL)
    uid, month = harness.usage.call_args.args
    assert uid == 'target-customer' and month.utcoffset() == timedelta(0)
    assert (month.year, month.month) == (datetime.now(timezone.utc).year, datetime.now(timezone.utc).month)
    assert len(harness.store.writes) == 1
    row = harness.store.writes[0]
    assert set(row) == {'actor_uid', 'action', 'target_uid', 'email_sha256', 'at'}
    assert row['actor_uid'] == 'support-caller' and row['action'] == 'lookup'
    assert row['email_sha256'] == hashlib.sha256(EMAIL.encode()).hexdigest()
    assert EMAIL not in str(row) and 'firebase-token' not in str(row)


@pytest.mark.parametrize('plan', ['unlimited', 'architect'])
def test_unlimited_limit_is_null(harness, plan):
    harness.store.subscription = {'plan': plan}
    response = lookup(harness)
    assert response.status_code == 200, response.text
    assert response.json()['transcription_seconds_limit'] is None
    assert response.json()['transcription_seconds_remaining'] is None


def test_finite_zero_is_not_unlimited(harness):
    harness.store.subscription['limits'] = {'transcription_seconds': 0}
    response = lookup(harness)
    assert response.status_code == 200
    assert response.json()['transcription_seconds_limit'] == response.json()['transcription_seconds_remaining'] == 0


@pytest.mark.parametrize('stored', [None, {'plan': 'free'}])
def test_subscription_reader_does_not_create_or_migrate(harness, stored):
    harness.store.subscription = stored
    from testing.import_isolation import AutoMockModule, stub_modules

    factory = AutoMockModule('utils.subscription')
    factory.get_default_basic_subscription = Mock(
        return_value=Subscription(limits=PlanLimits(transcription_seconds=1200))
    )
    with stub_modules({'utils.subscription': factory}):
        response = lookup(harness)
    assert response.status_code == 200, response.text
    assert response.json()['plan'] == 'basic'
    assert len(harness.store.writes) == 1
    assert harness.store.subscription == stored


def test_unknown_email(harness):
    harness.resolve.side_effect = harness.router.auth.UserNotFoundError('SECRET-AUTH-ERROR')
    response = lookup(harness)
    assert response.status_code == 404 and response.json()['detail'] == 'Account not found'
    assert harness.store.writes == []


@pytest.mark.parametrize('email', ['', ' ', 'one@example.com,two@example.com', '*@example.com', 'not-an-email'])
def test_exact_email_validation(harness, email):
    response = harness.client.get(
        '/v1/support/lookup', params={'email': email}, headers={'Authorization': 'Bearer firebase-token'}
    )
    assert response.status_code == 422
    harness.resolve.assert_not_called()
    assert harness.store.writes == []


@pytest.mark.parametrize(
    'window',
    [
        {'from': '2026-10-04T00:00:00'},
        {'to': '2026-10-05T00:00:00'},
        {'to': (NOW + timedelta(days=7, seconds=1)).isoformat()},
        {'to': NOW.isoformat()},
        {'to': (NOW - timedelta(seconds=1)).isoformat()},
        {'from': '1780000000'},
    ],
)
def test_trace_window_validation(harness, window):
    assert trace(harness, **window).status_code == 422
    harness.resolve.assert_not_called()
    assert harness.store.writes == []


def recording(**fields):
    return {
        'id': 'recording',
        'started_at': NOW,
        'finished_at': NOW + timedelta(seconds=45),
        'status': 'completed',
        **fields,
    }


def test_discarded_or_deleted_is_not_saved():
    discarded = project_support_trace(recording(discarded=True))
    deleted = project_support_trace(recording(deleted=True))
    assert discarded.captured and discarded.synced and not discarded.saved and discarded.discarded
    assert deleted.captured and deleted.synced and not deleted.saved and deleted.deleted
    assert 'SECRET' not in discarded.model_dump_json()
    row = project_support_trace(
        recording(
            audio_files=[{'path': 'gs://SECRET-BUCKET/SECRET-AUDIO', 'url': 'SECRET-URL'}],
            transcript='SECRET-TRANSCRIPT',
            structured={'overview': 'SECRET-STRUCTURE'},
            summary='SECRET-SUMMARY',
        )
    )
    data = row.model_dump(mode='json')
    assert data['captured'] and data['synced'] and data['processed'] and data['saved']
    assert data['audio_present'] and data['has_transcript'] and not data['failed']
    assert data['duration_seconds'] == 45
    assert set(data) == set(SupportTraceRow.model_fields)
    assert not {'transcript', 'structured', 'summary', 'audio_files'} & data.keys()
    assert 'SECRET' not in row.model_dump_json()


@pytest.mark.parametrize(
    'status,post_status,processed,saved,failed,stage',
    [
        ('completed', None, True, True, False, None),
        ('completed', 'not_started', True, True, False, None),
        ('completed', 'in_progress', False, False, False, None),
        ('processing', 'completed', True, False, False, None),
        ('failed', None, False, False, True, 'process'),
        ('completed', 'failed', False, False, True, 'process'),
        ('failed', 'completed', True, False, True, 'save'),
    ],
)
def test_projection_lifecycle_truth_table(status, post_status, processed, saved, failed, stage):
    row = project_support_trace(
        recording(status=status, postprocessing={'status': post_status, 'error': 'SECRET-ERROR'}, error='SECRET-ERROR')
    )
    assert (row.processed, row.saved, row.failed, row.failure_stage) == (processed, saved, failed, stage)
    assert 'SECRET' not in row.model_dump_json()


@pytest.mark.parametrize('field', ['transcript', 'transcript_segments', 'segments'])
def test_transcript_presence_only(field):
    row = project_support_trace(recording(**{field: 'SECRET-TRANSCRIPT'}))
    assert row.has_transcript and 'SECRET' not in row.model_dump_json()


@pytest.mark.parametrize('marker,expected', [(True, True), (False, False), (None, False)])
def test_payload_free_storage_presence(marker, expected):
    row = project_support_trace(recording(transcript_segments_compressed=marker))
    assert row.has_transcript is expected


def test_trace_denies_missing_support_grant(harness):
    harness.store.access = None
    assert trace(harness).status_code == 403
    harness.resolve.assert_not_called()
    assert harness.store.query_events == harness.store.writes == []


def test_allowlist_storage_failure_is_sanitized(harness, monkeypatch):
    from utils import support_auth

    monkeypatch.setattr(support_auth, 'get_support_access', Mock(side_effect=RuntimeError('SECRET-ERROR')))
    response = lookup(harness)
    assert response.status_code == 503 and 'SECRET' not in response.text
    harness.resolve.assert_not_called()
    assert harness.store.writes == []


def test_trace_window_filters_server_rows(harness):
    harness.store.rows = [
        recording(id='before', started_at=NOW - timedelta(seconds=1)),
        recording(id='inside', transcript_segments_compressed=True),
        recording(id='after', started_at=NOW + timedelta(days=1, seconds=1)),
    ]
    response = trace(harness)
    assert response.status_code == 200
    assert [row['conversation_id'] for row in response.json()['rows']] == ['inside']
    assert not response.json()['truncated']


def test_trace_real_reader_bounds_masks_and_audits(harness):
    harness.store.rows = [recording(id=str(index), started_at=NOW + timedelta(seconds=index)) for index in range(51)]
    harness.store.rows[50].update(
        transcript='SECRET-TRANSCRIPT',
        transcript_segments_compressed=True,
        structured={'overview': 'SECRET-SUMMARY'},
        photos=['SECRET-PHOTO'],
    )
    response = trace(harness)
    assert response.status_code == 200, response.text
    data = response.json()
    assert set(data) == {'email', 'uid', 'from', 'to', 'truncated', 'rows'}
    assert len(data['rows']) == 50 and data['truncated']
    assert [row['conversation_id'] for row in data['rows']] == [str(index) for index in range(50, 0, -1)]
    assert data['rows'][0]['has_transcript']
    assert 'SECRET' not in response.text
    selected = next(event[1] for event in harness.store.query_events if event[0] == 'select')
    assert not {
        'structured',
        'summary',
        'photos',
        'error',
        'postprocessing',
        'transcript',
        'transcript_segments',
        'segments',
    } & set(selected)
    assert 'discarded' in selected and 'deleted' in selected
    assert ('limit', 51) in harness.store.query_events
    assert len(harness.store.writes) == 1
    audit = harness.store.writes[0]
    assert audit['action'] == 'trace' and audit['window_from'] == NOW and audit['window_to'] == NOW + timedelta(days=1)
    assert audit['email_sha256'] == hashlib.sha256(EMAIL.encode()).hexdigest()
    assert EMAIL not in str(audit)


def test_trace_seven_days_empty_and_offset_normalization(harness):
    response = trace(harness, **{'from': '2026-10-04T07:00:00+07:00', 'to': (NOW + timedelta(days=7)).isoformat()})
    assert response.status_code == 200
    assert response.json()['rows'] == [] and not response.json()['truncated']
    assert harness.store.writes[0]['window_from'] == NOW


@pytest.mark.parametrize('action', ['lookup', 'trace'])
def test_audit_failure_fails_closed(harness, action):
    harness.store.audit_fails = True
    response = lookup(harness) if action == 'lookup' else trace(harness)
    assert response.status_code == 503 and 'SECRET' not in response.text and 'rows' not in response.json()


def test_metadata_decorators_skip_content(harness):
    from database.helpers import prepare_for_read, with_photos

    decrypt = Mock(side_effect=AssertionError('Must not decode content'))
    photos = Mock(side_effect=AssertionError('Must not read photos'))

    @prepare_for_read(decrypt)
    @with_photos(photos)
    def reader(uid, *, metadata_only=False):
        return [{'id': 'recording'}]

    assert reader('target-customer', metadata_only=True) == [{'id': 'recording'}]
    decrypt.assert_not_called()
    photos.assert_not_called()


def test_private_get_only_router_and_main_registration(harness):
    assert {route.path for route in harness.router.router.routes} == {'/v1/support/lookup', '/v1/support/trace'}
    for route in harness.router.router.routes:
        assert route.methods == {'GET'} and route.tags == ['support'] and not route.include_in_schema
    assert export_openapi.public_contract_routes(harness.app) == []
    assert export_openapi.app_client_contract_routes(harness.app) == []
    assert export_openapi.integration_public_contract_routes(harness.app) == []
    assert harness.app.openapi()['paths'] == {}
    assert 'app.include_router(support.router)' in (Path(__file__).resolve().parents[2] / 'main.py').read_text()


@pytest.mark.parametrize('model', [SupportLookupResponse, SupportTraceRow, SupportTraceResponse])
def test_response_models_forbid_extras(model):
    assert model.model_config['extra'] == 'forbid'
    with pytest.raises(ValidationError):
        model.model_validate({'transcript': 'SECRET-TRANSCRIPT'})
