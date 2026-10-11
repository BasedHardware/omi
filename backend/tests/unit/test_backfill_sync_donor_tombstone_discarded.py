"""Idempotent dry-run/apply backfill for sync donor discarded stamps."""

from types import SimpleNamespace

import scripts.backfill_sync_donor_tombstone_discarded as backfill


class _Snapshot:
    def __init__(self, doc_id, data, store, *, path):
        self.id = doc_id
        self._data = data
        self.reference = _DocRef(store, path)

    def to_dict(self):
        return dict(self._data)


class _DocRef:
    def __init__(self, store, path):
        self.path = path
        self._store = store
        parts = path.split('/')
        self.id = parts[-1]
        self.parent = SimpleNamespace(parent=SimpleNamespace(id=parts[1] if len(parts) >= 2 else None))

    def update(self, data):
        self._store.conversations[self.path].update(data)
        self._store.direct_writes.append((self.path, dict(data)))


class _Batch:
    def __init__(self, client):
        self._client = client
        self.ops = []

    def update(self, ref, data):
        self.ops.append((ref.path, dict(data)))

    def commit(self):
        self._client.commits.append(list(self.ops))
        for path, data in self.ops:
            self._client.conversations[path].update(data)
        self.ops = []


class _ConversationQuery:
    def __init__(self, client, uid):
        self._client = client
        self._uid = uid
        self._filters = []

    def where(self, *, filter):
        self._filters.append(filter)
        return self

    def stream(self):
        prefix = f'users/{self._uid}/conversations/'
        rows = []
        for path, data in sorted(self._client.conversations.items()):
            if not path.startswith(prefix):
                continue
            if not _matches(data, self._filters):
                continue
            rows.append(_Snapshot(path.rsplit('/', 1)[-1], data, self._client, path=path))
        return rows


class _UserQuery:
    def __init__(self, client):
        self._client = client
        self._after = None
        self._limit = None

    def select(self, _fields):
        return self

    def order_by(self, field):
        self.ordered_by = field
        return self

    def limit(self, limit):
        self._limit = limit
        return self

    def start_after(self, cursor):
        if isinstance(cursor, dict):
            self._after = cursor['__name__']
        else:
            self._after = cursor.id
        return self

    def stream(self):
        uids = sorted(self._client.users)
        if self._after is not None:
            uids = [uid for uid in uids if uid > self._after]
        if self._limit is not None:
            uids = uids[: self._limit]
        return [_Snapshot(uid, {}, self._client, path=f'users/{uid}') for uid in uids]


class _UserDocument:
    def __init__(self, client, uid):
        self._client = client
        self._uid = uid

    def collection(self, name):
        assert name == 'conversations'
        return _ConversationQuery(self._client, self._uid)


class _Users:
    def __init__(self, client):
        self._client = client

    def select(self, fields):
        return _UserQuery(self._client).select(fields)

    def document(self, uid):
        return _UserDocument(self._client, uid)


class _Client:
    def __init__(self, users, conversations):
        self.users = list(users)
        self.conversations = {path: dict(data) for path, data in conversations.items()}
        self.commits = []
        self.direct_writes = []

    def collection(self, name):
        assert name == 'users'
        return _Users(self)

    def batch(self):
        return _Batch(self)


def _matches(data, filters):
    for filt in filters:
        if data.get(filt.field_path) != filt.value:
            return False
    return True


def _client():
    return _Client(
        ['a', 'b', 'c'],
        {
            'users/a/conversations/kept': {'deleted': False, 'discarded': False},
            'users/a/conversations/donor': {
                'deleted': True,
                'discarded': False,
                'sync_merged_into': 'kept',
            },
            'users/b/conversations/already': {
                'deleted': True,
                'discarded': True,
                'sync_merged_into': 'survivor',
            },
            'users/c/conversations/plain': {'discarded': False},
        },
    )


def test_dry_run_counts_unfixed_tombstones_without_writing():
    client = _client()
    summary = backfill.run_backfill(client, apply=False, page_size=200, start_after=None, limit=None)
    assert summary == {
        'scanned_users': 3,
        'scanned_tombstones': 2,
        'already_hidden': 1,
        'written': 1,
        'last_uid': 'c',
        'apply': False,
    }
    assert client.conversations['users/a/conversations/donor']['discarded'] is False
    assert client.commits == []


def test_apply_stamps_discarded_and_is_idempotent():
    client = _client()
    first = backfill.run_backfill(client, apply=True, page_size=200, start_after=None, limit=None)
    assert first['written'] == 1
    assert client.conversations['users/a/conversations/donor']['discarded'] is True
    assert client.conversations['users/b/conversations/already']['discarded'] is True
    second = backfill.run_backfill(client, apply=True, page_size=200, start_after=None, limit=None)
    assert second['written'] == 0
    assert second['already_hidden'] == 2


def test_resume_after_uid_skips_earlier_users():
    client = _client()
    summary = backfill.run_backfill(client, apply=False, page_size=200, start_after='a', limit=None)
    assert summary['scanned_users'] == 2
    assert summary['written'] == 0
    assert summary['last_uid'] == 'c'
