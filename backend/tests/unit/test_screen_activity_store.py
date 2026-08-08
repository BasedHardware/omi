"""Behavioral tests for ``database.screen_activity`` over the neutral storage port (WP2).

Before the storage-port migration this module talked to the raw Firestore client, so no unit test
exercised its real read/write logic (the MCP suites stub the whole ``database.screen_activity``
module). These tests drive the *real* functions through a ``FakeDocumentStore`` injected at the
``_store`` seam, asserting on returned values and stored state at the exact user-scoped paths.
"""

from datetime import datetime

import pytest

import database.screen_activity as screen_activity_db
from tests.store_fakes import FakeDocumentStore


@pytest.fixture
def store(monkeypatch):
    fake = FakeDocumentStore()
    monkeypatch.setattr(screen_activity_db, '_store', lambda: fake)
    return fake


def _row(id_, ts, app='Chrome', title='Tab', ocr='text'):
    return {'id': id_, 'timestamp': ts, 'appName': app, 'windowTitle': title, 'ocrText': ocr}


class TestUpsert:
    def test_empty_rows_writes_nothing(self, store):
        assert screen_activity_db.upsert_screen_activity('u1', []) == 0
        assert store._docs == {}

    def test_rows_persist_at_user_scoped_paths(self, store):
        n = screen_activity_db.upsert_screen_activity(
            'u1', [_row('a', '2026-01-01 10:00:00.000'), _row('b', '2026-01-01 11:00:00.000')]
        )
        assert n == 2
        assert 'users/u1/screen_activity/a' in store._docs
        assert store._docs['users/u1/screen_activity/b']['appName'] == 'Chrome'

    def test_ocr_text_truncated_to_1000(self, store):
        screen_activity_db.upsert_screen_activity('u1', [_row('a', 't', ocr='x' * 5000)])
        assert len(store._docs['users/u1/screen_activity/a']['ocrText']) == 1000

    def test_chunks_over_500_all_written(self, store):
        rows = [_row(str(i), f'2026-01-01 10:00:{i:02d}.000') for i in range(750)]
        assert screen_activity_db.upsert_screen_activity('u1', rows) == 750
        assert len([p for p in store._docs if p.startswith('users/u1/screen_activity/')]) == 750

    def test_client_id_with_slash_is_rejected_not_written_to_wrong_path(self, store):
        # A '/' in the client-provided id would split the composed path into extra segments (wrong
        # Mongo collection/key; Firestore rejects the odd-segment path). It must be refused, and
        # nothing partial must land — not silently written under a mis-parsed path.
        with pytest.raises(ValueError):
            screen_activity_db.upsert_screen_activity('u1', [_row('dev/../ice', '2026-01-01 10:00:00.000')])
        assert store._docs == {}


class TestGet:
    def test_returns_rows_with_id_ordered_by_timestamp(self, store):
        store.set('users/u1/screen_activity/b', {'timestamp': '2026-01-01 12:00:00.000', 'appName': 'Chrome'})
        store.set('users/u1/screen_activity/a', {'timestamp': '2026-01-01 10:00:00.000', 'appName': 'Chrome'})
        rows = screen_activity_db.get_screen_activity('u1')
        assert [r['id'] for r in rows] == ['a', 'b']

    def test_date_range_and_app_filter(self, store):
        store.set('users/u1/screen_activity/a', {'timestamp': '2026-01-01 09:00:00.000', 'appName': 'Chrome'})
        store.set('users/u1/screen_activity/b', {'timestamp': '2026-01-02 09:00:00.000', 'appName': 'Cursor'})
        store.set('users/u1/screen_activity/c', {'timestamp': '2026-01-02 09:00:00.000', 'appName': 'Chrome'})
        rows = screen_activity_db.get_screen_activity(
            'u1',
            start_date=datetime(2026, 1, 2, 0, 0, 0),
            end_date=datetime(2026, 1, 2, 23, 59, 59),
            app_filter='Cursor',
        )
        assert [r['id'] for r in rows] == ['b']

    def test_limit_is_honored(self, store):
        for i in range(5):
            store.set(f'users/u1/screen_activity/{i}', {'timestamp': f'2026-01-01 10:00:0{i}.000', 'appName': 'Chrome'})
        assert len(screen_activity_db.get_screen_activity('u1', limit=2)) == 2


class TestSummary:
    def test_empty_summary(self, store):
        assert screen_activity_db.get_screen_activity_summary('u1') == {'apps': {}, 'total_screenshots': 0}

    def test_groups_by_app_and_counts(self, store):
        store.set('users/u1/screen_activity/a', {'timestamp': 't1', 'appName': 'Chrome', 'windowTitle': 'X'})
        store.set('users/u1/screen_activity/b', {'timestamp': 't2', 'appName': 'Chrome', 'windowTitle': 'Y'})
        store.set('users/u1/screen_activity/c', {'timestamp': 't3', 'appName': 'Cursor', 'windowTitle': ''})
        summary = screen_activity_db.get_screen_activity_summary('u1')
        assert summary['total_screenshots'] == 3
        assert summary['apps']['Chrome']['count'] == 2
        assert set(summary['apps']['Chrome']['window_titles']) == {'X', 'Y'}


class TestOcrText:
    def test_missing_document_returns_empty(self, store):
        assert screen_activity_db.get_screen_activity_ocr_text('u1', 'missing') == ''

    def test_returns_truncated_ocr(self, store):
        store.set('users/u1/screen_activity/a', {'ocrText': 'y' * 500})
        assert screen_activity_db.get_screen_activity_ocr_text('u1', 'a', max_len=50) == 'y' * 50

    def test_slash_in_id_is_rejected_not_path_traversed(self, store):
        # A sid containing '/' must not compose an unintended document path (path injection): the
        # read normalizes the id segment exactly as the write does, and an unsafe id is refused.
        with pytest.raises(ValueError):
            screen_activity_db.get_screen_activity_ocr_text('u1', 'a/b')


class TestIds:
    def test_list_ids_for_user(self, store):
        store.set('users/u1/screen_activity/a', {'timestamp': 't'})
        store.set('users/u1/screen_activity/b', {'timestamp': 't'})
        store.set('users/u2/screen_activity/c', {'timestamp': 't'})
        assert sorted(screen_activity_db.get_screen_activity_ids('u1')) == ['a', 'b']
