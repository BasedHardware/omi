"""Hidden counts use one projected, capped query and the Home visibility rules."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import hidden_noise_counts as counts_db

START = datetime(2026, 10, 27, tzinfo=timezone.utc)
END = START + timedelta(days=1)


class FakeFirestore:
    def __init__(self, rows):
        self.rows = rows
        self.path = []
        self.filters = []
        self.projection = None
        self.row_limit = None
        self.streams = 0

    def collection(self, name):
        self.path.append(name)
        return self

    def document(self, name):
        self.path.append(name)
        return self

    def where(self, *, filter):
        self.filters.append((filter.field_path, filter.op_string, filter.value))
        return self

    def order_by(self, field, *, direction):
        assert (field, direction) == ('created_at', 'DESCENDING')
        return self

    def select(self, fields):
        self.projection = fields
        return self

    def limit(self, limit):
        self.row_limit = limit
        return self

    def stream(self):
        self.streams += 1
        assert self.path == ['users', 'test-uid', 'conversations']
        assert self.projection == counts_db.HIDDEN_NOISE_FIELDS
        assert self.row_limit == 1001
        matches = []
        for row in self.rows:
            for field, op, value in self.filters:
                stamp = row.get(field)
                if stamp is None:
                    break
                if op == '==' and (type(stamp) is not type(value) or stamp != value):
                    break
                if op == '>=' and stamp < value:
                    break
                if op == '<=' and stamp > value:
                    break
            else:
                matches.append(row)
        matches.sort(key=lambda row: row['created_at'], reverse=True)
        for row in matches[: self.row_limit]:
            projected = {key: value for key, value in row.items() if key in self.projection}
            yield SimpleNamespace(to_dict=lambda data=projected: dict(data))


def row(**updates):
    return dict(created_at=START, discarded=True, content_kind='noise', status='completed') | updates


def count(rows, tz='UTC'):
    client = FakeFirestore(rows)
    result = counts_db.count_hidden_noise_by_day('test-uid', START, END, ZoneInfo(tz), firestore_client=client)
    assert client.streams == 1
    assert client.filters == [('discarded', '==', True), ('created_at', '>=', START), ('created_at', '<=', END)]
    return result


def test_home_visibility_and_hidden_noise_criteria():
    rows = [
        row(),
        row(content_kind='media', status='processing'),
        row(is_locked=True),  # Home displays locked rows too.
        row(sync_relevance_user_kept=False),
        row(sync_relevance_user_kept=True),
        row(content_kind='speech'),
        row(content_kind=None),
        row(discarded=False),
        row(deleted=True),
        row(sync_merged_into='survivor'),
        row(dream_duplicate_of='canonical'),  # The reveal list shows Dream duplicates.
        row(status='in_progress'),
        row(status='failed'),
        row(status=None),
        row(created_at=START - timedelta(microseconds=1)),
        row(created_at=END + timedelta(microseconds=1)),
    ]
    assert count(rows) == {'days': [{'date': '2026-10-27', 'count': 5}], 'total': 5, 'truncated': False}


def test_timezone_midnight_and_inclusive_bounds():
    rows = [row(), row(created_at=START + timedelta(hours=7)), row(created_at=END)]
    assert count(rows, 'America/Los_Angeles') == {
        'days': [{'date': '2026-10-26', 'count': 1}, {'date': '2026-10-27', 'count': 2}],
        'total': 3,
        'truncated': False,
    }


def test_empty_omits_zero_days():
    assert count([]) == {'days': [], 'total': 0, 'truncated': False}


@pytest.mark.parametrize('size,truncated', [(999, False), (1000, False), (1001, True)])
def test_scan_cap(size, truncated):
    assert count([row()] * size) == {
        'days': [{'date': '2026-10-27', 'count': min(size, 1000)}],
        'total': min(size, 1000),
        'truncated': truncated,
    }


def test_cap_applies_before_post_filtering():
    assert count([row(content_kind='speech')] * 1001) == {'days': [], 'total': 0, 'truncated': True}


@pytest.fixture
def api(monkeypatch):
    from routers import conversations as routes

    client = FakeFirestore([row()])
    monkeypatch.setattr(counts_db, 'get_firestore_client', lambda: client)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.auth.get_current_user_uid] = lambda: 'test-uid'
    with TestClient(app) as http:
        yield http, client


def test_endpoint_contract_default_timezone_and_route_order(api):
    http, client = api
    response = http.get(
        '/v1/conversations/hidden-noise-counts', params={'start_date': START.isoformat(), 'end_date': END.isoformat()}
    )
    assert response.status_code == 200
    assert response.json() == {
        'tz': 'UTC',
        'start_date': '2026-10-27T00:00:00Z',
        'end_date': '2026-10-28T00:00:00Z',
        'days': [{'date': '2026-10-27', 'count': 1}],
        'total': 1,
        'truncated': False,
    }
    assert client.streams == 1


@pytest.mark.parametrize(
    'updates,status',
    [
        ({'start_date': None}, 422),
        ({'end_date': None}, 422),
        ({'start_date': 'invalid'}, 422),
        ({'tz': 'Not/AZone'}, 400),
        ({'tz': '../UTC'}, 400),
        ({'start_date': (END + timedelta(seconds=1)).isoformat()}, 400),
        ({'end_date': (START + timedelta(days=31, microseconds=1)).isoformat()}, 400),
    ],
)
def test_invalid_window_or_timezone_never_queries(api, updates, status):
    http, client = api
    params = {'start_date': START.isoformat(), 'end_date': END.isoformat()} | updates
    response = http.get(
        '/v1/conversations/hidden-noise-counts', params={k: v for k, v in params.items() if v is not None}
    )
    assert response.status_code == status
    assert client.streams == 0


def test_31_day_window_and_naive_timestamps_are_accepted(api):
    http, client = api
    response = http.get(
        '/v1/conversations/hidden-noise-counts',
        params={
            'start_date': '2026-10-27T00:00:00',
            'end_date': '2026-11-27T01:00:00+01:00',
            'tz': 'America/Los_Angeles',
        },
    )
    assert response.status_code == 200
    assert response.json()['days'] == [{'date': '2026-10-26', 'count': 1}]
    assert response.json()['end_date'] == '2026-11-27T00:00:00Z'
    assert client.streams == 1
