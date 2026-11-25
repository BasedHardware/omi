"""Hermetic tests for ``retention check`` (fake Firestore, fake GCS, fake admin API)."""

import argparse
import json
import zlib
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from database.support_actions import ActionContext, ActionRecord
from utils.support import retention

UID = 'uid-123'


# --- fakes ----------------------------------------------------------------


class _Snap:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return None if self._data is None else dict(self._data)


class _Doc:
    def __init__(self, store, path):
        self._store = store
        self._path = path

    def get(self):
        self._store.gets.append(self._path)
        return _Snap(self._path.rsplit('/', 1)[-1], self._store.docs.get(self._path))

    def collection(self, name):
        return _Collection(self._store, f'{self._path}/{name}')


class _Query:
    def __init__(self, collection, filters=(), limit=None):
        self._collection = collection
        self._filters = list(filters)
        self._limit = limit

    def where(self, *, filter):
        return _Query(self._collection, self._filters + [filter], self._limit)

    def order_by(self, field):
        return self

    def limit(self, n):
        return _Query(self._collection, self._filters, n)

    def stream(self):
        store = self._collection._store
        store.queries.append({'path': self._collection._path, 'filters': self._filters, 'limit': self._limit})
        rows = []
        prefix = self._collection._path + '/'
        for path, data in sorted(store.docs.items(), key=lambda item: item[1].get('created_at') if item[1] else 0):
            if not path.startswith(prefix) or '/' in path[len(prefix) :]:
                continue
            ok = True
            for f in self._filters:
                value = data.get(f.field_path)
                if f.op_string == '>=' and not value >= f.value:
                    ok = False
                if f.op_string == '<' and not value < f.value:
                    ok = False
            if ok:
                rows.append(_Snap(path.rsplit('/', 1)[-1], data))
        return iter(rows[: self._limit] if self._limit else rows)


class _Collection(_Query):
    def __init__(self, store, path):
        self._store = store
        self._path = path
        super().__init__(self)

    def document(self, doc_id):
        return _Doc(self._store, f'{self._path}/{doc_id}')


class FakeFirestore:
    _database_string = 'projects/test-project/databases/(default)'

    def __init__(self, docs=None):
        self.docs = dict(docs or {})
        self.gets = []
        self.queries = []

    def collection(self, name):
        return _Collection(self, name)


def _blob(size, created, deleted=None):
    return SimpleNamespace(size=size, time_created=created, time_deleted=deleted)


class FakeStorage:
    def __init__(self, objects=None, soft_deleted=None, no_soft_delete=()):
        self.objects = objects or {}  # (bucket, prefix) -> [blob]
        self.soft = soft_deleted or {}
        self.no_soft_delete = set(no_soft_delete)
        self.calls = []

    def list_blobs(self, bucket, prefix, versions=False, soft_deleted=False):
        assert not (versions and soft_deleted)
        self.calls.append((bucket, prefix, versions, soft_deleted))
        if soft_deleted:
            if bucket in self.no_soft_delete:
                raise RuntimeError('soft delete policy is not enabled')
            return iter(self.soft.get((bucket, prefix), []))
        return iter(self.objects.get((bucket, prefix), []))


class FakeAdmin:
    def get_database(self, name):
        return SimpleNamespace(
            point_in_time_recovery_enablement=SimpleNamespace(name='POINT_IN_TIME_RECOVERY_ENABLED'),
            version_retention_period=SimpleNamespace(total_seconds=lambda: 604800.0),
            earliest_version_time=datetime(2026, 11, 13, tzinfo=timezone.utc),
        )

    def list_backup_schedules(self, parent):
        return [
            SimpleNamespace(
                name=f'{parent}/backupSchedules/daily',
                retention=SimpleNamespace(seconds=1209600),
                weekly_recurrence=None,
            )
        ]


class FailingAdmin:
    def get_database(self, name):
        raise PermissionError('denied')


def _conv(created, **extra):
    data = {
        'created_at': created,
        'started_at': created,
        'finished_at': created,
        'status': 'completed',
        'discarded': False,
        'structured': {'title': 'Secret Meeting Title'},
        'data_protection_level': 'standard',
    }
    data.update(extra)
    return data


def _args(conversation=None, month=None):
    return argparse.Namespace(uid=UID, conversation=conversation, month=month)


def _ctx():
    return ActionContext(ticket='T1', actor='support person', reason='retention question', agent='agent-1')


def _run(firestore, storage, admin=None, **kwargs):
    record = ActionRecord(action_id='a1')
    with patch.object(retention, '_firestore_client', return_value=firestore), patch.object(
        retention, '_storage_client', return_value=storage
    ), patch.object(retention, '_firestore_admin_client', return_value=admin or FakeAdmin()), patch.object(
        retention, '_private_cloud_sync_bucket', return_value='omi-private-cloud-sync'
    ), patch.object(
        retention, '_memories_recordings_bucket', return_value='memories-recordings'
    ):
        result = retention.check(_args(**kwargs), _ctx(), record)
    return result, record


def _aug(day):
    return datetime(2025, 8, day, tzinfo=timezone.utc)


# --- tests ----------------------------------------------------------------


def test_register_adds_retention_check():
    parser = argparse.ArgumentParser()
    groups = parser.add_subparsers(dest='group')
    retention.register(groups)
    args = parser.parse_args(['retention', 'check', UID, '--month', '2025-12'])
    assert args.action == 'check' and args.handler is retention.check
    assert args.month == (datetime(2025, 12, 1, tzinfo=timezone.utc), datetime(2026, 1, 1, tzinfo=timezone.utc))
    with pytest.raises(SystemExit):
        parser.parse_args(['retention', 'check', UID, '--month', '2025-13'])


def test_refuses_without_filter():
    fs = FakeFirestore()
    with pytest.raises(retention.RetentionCheckError):
        _run(fs, FakeStorage())
    assert fs.gets == [] and fs.queries == []


def test_month_query_selects_only_that_utc_month():
    base = f'users/{UID}/conversations'
    fs = FakeFirestore(
        {
            f'{base}/jul': _conv(datetime(2025, 7, 31, 23, 59, tzinfo=timezone.utc)),
            f'{base}/aug1': _conv(_aug(1)),
            f'{base}/aug31': _conv(datetime(2025, 8, 31, 23, 59, tzinfo=timezone.utc)),
            f'{base}/sep': _conv(datetime(2025, 9, 1, tzinfo=timezone.utc)),
        }
    )
    result, record = _run(fs, FakeStorage(), month='2025-08')
    assert [c['id'] for c in result['conversations']] == ['aug1', 'aug31']
    (query,) = fs.queries
    assert query['limit'] == retention.CONVERSATION_CAP + 1
    assert {(f.op_string, f.value) for f in query['filters']} == {
        ('>=', datetime(2025, 8, 1, tzinfo=timezone.utc)),
        ('<', datetime(2025, 9, 1, tzinfo=timezone.utc)),
    }
    assert result['capped'] is False
    # 2 query rows + legal_holds + deletion gate + account_deletions
    assert result['firestore_reads'] == 5
    # 4 prefixes x (versions + soft-deleted) per conversation
    assert result['listing_calls'] == 16
    assert record.summary['conversations_checked'] == 2


def test_single_conversation_reports_fields_and_compressed_segment_count():
    segments = [{'text': 'a'}, {'text': 'b'}, {'text': 'c'}]
    fs = FakeFirestore(
        {
            f'users/{UID}/conversations/c1': _conv(
                _aug(2),
                transcript_segments=zlib.compress(json.dumps(segments).encode()),
                transcript_segments_compressed=True,
            )
        }
    )
    result, _ = _run(fs, FakeStorage(), conversation='c1')
    (conv,) = result['conversations']
    assert conv['id'] == 'c1' and conv['exists'] is True
    assert conv['title'] == 'Secret Meeting Title'
    assert conv['conversation_status'] == 'completed' and conv['discarded'] is False
    assert conv['transcript_present'] is True and conv['segment_count'] == 3
    assert fs.queries == []
    assert [p['prefix'] for p in conv['storage']] == [
        f'chunks/{UID}/c1/',
        f'raw-live/{UID}/c1/',
        f'playback/{UID}/c1/',
        f'{UID}/c1.wav',
    ]


def test_enhanced_conversation_is_reported_encrypted():
    fs = FakeFirestore(
        {
            f'users/{UID}/conversations/c1': _conv(
                _aug(2), data_protection_level='enhanced', transcript_segments='opaque'
            )
        }
    )
    result, _ = _run(fs, FakeStorage(), conversation='c1')
    assert result['conversations'][0]['segment_count'] == 'encrypted'
    assert result['conversations'][0]['transcript_present'] is True


def test_missing_conversation_is_reported_not_raised():
    result, record = _run(FakeFirestore(), FakeStorage(), conversation='gone')
    assert result['conversations'][0]['exists'] is False
    assert record.summary['conversations_checked'] == 1


def test_cap_limits_and_reports():
    base = f'users/{UID}/conversations'
    docs = {f'{base}/c{i:03d}': _conv(datetime(2025, 8, 1, 0, 0, i % 60, i, tzinfo=timezone.utc)) for i in range(205)}
    result, record = _run(FakeFirestore(docs), FakeStorage(), month='2025-08')
    assert len(result['conversations']) == retention.CONVERSATION_CAP
    assert result['capped'] is True and record.summary['capped'] is True


def test_audio_present_vs_absent_and_object_kinds():
    base = f'users/{UID}/conversations'
    fs = FakeFirestore({f'{base}/with': _conv(_aug(3)), f'{base}/without': _conv(_aug(4))})
    t1, t2, t3 = _aug(3), _aug(5), _aug(6)
    storage = FakeStorage(
        objects={
            ('omi-private-cloud-sync', f'chunks/{UID}/with/'): [_blob(100, t2), _blob(50, t1, deleted=t3)],
            ('memories-recordings', f'{UID}/with.wav'): [_blob(10, t3)],
        },
        soft_deleted={('omi-private-cloud-sync', f'chunks/{UID}/with/'): [_blob(7, t1)]},
    )
    result, record = _run(fs, storage, month='2025-08')
    by_id = {c['id']: c for c in result['conversations']}
    chunks = by_id['with']['storage'][0]
    assert chunks['objects'] == 3 and chunks['bytes'] == 157
    assert (chunks['live'], chunks['noncurrent'], chunks['soft_deleted']) == (1, 1, 1)
    assert chunks['earliest_created'] == t1.isoformat() and chunks['latest_created'] == t2.isoformat()
    assert all(p['objects'] == 0 for p in by_id['without']['storage'])
    assert record.summary['conversations_with_audio'] == 1
    assert record.summary['objects_total'] == 4


def test_bucket_without_soft_delete_is_tolerated():
    fs = FakeFirestore({f'users/{UID}/conversations/c1': _conv(_aug(2))})
    storage = FakeStorage(
        objects={('memories-recordings', f'{UID}/c1.wav'): [_blob(10, _aug(2))]},
        no_soft_delete={'memories-recordings'},
    )
    result, _ = _run(fs, storage, conversation='c1')
    storage_by_bucket = {p['bucket'] + ':' + p['prefix']: p for p in result['conversations'][0]['storage']}
    memories = storage_by_bucket[f'memories-recordings:{UID}/c1.wav']
    assert memories['objects'] == 1
    assert memories['soft_delete'].startswith('unavailable')
    assert storage_by_bucket[f'omi-private-cloud-sync:chunks/{UID}/c1/']['soft_delete'] == 'listed'


def test_account_state_reports_hold_gate_and_marker():
    fs = FakeFirestore(
        {
            f'users/{UID}/conversations/c1': _conv(_aug(2)),
            f'legal_holds/{UID}': {'active': True, 'issuer': 'counsel', 'matter': 'm-1'},
            f'legal_hold_deletion_gates/{UID}': {'kind': 'hold', 'state': 'blocked', 'started_at': _aug(1), 'x': 1},
            f'account_deletions/{UID}': {'state': 'pending'},
        }
    )
    result, _ = _run(fs, FakeStorage(), conversation='c1')
    account = result['account']
    assert account['legal_hold'] == {'active': True, 'issuer': 'counsel', 'matter': 'm-1'}
    assert account['deletion_gate'] == {'kind': 'hold', 'state': 'blocked', 'started_at': _aug(1), 'finished_at': None}
    assert account['account_deletion_marker'] is True
    empty, _ = _run(FakeFirestore(), FakeStorage(), conversation='c1')
    assert empty['account'] == {'legal_hold': None, 'deletion_gate': None, 'account_deletion_marker': False}


def test_backup_coverage_known_and_failed_lookup():
    fs = FakeFirestore({f'users/{UID}/conversations/c1': _conv(_aug(2))})
    ok, _ = _run(fs, FakeStorage(), conversation='c1')
    assert ok['backups']['coverage'] == 'known'
    assert ok['backups']['pitr_enablement'] == 'POINT_IN_TIME_RECOVERY_ENABLED'
    assert ok['backups']['version_retention_seconds'] == 604800.0
    assert ok['backups']['backup_schedules'][0]['retention_seconds'] == 1209600.0

    failed, record = _run(fs, FakeStorage(), admin=FailingAdmin(), conversation='c1')
    assert failed['backups'] == {
        'coverage': 'unknown',
        'database': 'projects/test-project/databases/(default)',
        'error_type': 'PermissionError',
    }
    assert record.summary['conversations_checked'] == 1


def test_summary_holds_only_content_free_counts():
    fs = FakeFirestore(
        {
            f'users/{UID}/conversations/conv-secret-id': _conv(_aug(2)),
            f'legal_holds/{UID}': {'active': True, 'issuer': 'Named Lawyer'},
        }
    )
    storage = FakeStorage(objects={('omi-private-cloud-sync', f'chunks/{UID}/conv-secret-id/'): [_blob(5, _aug(2))]})
    result, record = _run(fs, storage, conversation='conv-secret-id')
    assert set(record.summary) == {
        'conversations_checked',
        'conversations_with_audio',
        'objects_total',
        'listing_calls',
        'firestore_reads',
        'capped',
    }
    assert all(isinstance(v, (bool, int)) for v in record.summary.values())
    blob = json.dumps(record.summary)
    for secret in ('Secret Meeting Title', 'conv-secret-id', UID, 'Named Lawyer', 'omi-private-cloud-sync'):
        assert secret not in blob
    assert record.summary['listing_calls'] == result['listing_calls'] == len(storage.calls) == 8
    assert record.summary['firestore_reads'] == result['firestore_reads'] == len(fs.gets) == 4


def test_check_ignores_apply_and_writes_nothing():
    fs = FakeFirestore({f'users/{UID}/conversations/c1': _conv(_aug(2))})
    before = dict(fs.docs)
    record = ActionRecord(action_id='a1')
    ctx = ActionContext(ticket='T1', actor='a', reason='r', agent='g', apply=True)
    with patch.object(retention, '_firestore_client', return_value=fs), patch.object(
        retention, '_storage_client', return_value=FakeStorage()
    ), patch.object(retention, '_firestore_admin_client', return_value=FakeAdmin()):
        retention.check(_args(conversation='c1'), ctx, record)
    assert fs.docs == before
