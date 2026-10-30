"""Bounded migration mechanics; emulator exercises actual contention/retries."""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.sync import cap_hold


@pytest.mark.parametrize('legacy', [None, {'version': 1, 'seconds': 99999, 'count': 999}])
def test_summary_pages_resume_after_fence_and_never_publish_partial_totals(monkeypatch, legacy):
    prefix = ('users', 'synthetic', 'stt_cap_holds')
    total_key = ('users', 'synthetic', 'stt_cap_hold_summary', 'current')
    rows = {(*prefix, f'old-{i:04d}'): {'state': 'held', 'seconds': 0.25, 'created_at': i + 1} for i in range(805)}
    if legacy is not None:
        rows[total_key] = legacy
    client = StrictFirestore(rows)
    cursors = []

    class Query:
        cursor = None

        def document(self, identity):
            return client.document('/'.join((*prefix, identity)))

        def order_by(self, field):
            assert field == '__name__'
            return self

        def limit(self, limit):
            assert limit == 400
            return self

        def start_after(self, cursor):
            self.cursor = cursor['__name__'].id
            return self

        def stream(self, *, transaction):
            transaction._assert_read_allowed()
            cursors.append(self.cursor)
            ids = sorted(path[-1] for path in client.rows if path[:-1] == prefix)
            ids = [identity for identity in ids if self.cursor is None or identity > self.cursor][:400]
            return iter(
                SimpleNamespace(
                    id=identity,
                    reference=self.document(identity),
                    to_dict=lambda identity=identity: dict(client.rows[(*prefix, identity)]),
                )
                for identity in ids
            )

    monkeypatch.setattr(cap_hold, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(cap_hold, 'holds', lambda uid: Query())
    calls = 0

    @contextmanager
    def fence(uid):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError('synthetic deletion fence')
        yield

    monkeypatch.setattr(cap_hold, 'external_write_fence', fence)
    with pytest.raises(RuntimeError, match='synthetic deletion fence'):
        cap_hold.ensure_summary('synthetic')
    partial = client.rows[total_key]
    assert partial['build_owner']
    assert partial['build_lease_until'] > cap_hold.time.time()
    assert {key: value for key, value in partial.items() if key not in {'build_owner', 'build_lease_until'}} == {
        'version': 1,
        'building': True,
        'cursor': 'old-0399',
        'partial_seconds': 100.0,
        'partial_count': 400,
    }
    assert sum('listed_at' in row for path, row in client.rows.items() if path[:-1] == prefix) == 400
    client.rows[total_key]['build_lease_until'] = 0  # Abandoned owner expires; a new call resumes.
    assert cap_hold.ensure_summary('synthetic') == {'version': 2, 'seconds': 201.25, 'count': 805}
    assert cursors == [None, 'old-0399', 'old-0799']
    assert all(len(tx.updates) <= 400 and len(tx.sets) == 1 for tx in client.transactions)
    assert all('listed_at' in row for path, row in client.rows.items() if path[:-1] == prefix)


def test_ready_summary_has_one_read_and_no_fence_or_query(monkeypatch):
    result = {'version': 2, 'seconds': 30.5, 'count': 2}
    ref = SimpleNamespace(get=Mock(return_value=SimpleNamespace(exists=True, to_dict=lambda: result)))
    monkeypatch.setattr(cap_hold, 'get_firestore_client', lambda: None)
    monkeypatch.setattr(cap_hold, 'summary_ref', lambda uid: ref)
    monkeypatch.setattr(cap_hold, 'external_write_fence', Mock(side_effect=AssertionError('unexpected fence')))
    monkeypatch.setattr(cap_hold, 'holds', Mock(side_effect=AssertionError('unexpected query')))
    assert cap_hold.ensure_summary('synthetic') == result
    ref.get.assert_called_once_with()


def test_busy_initializer_times_out_without_partial_response_or_hold_query(monkeypatch):
    marker = {
        'version': 1,
        'building': True,
        'build_owner': 'other',
        'build_lease_until': 1000,
        'cursor': 'old-0399',
        'partial_seconds': 100,
        'partial_count': 400,
    }
    ref = SimpleNamespace(get=Mock(return_value=SimpleNamespace(exists=True, to_dict=lambda: dict(marker))))
    monkeypatch.setattr(cap_hold, 'get_firestore_client', lambda: None)
    monkeypatch.setattr(cap_hold, 'summary_ref', lambda uid: ref)
    monkeypatch.setattr(cap_hold.time, 'time', lambda: 100)
    clock = iter([0, 31])
    monkeypatch.setattr(cap_hold.time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(cap_hold, 'holds', Mock(side_effect=AssertionError('non-owner queried holds')))
    with pytest.raises(RuntimeError, match='initialization in progress'):
        cap_hold.ensure_summary('synthetic')
    ref.get.assert_called_once_with()
