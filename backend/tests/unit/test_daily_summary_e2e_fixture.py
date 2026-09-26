"""Hermetic contracts for the local-only daily-summary review-card fixture."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.daily_summary_e2e as fixture_router

UID = 'auth-emulator-review-card-fixture'


def _client(monkeypatch, *, local: bool = True):
    written: list[tuple[str, dict]] = []
    monkeypatch.setattr(fixture_router, 'is_chat_first_e2e_harness_runtime', lambda: local)
    monkeypatch.setattr(
        fixture_router.daily_summaries_db,
        'create_daily_summary',
        lambda uid, data: written.append((uid, data)) or data['id'],
    )
    app = FastAPI()
    app.include_router(fixture_router.router)
    app.dependency_overrides[fixture_router.auth.get_current_user_uid] = lambda: UID
    return TestClient(app), written


def test_seed_writes_the_wire_shape_the_desktop_card_reads(monkeypatch):
    client, written = _client(monkeypatch)

    response = client.post(
        '/v1/dev-harness/daily-summary/seed',
        json={
            'date': '2026-03-04',
            'memories': [
                {'memory_id': 'mem_a', 'content': 'Prefers async standups.', 'category': 'system'},
                {'memory_id': 'mem_b', 'content': 'Ships on Wednesdays.', 'category': 'workflow'},
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {
        'status': 'ok',
        'summary_id': 'dev-harness-daily-summary-2026-03-04',
        'date': '2026-03-04',
        'memories_learned': 2,
    }
    uid, data = written[0]
    assert uid == UID
    assert data['id'] == 'dev-harness-daily-summary-2026-03-04'
    assert data['date'] == '2026-03-04'
    # The desktop decodes `memories_learned` by these exact keys
    # (`DailySummaryRecord.LearnedMemory`); a rename here renders no rows at all.
    assert [(entry['memory_id'], entry['content'], entry['category']) for entry in data['memories_learned']] == [
        ('mem_a', 'Prefers async standups.', 'system'),
        ('mem_b', 'Ships on Wednesdays.', 'workflow'),
    ]
    assert all(isinstance(entry['captured_at'], str) for entry in data['memories_learned'])


def test_seed_is_idempotent_for_one_day(monkeypatch):
    client, written = _client(monkeypatch)
    payload = {'date': '2026-03-04', 'memories': [{'memory_id': 'mem_a', 'content': 'One.'}]}

    first = client.post('/v1/dev-harness/daily-summary/seed', json=payload)
    second = client.post('/v1/dev-harness/daily-summary/seed', json=payload)

    # One doc id per day, so a re-run overwrites rather than leaving two
    # summaries competing for the desktop's newest-first read of one record.
    assert first.json()['summary_id'] == second.json()['summary_id']
    assert {data['id'] for _, data in written} == {'dev-harness-daily-summary-2026-03-04'}


@pytest.mark.parametrize(
    'memories',
    [
        [],
        [{'memory_id': '  ', 'content': 'No identity.'}],
        [{'memory_id': 'mem_a', 'content': '   '}],
    ],
)
def test_seed_refuses_rows_that_address_no_memory(monkeypatch, memories):
    client, written = _client(monkeypatch)

    response = client.post('/v1/dev-harness/daily-summary/seed', json={'memories': memories})

    assert response.status_code == 400
    assert written == []


def test_seed_refuses_an_invalid_date(monkeypatch):
    client, written = _client(monkeypatch)

    response = client.post(
        '/v1/dev-harness/daily-summary/seed',
        json={'date': '04-03-2026', 'memories': [{'memory_id': 'mem_a', 'content': 'One.'}]},
    )

    assert response.status_code == 400
    assert written == []


def test_fixture_router_is_defensively_hidden_when_directly_included_outside_local(monkeypatch):
    client, written = _client(monkeypatch, local=False)

    response = client.post(
        '/v1/dev-harness/daily-summary/seed',
        json={'memories': [{'memory_id': 'mem_a', 'content': 'One.'}]},
    )

    assert response.status_code == 404
    assert written == []
