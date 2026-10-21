"""WQ4: real list builders, billed read counts, cursor and lifecycle contracts."""

import copy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from google.api_core.datetime_helpers import DatetimeWithNanoseconds
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from config import firestore_read_levers as levers
from database import conversations as db
from utils import conversation_page_cursor as codec
from utils.other.list_budget import ListReadBudget

T0 = datetime(2026, 10, 19, tzinfo=timezone.utc)


def rows(count=20, *, tied=False):
    return [
        dict(
            id=f'{count - i:03d}',
            created_at=T0 if tied else T0 - timedelta(seconds=i),
            started_at=T0 - timedelta(seconds=i),
            discarded=False,
            has_photos=False,
            transcript_segments=[],
            structured={},
            data_protection_level='standard',
        )
        for i in range(count)
    ]


class Snapshot:
    update_time = None

    def __init__(self, row):
        self.row = copy.deepcopy(row)
        self.id = row['id']

    def to_dict(self):
        return copy.deepcopy(self.row)


class CountingQuery:
    def __init__(self, data, counts=None, *, filters=(), orders=(), size=None, skip=0, bookmark=None, fields=None):
        self.data = data
        self.counts = counts if counts is not None else {'reads': 0, 'offsets': [], 'streams': []}
        self.filters, self.orders = filters, orders
        self.size, self.skip, self.bookmark, self.fields = size, skip, bookmark, fields
        self.on_read = None

    def clone(self, **kwargs):
        query = CountingQuery(
            self.data,
            self.counts,
            filters=self.filters,
            orders=self.orders,
            size=self.size,
            skip=self.skip,
            bookmark=self.bookmark,
            fields=self.fields,
        )
        query.__dict__.update(kwargs)
        query.on_read = self.on_read
        return query

    def collection(self, name):
        return self

    def document(self, name):
        return self

    def where(self, *, filter):
        return self.clone(filters=(*self.filters, filter))

    def order_by(self, field, direction=None):
        assert direction == firestore.Query.DESCENDING
        return self.clone(orders=(*self.orders, field))

    def select(self, fields):
        return self.clone(fields=fields)

    def limit(self, size):
        return self.clone(size=size)

    def offset(self, skip):
        self.counts['offsets'].append(skip)
        return self.clone(skip=skip)

    def start_after(self, bookmark):
        assert self.skip == 0
        if isinstance(bookmark, Snapshot):
            bookmark = {self.orders[0]: bookmark.row[self.orders[0]], '__name__': bookmark.id}
        assert set(bookmark) == {self.orders[0], '__name__'}
        return self.clone(bookmark=bookmark)

    def stream(self, **kwargs):
        self.counts['streams'].append(kwargs)
        data = list(self.data)
        for f in self.filters:

            def match(row):
                value = row
                for field in f.field_path.split('.'):
                    value = value.get(field) if isinstance(value, dict) else None
                if f.op_string == '==':
                    return value == f.value
                if f.op_string == 'in':
                    return value in f.value
                if f.op_string == '>=':
                    return value is not None and value >= f.value
                if f.op_string == '<=':
                    return value is not None and value <= f.value
                raise AssertionError(f.op_string)

            data = [row for row in data if match(row)]
        field = self.orders[0]
        data.sort(key=lambda row: (row[field], row['id']), reverse=True)
        if self.bookmark:
            key = (self.bookmark[field], self.bookmark['__name__'])
            data = [row for row in data if (row[field], row['id']) < key]
        self.counts['reads'] += min(self.skip, len(data))
        data = data[self.skip :]
        if self.size is not None:
            data = data[: self.size]
        for row in data:
            self.counts['reads'] += 1
            if self.on_read:
                self.on_read(row)
            yield Snapshot(row)


@pytest.fixture(autouse=True)
def off(monkeypatch):
    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)


@pytest.fixture
def enable(monkeypatch):
    # Production registry belongs to the integrator; emulate that registration.
    monkeypatch.setattr(levers, 'KNOWN_LEVERS', levers.KNOWN_LEVERS | {'conversation_list_cursor'})
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"conversation_list_cursor":100}')


def budget(max_documents=10000):
    return ListReadBudget(deadline_monotonic=100, max_documents=max_documents, clock=lambda: 0)


def fetch(monkeypatch, data, *, uid='u', photo=False, **kwargs):
    query = CountingQuery(data)
    monkeypatch.setattr(db, 'db', query)
    call = db.get_conversations if photo else db.get_conversations_without_photos
    result = call(uid, **kwargs)
    return result, query.counts


@pytest.mark.parametrize('include_discarded', [False, True])
def test_read_count_page_one_vs_four(monkeypatch, enable, include_discarded):
    data = rows()
    monkeypatch.delenv('FIRESTORE_READ_LEVERS')
    off_reads = []
    expected = None
    for offset in (0, 6):
        b = budget()
        expected, counts = fetch(
            monkeypatch, data, limit=2, offset=offset, include_discarded=include_discarded, budget=b
        )
        off_reads.append(counts['reads'])
        assert b.docs_scanned == counts['reads']
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"conversation_list_cursor":100}')
    token = None
    on_reads = []
    for page in range(4):
        b = budget()
        result, counts = fetch(
            monkeypatch,
            data,
            limit=2,
            offset=page * 2,
            include_discarded=include_discarded,
            cursor=token,
            page_envelope=True,
            budget=b,
        )
        token = result['next_cursor']
        on_reads.append(counts['reads'])
        assert b.docs_scanned == counts['reads']
        if page:
            assert counts['offsets'] == []
    assert off_reads == [2, 8]
    assert on_reads == [2, 2, 2, 2]
    assert result['conversations'] == expected


@pytest.mark.parametrize('photo', [False, True])
def test_unregistered_new_lever_is_safe_and_off_shape_unchanged(monkeypatch, photo):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"conversation_list_cursor":100}')
    result, counts = fetch(monkeypatch, rows(), photo=photo, limit=2, offset=6, cursor='invalid', page_envelope=True)
    assert isinstance(result, list)
    assert len(result) == 2 and counts['reads'] == 8


@pytest.mark.parametrize('photo', [False, True])
def test_registered_but_unset_lever_ignores_cursor_and_envelope(monkeypatch, enable, photo):
    monkeypatch.delenv('FIRESTORE_READ_LEVERS')
    original, counts = fetch(monkeypatch, rows(), photo=photo, limit=2, offset=2)
    result, new_counts = fetch(
        monkeypatch, rows(), photo=photo, limit=2, offset=2, cursor='invalid', page_envelope=True
    )
    assert result == original and new_counts == counts


@pytest.mark.parametrize('photo', [False, True])
def test_envelope_after_hydration_and_legacy_offset_fallback(monkeypatch, enable, photo):
    first, counts = fetch(monkeypatch, rows(), photo=photo, limit=2, offset=6, page_envelope=True)
    legacy, legacy_counts = fetch(monkeypatch, rows(), photo=photo, limit=2, offset=6)
    assert set(first) == {'conversations', 'next_cursor'}
    assert first['conversations'] == legacy
    assert counts['reads'] == legacy_counts['reads'] == 8
    second, counts = fetch(
        monkeypatch, rows(), photo=photo, limit=2, offset=100000, page_envelope=True, cursor=first['next_cursor']
    )
    assert [row['id'] for row in second['conversations']] == ['012', '011']
    assert counts['reads'] == 2
    if photo:
        assert all(row['photos'] == [] for row in second['conversations'])


@pytest.mark.parametrize('invalid', ['', '???', 'a' * 5000, 42, [], {}])
def test_invalid_cursor_falls_back_with_warning(monkeypatch, enable, caplog, invalid):
    result, counts = fetch(monkeypatch, rows(), limit=2, offset=6, page_envelope=True, cursor=invalid)
    expected, _ = fetch(monkeypatch, rows(), limit=2, offset=6)
    assert result['conversations'] == expected and counts['reads'] == 8
    assert 'fallback' in caplog.text and 'cursor' in caplog.text


@pytest.mark.parametrize('change', ['expired', 'tampered', 'user', 'filter', 'order', 'visibility'])
def test_cursor_rejects_expiry_tampering_and_scope_changes(monkeypatch, enable, caplog, change):
    first, _ = fetch(monkeypatch, rows(), limit=2, page_envelope=True)
    token = first['next_cursor']
    kwargs = {}
    if change == 'expired':
        issued = codec.time.time()
        monkeypatch.setattr(codec.time, 'time', lambda: issued + 3601)
    elif change == 'tampered':
        token = ('A' if token[0] != 'A' else 'B') + token[1:]
    elif change == 'user':
        kwargs['uid'] = 'another-user'
    elif change == 'filter':
        kwargs['starred'] = False
    elif change == 'visibility':
        kwargs['include_discarded'] = True
    elif change == 'order':
        kwargs.update(photo=True, start_date=T0 - timedelta(days=1), date_field='started_at')
    result, counts = fetch(monkeypatch, rows(), limit=2, offset=6, page_envelope=True, cursor=token, **kwargs)
    expected, _ = fetch(monkeypatch, rows(), limit=2, offset=6, **kwargs)
    assert result['conversations'] == expected
    assert 'fallback' in caplog.text and 'cursor' in caplog.text
    assert counts['offsets'] == ([] if kwargs.get('include_discarded') else [6])


@pytest.mark.parametrize('include_discarded', [False, True])
def test_ties_deleted_bookmark_and_insertion_do_not_duplicate(monkeypatch, enable, include_discarded):
    data = rows(10, tied=True)
    first, _ = fetch(monkeypatch, data, limit=2, include_discarded=include_discarded, page_envelope=True)
    anchor = first['conversations'][-1]['id']
    data[:] = [row for row in data if row['id'] != anchor]
    data.insert(0, dict(data[0], id='new'))
    second, counts = fetch(
        monkeypatch,
        data,
        limit=3,
        offset=500,
        include_discarded=include_discarded,
        cursor=first['next_cursor'],
        page_envelope=True,
    )
    assert [row['id'] for row in second['conversations']] == ['008', '007', '006']
    assert counts['reads'] == 3


@pytest.mark.parametrize('hidden', ['deleted', 'dream_duplicate_of', 'rule_discard', 'discarded'])
def test_visibility_flip_during_page_fills_without_duplication_or_skips(monkeypatch, enable, hidden):
    data = rows(10)
    first, _ = fetch(monkeypatch, data, limit=2, page_envelope=True)
    query = CountingQuery(data)

    def flip(row):
        if row['id'] != '008':
            return
        if hidden == 'rule_discard':
            row['relevance_decision'] = {
                'verdict': 'discard',
                'decided_by': 'rule',
                'reason': 'empty_transcript',
            }
            row['status'] = 'completed'
        else:
            row[hidden] = 'donor' if hidden == 'dream_duplicate_of' else True

    query.on_read = flip
    monkeypatch.setattr(db, 'db', query)
    second = db.get_conversations_without_photos(
        'u', limit=2, offset=200, cursor=first['next_cursor'], page_envelope=True
    )
    assert [row['id'] for row in second['conversations']] == ['007', '006']
    assert query.counts['reads'] == 3
    third, _ = fetch(monkeypatch, data, limit=2, cursor=second['next_cursor'], page_envelope=True)
    assert [row['id'] for row in third['conversations']] == ['005', '004']


def test_hidden_skip_cap_advances_empty_page(monkeypatch, enable):
    data = rows(100)
    first, _ = fetch(monkeypatch, data, limit=2, page_envelope=True)
    for row in data[2:80]:
        row['deleted'] = True
    result, counts = fetch(monkeypatch, data, limit=2, cursor=first['next_cursor'], page_envelope=True)
    assert result['conversations'] == []
    assert counts['reads'] == db._RULE_DISCARD_PAGE_SKIP_CAP + 1
    assert result['next_cursor']
    next_page, _ = fetch(monkeypatch, data, limit=2, cursor=result['next_cursor'], page_envelope=True)
    assert [row['id'] for row in next_page['conversations']] == ['020', '019']


def test_cursor_budget_honest_prefix_and_resume(monkeypatch, enable):
    data = rows()
    first, _ = fetch(monkeypatch, data, limit=2, page_envelope=True)
    b = budget(1)
    result, counts = fetch(
        monkeypatch, data, limit=4, offset=100000, budget=b, cursor=first['next_cursor'], page_envelope=True
    )
    assert [row['id'] for row in result['conversations']] == ['018']
    assert b.truncated and b.docs_scanned == counts['reads'] == 2
    resumed, _ = fetch(monkeypatch, data, limit=2, cursor=result['next_cursor'], page_envelope=True)
    assert [row['id'] for row in resumed['conversations']] == ['017', '016']
    assert counts['streams'][0]['timeout'] == 100
    assert 'retry' in counts['streams'][0]


def test_empty_cursor_page_and_metadata_only(monkeypatch, enable):
    first, _ = fetch(monkeypatch, rows(2), limit=2, page_envelope=True)
    last, counts = fetch(monkeypatch, rows(2), limit=2, cursor=first['next_cursor'], page_envelope=True)
    assert last == {'conversations': [], 'next_cursor': None}
    assert counts['reads'] == 0
    metadata, _ = fetch(
        monkeypatch, rows(2), photo=True, limit=2, metadata_only=True, cursor='invalid', page_envelope=True
    )
    assert isinstance(metadata, list)


def test_codec_preserves_nanoseconds_and_configurable_expiry(monkeypatch):
    stamp = DatetimeWithNanoseconds.from_rfc3339('2026-10-19T00:00:00.123456789Z')
    monkeypatch.setattr(codec.time, 'time', lambda: 1000)
    token = codec.encode_cursor(stamp, 'a', 'scope')
    decoded, doc_id = codec.decode_cursor(token, 'scope')
    assert decoded.nanosecond == 123456789 and doc_id == 'a'
    monkeypatch.setenv('FSR_CONVERSATION_CURSOR_TTL_SECONDS', '2')
    monkeypatch.setattr(codec.time, 'time', lambda: 1003)
    with pytest.raises(ValueError):
        codec.decode_cursor(token, 'scope')


def test_sdk_value_cursor_compiles_without_bookmark_read():
    client = firestore.Client(project='cursor-unit-test', credentials=AnonymousCredentials())
    query = client.collection('users').document('u').collection('conversations')
    query = query.where(filter=firestore.FieldFilter('discarded', '==', False))
    query = query.order_by('created_at', direction=firestore.Query.DESCENDING)
    query = query.order_by('__name__', direction=firestore.Query.DESCENDING)
    # A real Firestore stamp has microsecond precision; use BookmarkDict because the
    # SDK deep-copies the bookmark and plain-dict deepcopy truncates the ordering key.
    stamp = DatetimeWithNanoseconds.from_rfc3339('2026-10-19T00:00:00.123456Z')
    bookmark = codec.BookmarkDict({'created_at': stamp, '__name__': 'a'})
    proto = query.start_after(bookmark).limit(2)._to_protobuf()
    assert not proto.start_at.before
    assert proto.start_at.values[0]._pb.timestamp_value.nanos == 123456000
    assert proto.start_at.values[1].reference_value.endswith('/users/u/conversations/a')
    assert proto.offset == 0 and proto.limit == 2
