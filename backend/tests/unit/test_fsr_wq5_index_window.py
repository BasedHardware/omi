"""Bound historical window work without offset or bookmark-document reads."""

import copy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from google.api_core.datetime_helpers import DatetimeWithNanoseconds
from google.auth.credentials import AnonymousCredentials
from google.cloud.firestore_v1 import Client

from database import memories
from tests.unit.test_external_list_nested_budget import Query, Ref, Snapshot, Store
from tests.unit.test_memory_service_parity import _load_memory_service, _sample_memory_dict
from utils.memory import read_resilience
from utils.memory.index_window import validate_window_cursors
from utils.memory.universal_list_cursor import StreamKeyset
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
    token = first.next_cursor
    remaining = []
    for _ in range(4):
        before = db.physical
        page = service.read_page(UID, limit=1, cursor=token)
        assert db.physical - before <= 2
        remaining.extend(memory.id for memory in page.memories)
        token = page.next_cursor
        if token is None:
            break
    assert remaining == ['a']


def test_legacy_cursor_without_exact_position_restarts_instead_of_guessing_nanoseconds():
    state = SimpleNamespace(
        historical_updated_scan=StreamKeyset(updated_at_us=123456, memory_id='old-boundary'),
        historical_created_scan=None,
    )
    with pytest.raises(ValueError, match='no exact index-window position'):
        validate_window_cursors(state, UID)


def test_all_modern_deep_account_emits_full_pages_without_exhausting_created_stream(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"memory_list_index_window":100}')
    monkeypatch.setenv('MEMORY_ENABLED', 'on')
    mod = _load_memory_service(monkeypatch)
    monkeypatch.setattr(mod, 'read_canonical_scan_page', lambda *args, **kw: ([], True))
    monkeypatch.setattr(memories, 'prepare_memory_for_read', lambda raw, uid: raw)
    db = KeysetStore(rows(5000))
    service = mod.MemoryService(db_client=db)
    monkeypatch.setattr(service, 'canonical_statuses', lambda *args, **kw: {})
    monkeypatch.setattr(read_resilience, '_retry_allowance', read_resilience.RetryAllowance())
    first = service.read_page(UID, limit=7)
    assert [memory.id for memory in first.memories] == [f'm-{i:05}' for i in range(7)]
    assert db.physical == 14
    second = service.read_page(UID, limit=7, cursor=first.next_cursor)
    assert [memory.id for memory in second.memories] == [f'm-{i:05}' for i in range(7, 14)]
    assert db.physical == 28


def test_public_window_seam_clamps_route_max_without_claiming_exhaustion(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"memory_list_index_window":100}')
    db = KeysetStore(rows(1000))
    payloads, positions, exhausted = memories.scan_memory_list_index_window(
        UID,
        order_field='updated_at',
        limit=1000,
        cursor='',
        firestore_client=db,
    )
    assert len(payloads) == len(positions) == db.physical == 500
    assert not exhausted


def test_suppressed_historical_windows_emit_full_canonical_pages(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"memory_list_index_window":100}')
    monkeypatch.setenv('MEMORY_ENABLED', 'on')
    monkeypatch.setenv('OMI_MEMORY_READ_RETRY_BURST', '64')
    monkeypatch.setattr(read_resilience, '_retry_allowance', read_resilience.RetryAllowance())
    mod = _load_memory_service(monkeypatch)
    monkeypatch.setattr(memories, 'prepare_memory_for_read', lambda raw, uid: raw)
    historical_rows = rows(40)
    canonical = [
        mod.MemoryDB.model_validate({**_sample_memory_dict(raw['id']), **raw}) for raw in historical_rows.values()
    ]

    def canonical_page(uid, *, limit, start_after=None, **kw):
        remaining = canonical
        if start_after is not None:
            stamp, memory_id = start_after
            remaining = [m for m in canonical if (-m.updated_at.timestamp(), m.id) > (-stamp.timestamp(), memory_id)]
        chunk = remaining[:limit]
        return [(m, (m.updated_at, m.id)) for m in chunk], len(remaining) <= limit

    monkeypatch.setattr(mod, 'read_canonical_scan_page', canonical_page)
    db = KeysetStore(historical_rows)
    service = mod.MemoryService(db_client=db)
    monkeypatch.setattr(
        service, 'canonical_statuses', lambda uid, ids, **kw: dict.fromkeys(ids, mod.MemoryItemStatus.active)
    )
    ids, token = [], None
    for offset in range(0, 40, 5):
        before = db.physical
        page = service.read_page(UID, limit=5, cursor=token)
        assert [m.id for m in page.memories] == [f'm-{i:05}' for i in range(offset, offset + 5)]
        assert db.physical - before <= 10
        ids.extend(m.id for m in page.memories)
        token = page.next_cursor
        if offset < 35:
            assert token is not None
    # An exactly full raw window may need one final empty read to prove exhaustion.
    if token is not None:
        final = service.read_page(UID, limit=5, cursor=token)
        assert final.memories == []
        assert final.next_cursor is None
    assert len(ids) == len(set(ids)) == 40


def test_historical_window_bound_blocks_older_canonical_head(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"memory_list_index_window":100}')
    monkeypatch.setenv('MEMORY_ENABLED', 'on')
    mod = _load_memory_service(monkeypatch)
    monkeypatch.setattr(memories, 'prepare_memory_for_read', lambda raw, uid: raw)
    canonical = mod.MemoryDB.model_validate({**_sample_memory_dict('older'), 'updated_at': NOW - timedelta(minutes=30)})
    monkeypatch.setattr(
        mod, 'read_canonical_scan_page', lambda *a, **kw: ([(canonical, (canonical.updated_at, canonical.id))], True)
    )
    historical_rows = rows(4)
    for raw in historical_rows.values():
        raw['created_at'] -= timedelta(hours=1)
    # The canonical head lies between the two exhausted bounds. Only the
    # minimum bound is safe; using the older created bound would emit it early.
    service = mod.MemoryService(db_client=KeysetStore(historical_rows))
    monkeypatch.setattr(
        service, 'canonical_statuses', lambda uid, ids, **kw: dict.fromkeys(ids, mod.MemoryItemStatus.active)
    )
    monkeypatch.setattr(read_resilience, '_retry_allowance', read_resilience.RetryAllowance())
    page = service.read_page(UID, limit=2)
    assert page.memories == []
    assert page.next_cursor is not None


@pytest.mark.parametrize('order_field', ['updated_at', 'created_at'])
def test_malformed_historical_order_returns_normal_page(monkeypatch, order_field):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"memory_list_index_window":100}')
    monkeypatch.setenv('MEMORY_ENABLED', 'on')
    mod = _load_memory_service(monkeypatch)
    monkeypatch.setattr(mod, 'read_canonical_scan_page', lambda *a, **kw: ([], True))
    monkeypatch.setattr(memories, 'prepare_memory_for_read', lambda raw, uid: raw)
    raw = {'id': 'bad-order', 'content': 'fact', 'category': 'interesting', order_field: 'malformed'}
    if order_field == 'updated_at':
        raw['created_at'] = datetime.fromtimestamp(0, tz=timezone.utc)
    good = {'id': 'good', 'content': 'fact', 'category': 'interesting', 'created_at': NOW, 'updated_at': NOW}
    # Inject storage snapshots so the timestamp-only query fake need not sort mixed Firestore types.
    monkeypatch.setattr(
        memories,
        '_stream_memory_list_index_window',
        lambda *a, **kw: [Snapshot(f'users/{UID}/memories/{row["id"]}', row) for row in [raw, good] if a[1] in row],
    )
    db = KeysetStore({})
    service = mod.MemoryService(db_client=db)
    monkeypatch.setattr(service, 'canonical_statuses', lambda *a, **kw: {})
    monkeypatch.setattr(read_resilience, '_retry_allowance', read_resilience.RetryAllowance())
    page = service.read_page(UID, limit=5)
    assert [m.id for m in page.memories] == ['good']
    assert not page.truncated
    assert page.next_cursor is None
    _, positions, _ = memories.scan_memory_list_index_window(
        UID, order_field=order_field, limit=5, cursor='', firestore_client=db
    )
    assert positions[0] == (datetime.fromtimestamp(0, tz=timezone.utc), 'bad-order')
