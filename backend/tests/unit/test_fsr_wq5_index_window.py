"""Bound historical window work without offset or bookmark-document reads."""

import copy
from datetime import datetime, timedelta, timezone

import pytest
from google.api_core.datetime_helpers import DatetimeWithNanoseconds
from google.auth.credentials import AnonymousCredentials
from google.cloud.firestore_v1 import Client

from database import memories
from tests.unit.test_external_list_nested_budget import Query, Ref, Snapshot, Store
from tests.unit.test_memory_service_parity import _load_memory_service
from utils.memory import read_resilience
from utils.memory.index_window_cursor import BookmarkDict, decode_cursor, encode_cursor, query_scope

UID = 'owner'
NOW = datetime(2026, 10, 20, tzinfo=timezone.utc)


def stamp_key(value):
    stamp = value.timestamp_pb() if isinstance(value, DatetimeWithNanoseconds) else None
    return (stamp.seconds, stamp.nanos) if stamp else (int(value.timestamp()), value.microsecond * 1000)


class KeysetQuery(Query):
    def document(self, doc_id):
        return KeysetRef(self.store, self.path + '/' + doc_id)

    def stream(self, **kwargs):
        rows = [(path, row) for path, row in self.store.rows.items() if path.rsplit('/', 1)[0] == self.path]
        fields = [field for field, _ in self.orders if field != '__name__']
        rows = [(path, row) for path, row in rows if all(field in row for field in fields)]
        field = fields[0]
        # Firestore: timestamp DESC, explicit name ASC (implicit DESC on legacy query).
        ascending_name = len(self.orders) > 1 and self.orders[-1][1] != 'DESCENDING'

        def key(path, row):
            seconds, nanos = stamp_key(row[field])
            return (-seconds, -nanos, path if ascending_name else tuple(-ord(c) for c in path))

        rows.sort(key=lambda row: key(*row))
        if self.after is not None:
            if isinstance(self.after, dict):
                anchor = (self.after['__name__'].path, {field: self.after[field]})
            else:
                anchor = (self.after.reference.path, self.after.to_dict())
            rows = [row for row in rows if key(*row) > key(*anchor)]
        selected = rows[self.skip : self.skip + self.n]
        self.store.physical += min(self.skip, len(rows)) + len(selected)
        self.store.windows.append((self.path, self.orders, self.n, len(selected)))
        return iter(Snapshot(path, row) for path, row in selected)


class KeysetRef(Ref):
    def collection(self, path):
        return KeysetQuery(self.store, self.path + '/' + path)


class KeysetStore(Store):
    def collection(self, path):
        return KeysetQuery(self, path)


def rows(count, *, legacy=False):
    return {
        f'users/{UID}/memories/m-{i:05}': {
            'id': f'm-{i:05}',
            'content': f'fact {i}',
            'category': 'interesting',
            'created_at': NOW - timedelta(seconds=i),
            **({} if legacy and i % 2 else {'updated_at': NOW - timedelta(seconds=i)}),
        }
        for i in range(count)
    }


def window(db, limit, cursor=None):
    return memories._stream_memory_list_index_window(
        db.collection('users').document(UID).collection('memories'),
        'updated_at',
        limit,
        uid=UID,
        cursor=cursor,
    )


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv('MEMORY_V3_CURSOR_SECRET', 'wq5-unit-secret')
    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)


def test_off_query_reads_and_payloads_identical(monkeypatch):
    baseline, gated = KeysetStore(rows(800)), KeysetStore(rows(800))
    expected = window(baseline, 700)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"memory_list_index_window":0}')
    actual = window(gated, 700, 'ignored')
    assert [doc.to_dict() for doc in actual] == [doc.to_dict() for doc in expected]
    assert gated.windows == baseline.windows
    assert gated.physical == baseline.physical == 700


@pytest.mark.parametrize('depth', [0, 100, 4000])
@pytest.mark.parametrize('page_size', [1, 7, 100, 500])
def test_on_read_cap_is_page_size_at_every_depth(monkeypatch, depth, page_size):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"memory_list_index_window":100}')
    db = KeysetStore(rows(5001))
    token = encode_cursor(
        NOW - timedelta(seconds=depth), f'm-{depth:05}', query_scope({'uid': UID, 'order': 'updated_at'})
    )
    result = window(db, page_size, token)
    assert len(result) == db.physical == page_size
    assert result[0].id == f'm-{depth+1:05}'
    assert db.windows[-1][2] == page_size


@pytest.mark.parametrize('cursor', [None, 'invalid', 'expired', 'other-user'])
def test_invalid_absent_expired_cursor_uses_old_window(monkeypatch, cursor):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"memory_list_index_window":100}')
    if cursor in {'expired', 'other-user'}:
        scope = query_scope({'uid': UID if cursor == 'expired' else 'another', 'order': 'updated_at'})
        token = encode_cursor(NOW, 'm-00000', scope)
        if cursor == 'expired':
            monkeypatch.setenv('MEMORY_V3_CURSOR_TTL_SECONDS', '1')
            monkeypatch.setattr('utils.memory.index_window_cursor.time.time', lambda: NOW.timestamp() + 10000000)
        cursor = token
    db = KeysetStore(rows(800))
    assert len(window(db, 700, cursor)) == db.physical == 700
    assert len(db.windows[-1][1]) == 1


def test_nanosecond_bookmark_survives_sdk_copy_and_deleted_boundary(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"memory_list_index_window":100}')
    stamp = DatetimeWithNanoseconds.from_rfc3339('2026-10-20T00:00:00.123456789Z')
    scope = query_scope({'uid': UID, 'order': 'updated_at'})
    token = encode_cursor(stamp, 'a', scope)
    decoded, _ = decode_cursor(token, scope)
    assert decoded.nanosecond == copy.deepcopy(BookmarkDict({'ts': decoded}))['ts'].nanosecond == 123456789
    db = KeysetStore({f'users/{UID}/memories/{key}': {'updated_at': stamp} for key in ['b', 'c']})
    assert [doc.id for doc in window(db, 1, token)] == ['b']


def test_mixed_service_cursor_caps_two_windows_and_survives_visibility_changes(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"memory_list_index_window":100}')
    monkeypatch.setenv('MEMORY_ENABLED', 'on')
    mod = _load_memory_service(monkeypatch)
    monkeypatch.setattr(mod, 'read_canonical_scan_page', lambda *args, **kw: ([], True))
    monkeypatch.setattr(memories, 'prepare_memory_for_read', lambda raw, uid: raw)
    db = KeysetStore(rows(40, legacy=True))
    service = mod.MemoryService(db_client=db)
    monkeypatch.setattr(service, 'canonical_statuses', lambda *args, **kw: {})
    # Each request has a fresh admission, without wall-clock sleeps in this loop.
    monkeypatch.setenv('OMI_MEMORY_READ_RETRY_BURST', '64')
    monkeypatch.setattr(read_resilience, '_retry_allowance', read_resilience.RetryAllowance())
    ids, token = [], None
    for iteration in range(40):
        before = db.physical
        page = service.read_page(UID, limit=3, cursor=token)
        assert db.physical - before <= 6
        ids.extend(memory.id for memory in page.memories)
        token = page.next_cursor
        if iteration == 0:
            # Remove the emitted boundary; hide an unseen row and edit another's content.
            db.rows.pop(f'users/{UID}/memories/{ids[-1]}')
            db.rows[f'users/{UID}/memories/m-00005']['user_review'] = False
            db.rows[f'users/{UID}/memories/m-00006']['content'] = 'edited'
        if token is None:
            break
    else:
        pytest.fail('cursor did not terminate')
    assert ids == [f'm-{i:05}' for i in range(40) if i != 5]
    assert len(ids) == len(set(ids))


def test_real_sdk_cursor_compilation_keeps_nanoseconds_without_a_document_read():
    client = Client(project='wq5-hermetic', credentials=AnonymousCredentials())
    collection = client.collection('users').document(UID).collection('memories')
    stamp = DatetimeWithNanoseconds.from_rfc3339('2026-10-20T00:00:00.123456789Z')
    query = (
        collection.order_by('updated_at', direction='DESCENDING')
        .order_by('__name__')
        .start_after(BookmarkDict({'updated_at': stamp, '__name__': collection.document('deleted-boundary')}))
    )
    compiled = query._to_protobuf()
    assert compiled.start_at.values[0].timestamp_value.nanosecond == 123456789
    assert compiled.start_at.values[1].reference_value.endswith('/memories/deleted-boundary')


def test_mixed_nanosecond_boundaries_follow_timestamp_before_id(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"memory_list_index_window":100}')
    monkeypatch.setenv('MEMORY_ENABLED', 'on')
    mod = _load_memory_service(monkeypatch)
    monkeypatch.setattr(mod, 'read_canonical_scan_page', lambda *args, **kw: ([], True))
    monkeypatch.setattr(memories, 'prepare_memory_for_read', lambda raw, uid: raw)
    older = DatetimeWithNanoseconds.from_rfc3339('2026-10-20T00:00:00.123456788Z')
    newer = DatetimeWithNanoseconds.from_rfc3339('2026-10-20T00:00:00.123456789Z')
    db = KeysetStore(
        {
            f'users/{UID}/memories/a': {
                'id': 'a',
                'content': 'a',
                'category': 'interesting',
                'updated_at': older,
                'created_at': older,
            },
            f'users/{UID}/memories/z': {'id': 'z', 'content': 'z', 'category': 'interesting', 'created_at': newer},
        }
    )
    service = mod.MemoryService(db_client=db)
    monkeypatch.setattr(service, 'canonical_statuses', lambda *args, **kw: {})
    monkeypatch.setattr(read_resilience, '_retry_allowance', read_resilience.RetryAllowance())
    first = service.read_page(UID, limit=1)
    assert [memory.id for memory in first.memories] == ['z']
    second = service.read_page(UID, limit=1, cursor=first.next_cursor)
    assert [memory.id for memory in second.memories] == ['a']
    assert db.physical <= 4
