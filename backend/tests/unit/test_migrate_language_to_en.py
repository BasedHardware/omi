"""Tests for the conversation language backfill migration (#11349).

Verifies 008_migrate_language_to_en.py: missing/empty language values are
backfilled to 'en', existing values are preserved, dry-run writes nothing,
user iteration is bounded in pages, and any per-user Firestore failure
fails the run (non-zero exit) instead of reporting success.
"""

import importlib.util
import logging
import sys
from pathlib import Path

import pytest

_MIGRATION_PATH = Path(__file__).resolve().parents[2] / 'migrations' / '008_migrate_language_to_en.py'


@pytest.fixture(scope='module')
def migration():
    spec = importlib.util.spec_from_file_location('migration_008_language_to_en', _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeConversationSnapshot:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self.reference = f'conversations/{doc_id}'
        self._data = data

    def to_dict(self):
        return self._data


class FakeConversationsCollection:
    def __init__(self, snapshots):
        self._snapshots = snapshots

    def select(self, fields):
        return self

    def stream(self):
        return iter(self._snapshots)


class FakeUserDoc:
    def __init__(self, uid, db):
        self.id = uid
        self._db = db

    def collection(self, name):
        assert name == 'conversations'
        return FakeConversationsCollection(self._db._conversations.get(self.id, []))


class FakeUsersCollection:
    def __init__(self, db):
        self._db = db
        self._limit = None
        self._after = None

    def order_by(self, field):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def start_after(self, values):
        cursor = values['__name__']
        self._after = cursor.id
        return self

    def stream(self):
        ids = self._db._users
        start = ids.index(self._after) + 1 if self._after else 0
        page = ids[start : start + self._limit] if self._limit else ids[start:]
        return iter([FakeUserDoc(uid, self._db) for uid in page])

    def document(self, uid):
        return FakeUserDoc(uid, self._db)


class FakeBatch:
    def __init__(self, db):
        self._db = db
        self.updates = []
        self.commits = 0

    def update(self, reference, data):
        self.updates.append((reference, data))

    def commit(self):
        self.commits += 1
        self._db.committed_batches.append(self.updates)
        if self._db.fail_on_commit:
            raise self._db.fail_on_commit


class FakeDB:
    def __init__(self, users, conversations, fail_on_commit=None):
        self._users = users
        self._conversations = conversations
        self.fail_on_commit = fail_on_commit
        self.committed_batches = []

    def collection(self, name):
        assert name == 'users'
        return FakeUsersCollection(self)

    def batch(self):
        return FakeBatch(self)


def _conv_snapshots(*languages):
    return [
        FakeConversationSnapshot(f'c{i}', {'language': lang} if lang is not None else {})
        for i, lang in enumerate(languages)
    ]


class TestProcessUserConversations:
    def test_backfills_missing_and_empty_language_only(self, migration):
        db = FakeDB(['u1'], {'u1': _conv_snapshots('fr', None, '', 'es')})
        updates, writes = migration.process_user_conversations(db, 'u1')
        assert updates == 2
        assert writes == 2
        committed = [u for batch in db.committed_batches for u in batch]
        assert committed == [('conversations/c1', {'language': 'en'}), ('conversations/c2', {'language': 'en'})]

    def test_existing_language_is_preserved(self, migration):
        db = FakeDB(['u1'], {'u1': _conv_snapshots('fr', 'es', 'zh')})
        updates, writes = migration.process_user_conversations(db, 'u1')
        assert updates == 0
        assert writes == 0
        assert db.committed_batches == []

    def test_dry_run_counts_without_writing(self, migration):
        db = FakeDB(['u1'], {'u1': _conv_snapshots(None, '')})
        updates, writes = migration.process_user_conversations(db, 'u1', dry_run=True)
        assert updates == 2
        assert writes == 0
        assert db.committed_batches == []

    def test_firestore_failure_is_propagated(self, migration):
        db = FakeDB(['u1'], {'u1': _conv_snapshots(None)}, fail_on_commit=RuntimeError('commit failed'))
        with pytest.raises(RuntimeError):
            migration.process_user_conversations(db, 'u1')


class TestIterUserIds:
    def test_paginates_all_users_in_order(self, migration):
        db = FakeDB([f'u{i:04d}' for i in range(2500)], {})
        assert list(migration.iter_user_ids(db, page_size=1000)) == [f'u{i:04d}' for i in range(2500)]

    def test_resumes_after_start_after(self, migration):
        db = FakeDB([f'u{i:04d}' for i in range(2500)], {})
        result = list(migration.iter_user_ids(db, start_after='u1000', page_size=1000))
        assert result == [f'u{i:04d}' for i in range(1001, 2500)]

    def test_max_users_bounds_iteration(self, migration):
        db = FakeDB([f'u{i:04d}' for i in range(2500)], {})
        assert list(migration.iter_user_ids(db, page_size=1000, max_users=100)) == [f'u{i:04d}' for i in range(100)]


class TestMain:
    def test_dry_run_reports_without_committing(self, migration, monkeypatch, caplog):
        db = FakeDB(['u1'], {'u1': _conv_snapshots(None)})
        monkeypatch.setattr(migration, 'get_firestore_client', lambda: db)
        monkeypatch.setattr(sys, 'argv', ['008_migrate_language_to_en.py', '--dry-run'])
        caplog.set_level(logging.INFO)
        migration.main()
        assert db.committed_batches == []
        assert 'would be updated' in caplog.text

    def test_worker_failure_exits_nonzero(self, migration, monkeypatch):
        db = FakeDB(['u1'], {'u1': _conv_snapshots(None)}, fail_on_commit=RuntimeError('commit failed'))
        monkeypatch.setattr(migration, 'get_firestore_client', lambda: db)
        monkeypatch.setattr(sys, 'argv', ['008_migrate_language_to_en.py', '--workers', '1'])
        with pytest.raises(SystemExit) as excinfo:
            migration.main()
        assert excinfo.value.code == 1

    def test_max_writes_stops_scheduling_after_budget(self, migration, monkeypatch, caplog):
        db = FakeDB([f'u{i:04d}' for i in range(50)], {f'u{i:04d}': _conv_snapshots(None) for i in range(50)})
        monkeypatch.setattr(migration, 'get_firestore_client', lambda: db)
        monkeypatch.setattr(sys, 'argv', ['008_migrate_language_to_en.py', '--workers', '2', '--max-writes', '5'])
        caplog.set_level(logging.INFO)
        migration.main()
        assert 'Reached --max-writes 5, stopping' in caplog.text
        committed_updates = sum(len(batch) for batch in db.committed_batches)
        assert 5 <= committed_updates <= 6
        assert committed_updates < 50

    def test_worker_failure_advises_rerun_without_start_after(self, migration, monkeypatch, caplog):
        db = FakeDB(
            ['u1', 'u2'],
            {'u1': _conv_snapshots(None), 'u2': _conv_snapshots(None)},
            fail_on_commit=RuntimeError('commit failed'),
        )
        monkeypatch.setattr(migration, 'get_firestore_client', lambda: db)
        monkeypatch.setattr(sys, 'argv', ['008_migrate_language_to_en.py', '--workers', '2'])
        caplog.set_level(logging.ERROR)
        with pytest.raises(SystemExit) as excinfo:
            migration.main()
        assert excinfo.value.code == 1
        assert 'Re-run the migration WITHOUT --start-after' in caplog.text
