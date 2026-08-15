"""The Developer API key memory-grant backfill grants only what a key's own scopes imply (#10734).

Developer API keys created before the create-path grant seeding landed (commit 8e03144a,
2026-06-27) have no entry under ``users/{uid}/memory_control/app_key_memory_grants``. The
grant gate fails closed on a missing grant, so those keys get a permanent 403 from
``GET /v1/dev/user/memories`` while their other endpoints keep working, and nothing
backfills them.

These tests pin the two properties that make the script safe to run against production:
dry run writes nothing, and applying grants exactly the capability the key already has —
never more.
"""

from datetime import datetime, timedelta, timezone

import pytest

import scripts.backfill_developer_api_key_memory_grants as backfill
from database.memory_app_key_grants import (
    APP_KEY_MEMORY_GRANT_DOC_ID,
    APP_KEY_MEMORY_GRANTS_COLLECTION,
    DEVELOPER_API_CONSUMER,
    DEVELOPER_API_DEFAULT_APP_ID,
)

BEFORE = backfill.SEEDING_LANDED_AT - timedelta(days=30)
AFTER = backfill.SEEDING_LANDED_AT + timedelta(days=1)


def _deep_merge(target, patch):
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value


class _Snapshot:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _DocRef:
    def __init__(self, db, path):
        self._db = db
        self._path = path

    def get(self):
        return _Snapshot(self._path.rsplit('/', 1)[-1], self._db.docs.get(self._path))

    def set(self, data, merge=False):
        self._db.writes.append(self._path)
        if merge:
            _deep_merge(self._db.docs.setdefault(self._path, {}), dict(data))
        else:
            self._db.docs[self._path] = dict(data)


class _Query:
    def __init__(self, db, prefix):
        self._db = db
        self._prefix = prefix
        self._limit = None

    def select(self, _fields):
        # The script projects fields; the fake ignores projection and returns whole docs.
        return self

    def document(self, doc_id):
        # The grant reader addresses a doc as collection('users/{uid}/memory_control').document(id).
        return _DocRef(self._db, f'{self._prefix}/{doc_id}')

    def limit(self, limit):
        self._limit = limit
        return self

    def stream(self):
        rows = [
            _Snapshot(path.rsplit('/', 1)[-1], data)
            for path, data in self._db.docs.items()
            if path.startswith(f'{self._prefix}/') and path.count('/') == self._prefix.count('/') + 1
        ]
        return rows[: self._limit] if self._limit is not None else rows


class _FirestoreFake:
    """Path-keyed document store: collection()/document() and document(path) hit the same map."""

    def __init__(self):
        self.docs = {}
        self.writes = []

    def collection(self, name):
        return _Query(self, name)

    def document(self, path):
        return _DocRef(self, path)

    # -- test helpers ------------------------------------------------------------------
    def add_key(self, key_id, uid, scopes, created_at):
        doc = {'id': key_id, 'user_id': uid, 'created_at': created_at}
        if scopes is not _ABSENT:
            doc['scopes'] = scopes
        self.docs[f'dev_api_keys/{key_id}'] = doc

    def grant_path(self, uid):
        return f'users/{uid}/{APP_KEY_MEMORY_GRANTS_COLLECTION}/{APP_KEY_MEMORY_GRANT_DOC_ID}'

    def add_grant(self, uid, key_id):
        self.docs[self.grant_path(uid)] = {
            'grants': {
                DEVELOPER_API_CONSUMER: {'apps': {DEVELOPER_API_DEFAULT_APP_ID: {'keys': {key_id: {'enabled': True}}}}}
            }
        }

    def grant_for(self, uid, key_id):
        doc = self.docs.get(self.grant_path(uid)) or {}
        keys = (
            doc.get('grants', {})
            .get(DEVELOPER_API_CONSUMER, {})
            .get('apps', {})
            .get(DEVELOPER_API_DEFAULT_APP_ID, {})
            .get('keys', {})
        )
        return keys.get(key_id)


_ABSENT = object()


def _run(db, monkeypatch, capsys, argv):
    monkeypatch.setattr(backfill, 'get_firestore_client', lambda: db)
    monkeypatch.setattr('sys.argv', ['backfill_developer_api_key_memory_grants.py', *argv])
    backfill.main()
    return eval(capsys.readouterr().out.strip())  # the script prints a dict literal


@pytest.fixture
def db():
    return _FirestoreFake()


def test_dry_run_reports_the_cohort_and_writes_nothing(db, monkeypatch, capsys):
    db.add_key('k1', 'u1', ['memories:read'], BEFORE)

    counts = _run(db, monkeypatch, capsys, [])

    assert counts['keys_needing_backfill'] == 1
    assert counts['distinct_users_needing_backfill'] == 1
    assert counts['dry_run'] is True
    assert db.writes == [], 'dry run must not write'
    assert db.grant_for('u1', 'k1') is None


def test_apply_seeds_read_only_grant_for_a_read_scoped_key(db, monkeypatch, capsys):
    db.add_key('k1', 'u1', ['memories:read', 'conversations:read'], BEFORE)

    counts = _run(db, monkeypatch, capsys, ['--apply'])

    assert counts['grants_written'] == 1
    grant = db.grant_for('u1', 'k1')
    assert grant['default_read'] is True
    assert grant['write'] is False, 'a read-scoped key must not gain write'
    assert grant['archive_read'] is False
    assert grant['scopes'] == ['memories.read']


def test_apply_seeds_write_for_a_write_scoped_key_without_inventing_read(db, monkeypatch, capsys):
    db.add_key('k1', 'u1', ['memories:write'], BEFORE)

    _run(db, monkeypatch, capsys, ['--apply'])

    grant = db.grant_for('u1', 'k1')
    assert grant['write'] is True
    assert grant['default_read'] is False
    assert grant['scopes'] == ['memories.write']


def test_key_without_a_memory_scope_is_left_alone(db, monkeypatch, capsys):
    db.add_key('k1', 'u1', ['conversations:read'], BEFORE)

    counts = _run(db, monkeypatch, capsys, ['--apply'])

    assert counts['skipped_no_memory_scope'] == 1
    assert counts.get('keys_needing_backfill', 0) == 0
    assert db.writes == []


def test_key_created_after_seeding_is_left_alone(db, monkeypatch, capsys):
    db.add_key('k1', 'u1', ['memories:read'], AFTER)

    counts = _run(db, monkeypatch, capsys, ['--apply'])

    assert counts['skipped_created_after_seeding'] == 1
    assert db.writes == []


def test_absent_scopes_field_is_treated_as_read_only_like_the_request_path(db, monkeypatch, capsys):
    # has_scope(None, ...) resolves a scope-less legacy key to the read-only set, which
    # includes memories:read — such a key can already read memories, so it needs the grant.
    db.add_key('k1', 'u1', _ABSENT, BEFORE)

    counts = _run(db, monkeypatch, capsys, ['--apply'])

    assert counts['absent_scopes_treated_as_read_only'] == 1
    grant = db.grant_for('u1', 'k1')
    assert grant['default_read'] is True
    assert grant['write'] is False, 'write is never inferred from an absent scopes field'


def test_existing_grant_is_not_rewritten_so_reruns_are_safe(db, monkeypatch, capsys):
    db.add_key('k1', 'u1', ['memories:read'], BEFORE)
    db.add_grant('u1', 'k1')

    counts = _run(db, monkeypatch, capsys, ['--apply'])

    assert counts['already_granted'] == 1
    assert counts.get('keys_needing_backfill', 0) == 0
    assert db.writes == []


def test_unusable_created_at_is_skipped_rather_than_guessed(db, monkeypatch, capsys):
    db.add_key('k1', 'u1', ['memories:read'], None)

    counts = _run(db, monkeypatch, capsys, ['--apply'])

    assert counts['skipped_unusable_created_at'] == 1
    assert db.writes == []


def test_naive_created_at_is_read_as_utc_instead_of_crashing_the_scan(db, monkeypatch, capsys):
    db.add_key('k1', 'u1', ['memories:read'], BEFORE.replace(tzinfo=None))
    db.add_key('k2', 'u2', ['memories:read'], BEFORE)

    counts = _run(db, monkeypatch, capsys, ['--apply'])

    assert counts['keys_needing_backfill'] == 2
    assert counts.get('skipped_unusable_created_at', 0) == 0


def test_second_key_for_the_same_user_is_seeded_against_written_state(db, monkeypatch, capsys):
    # The grant document is cached per uid; after a write that cache is stale, so a second
    # key for the same user must still be evaluated and seeded.
    db.add_key('k1', 'u1', ['memories:read'], BEFORE)
    db.add_key('k2', 'u1', ['memories:write'], BEFORE)

    counts = _run(db, monkeypatch, capsys, ['--apply'])

    assert counts['grants_written'] == 2
    assert counts['distinct_users_needing_backfill'] == 1
    assert db.grant_for('u1', 'k1')['default_read'] is True
    assert db.grant_for('u1', 'k2')['write'] is True


def test_limit_bounds_the_scan(db, monkeypatch, capsys):
    for i in range(5):
        db.add_key(f'k{i}', f'u{i}', ['memories:read'], BEFORE)

    counts = _run(db, monkeypatch, capsys, ['--limit', '2'])

    assert counts['total_dev_key_docs'] == 2
    assert db.writes == []


def test_key_without_user_id_is_skipped(db, monkeypatch, capsys):
    db.docs['dev_api_keys/k1'] = {'id': 'k1', 'scopes': ['memories:read'], 'created_at': BEFORE}

    counts = _run(db, monkeypatch, capsys, ['--apply'])

    assert counts['skipped_missing_user_id'] == 1
    assert db.writes == []
