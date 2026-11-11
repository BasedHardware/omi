"""Idempotent dry-run/apply backfill for daily-summary schedule fields (#13210)."""

import scripts.backfill_daily_summary_schedule_fields as backfill


class _Snapshot:
    def __init__(self, uid, data, store):
        self.id = uid
        self._data = data
        self.reference = _DocRef(store, uid)

    def to_dict(self):
        return dict(self._data)


class _DocRef:
    def __init__(self, store, uid):
        self.uid = uid
        self._store = store

    def set(self, data, merge=True):
        existing = self._store.docs.get(self.uid, {})
        if merge:
            self._store.docs[self.uid] = {**existing, **data}
        else:
            self._store.docs[self.uid] = dict(data)
        self._store.direct_writes.append((self.uid, dict(data), merge))


class _Batch:
    def __init__(self, client):
        self._client = client
        self.ops = []

    def set(self, ref, data, merge=True):
        self.ops.append((ref.uid, dict(data), merge))

    def commit(self):
        self._client.commits.append(list(self.ops))
        for uid, data, merge in self.ops:
            existing = self._client.docs.get(uid, {})
            if merge:
                self._client.docs[uid] = {**existing, **data}
            else:
                self._client.docs[uid] = dict(data)
        self.ops = []


class _Query:
    def __init__(self, client):
        self._client = client
        self._after = None
        self._limit = None
        self.selected = None
        self.ordered_by = None

    def select(self, fields):
        self.selected = list(fields)
        return self

    def order_by(self, field):
        self.ordered_by = field
        return self

    def limit(self, limit):
        self._limit = limit
        return self

    def start_after(self, cursor):
        # Mirror the SDK contract: a snapshot or a {'__name__': uid} dict; a bare string is rejected.
        if isinstance(cursor, dict):
            self._after = cursor['__name__']
        elif hasattr(cursor, 'id'):
            self._after = cursor.id
        else:
            raise ValueError(f'unsupported cursor {cursor!r}')
        return self

    def stream(self):
        uids = sorted(self._client.docs)
        if self._after is not None:
            uids = [uid for uid in uids if uid > str(self._after)]
        if self._limit is not None:
            uids = uids[: self._limit]
        self._client.queries.append(
            {'select': self.selected, 'order_by': self.ordered_by, 'limit': self._limit, 'start_after': self._after}
        )
        return [_Snapshot(uid, self._client.docs[uid], self._client) for uid in uids]


class _FakeClient:
    def __init__(self, docs):
        self.docs = {uid: dict(data) for uid, data in docs.items()}
        self.commits = []
        self.queries = []
        self.direct_writes = []

    def collection(self, name):
        assert name == 'users'
        return _Query(self)

    def batch(self):
        return _Batch(self)


def test_dry_run_writes_nothing_and_counts_absent_fields():
    client = _FakeClient(
        {
            'a': {'time_zone': 'UTC'},
            'b': {'time_zone': 'UTC', 'daily_summary_enabled': False, 'daily_summary_hour_local': 0},
            'c': {'daily_summary_hour_local': 8},
        }
    )

    summary = backfill.run_backfill(client, apply=False, page_size=500, start_after=None, limit=None)

    assert summary == {
        'scanned': 3,
        'with_time_zone': 2,
        'missing_enabled': 2,
        'missing_hour': 1,
        'written': 2,
        'last_uid': 'c',
        'apply': False,
    }
    assert client.commits == []
    assert client.direct_writes == []
    assert client.docs['a'] == {'time_zone': 'UTC'}
    assert client.docs['b']['daily_summary_enabled'] is False
    assert client.docs['b']['daily_summary_hour_local'] == 0
    assert client.queries[0]['select'] == [
        'time_zone',
        'daily_summary_enabled',
        'daily_summary_hour_local',
    ]
    assert client.queries[0]['order_by'] == '__name__'


def test_apply_writes_only_absent_fields_and_leaves_false_and_zero():
    client = _FakeClient(
        {
            'a': {'time_zone': 'UTC'},
            'b': {'daily_summary_enabled': False},
            'c': {'daily_summary_hour_local': 0, 'time_zone': 'UTC'},
            'd': {'daily_summary_enabled': True, 'daily_summary_hour_local': 22},
        }
    )

    summary = backfill.run_backfill(client, apply=True, page_size=500, start_after=None, limit=None)

    assert summary['written'] == 3
    assert summary['apply'] is True
    assert client.docs['a'] == {
        'time_zone': 'UTC',
        'daily_summary_enabled': True,
        'daily_summary_hour_local': 22,
    }
    assert client.docs['b'] == {'daily_summary_enabled': False, 'daily_summary_hour_local': 22}
    assert client.docs['c'] == {'daily_summary_hour_local': 0, 'time_zone': 'UTC', 'daily_summary_enabled': True}
    assert client.docs['d'] == {'daily_summary_enabled': True, 'daily_summary_hour_local': 22}
    assert len(client.commits) == 1
    written_uids = {uid for uid, _data, _merge in client.commits[0]}
    assert written_uids == {'a', 'b', 'c'}


def test_resume_via_start_after():
    client = _FakeClient(
        {
            'a': {},
            'b': {},
            'c': {},
        }
    )

    summary = backfill.run_backfill(client, apply=False, page_size=500, start_after='a', limit=None)

    assert summary['scanned'] == 2
    assert summary['last_uid'] == 'c'
    assert client.queries[0]['start_after'] == 'a'


def test_batch_flushes_at_five_hundred_ops():
    docs = {f'u{i:04d}': {} for i in range(501)}
    client = _FakeClient(docs)

    summary = backfill.run_backfill(client, apply=True, page_size=500, start_after=None, limit=None)

    assert summary['written'] == 501
    assert summary['scanned'] == 501
    assert [len(ops) for ops in client.commits] == [500, 1]
