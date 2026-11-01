"""Exercise real paging, delete batching and fail-closed scope with a fake store."""

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from google.cloud.firestore_v1 import FieldFilter  # Preload SDK before timed test calls.
import pytest

spec = importlib.util.spec_from_file_location(
    'retire_queue', Path(__file__).parents[2] / 'scripts/retire_dead_queue_backlog.py'
)
retirement = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retirement)


class FakeClient:
    def __init__(self, size, *, path=None, created=None):
        self.rows = [
            SimpleNamespace(
                reference=SimpleNamespace(path=path or f'users/u/projection_repairs/{i:04}'),
                to_dict=lambda: {'created_at': created or datetime(2026, 7, 1, tzinfo=timezone.utc)},
            )
            for i in range(size)
        ]
        self.commits = []
        self.fresh = 0

    def collection_group(self, queue):
        assert queue == 'projection_repairs'
        return Query(self)

    def batch(self):
        refs = []
        return SimpleNamespace(delete=refs.append, commit=lambda **kwargs: self.commits.append(list(refs)))


class Query:
    def __init__(self, client, start=0, limit=400, filtered=False):
        self.client, self.start, self.cap, self.filtered = client, start, limit, filtered

    def count(self):
        return SimpleNamespace(
            get=lambda **kwargs: [
                [SimpleNamespace(value=self.client.fresh if self.filtered else len(self.client.rows))]
            ]
        )

    def where(self, **kwargs):
        return Query(self.client, filtered=True)

    def select(self, fields):
        assert fields == ['created_at']
        return self

    def order_by(self, field):
        assert field == '__name__'
        return self

    def limit(self, cap):
        return Query(self.client, self.start, cap)

    def stream(self, **kwargs):
        return self.client.rows[self.start : self.start + self.cap]

    def start_after(self, doc):
        return Query(self.client, self.client.rows.index(doc) + 1)


def test_dry_run_pages_and_caps_without_writes():
    client = FakeClient(999)
    result = retirement.retire(client, 'projection_repairs', max_deletes=450)
    assert result == dict(queue='projection_repairs', total_count=999, scanned=450, deleted=0, cap=450)
    assert client.commits == []


def test_execute_caps_and_batches():
    client = FakeClient(999)
    result = retirement.retire(
        client, 'projection_repairs', execute=True, confirm_queue='projection_repairs', max_deletes=450
    )
    assert result['deleted'] == 450
    assert [len(batch) for batch in client.commits] == [400, 50]


@pytest.mark.parametrize('kwargs', [{'execute': True}, {'max_deletes': 0}, {'batch_size': 401}])
def test_invalid_authorization_or_caps(kwargs):
    with pytest.raises(ValueError):
        retirement.retire(FakeClient(1), 'projection_repairs', **kwargs)


@pytest.mark.parametrize(
    'path',
    ['users/u/messages/m', 'users/u/memories/m', 'other/u/projection_repairs/m', 'users/u/x/y/projection_repairs/m'],
)
def test_sibling_and_wrong_ancestry_rejected(path):
    client = FakeClient(1, path=path)
    with pytest.raises(ValueError):
        retirement.retire(client, 'projection_repairs', execute=True, confirm_queue='projection_repairs')
    assert client.commits == []


def test_fresh_rows_abort_before_any_batch():
    client = FakeClient(999)
    client.fresh = 1
    with pytest.raises(ValueError, match='post-retirement'):
        retirement.retire(client, 'projection_repairs', execute=True, confirm_queue='projection_repairs')
    assert client.commits == []


@pytest.mark.parametrize(
    'argv', [['--execute'], ['--execute', '--queue', 'projection_repairs', '--confirm-queue', 'projection_repairs']]
)
def test_cli_requires_explicit_cap_before_client_creation(argv):
    with pytest.raises(SystemExit):
        retirement.main(['--project', 'test', *argv])
