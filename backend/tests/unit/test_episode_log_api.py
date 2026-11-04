"""The real HTTP route contracts for the shadow read adapter, using synthetic state."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers import episodes as api
from utils.episodes.log import reads, worker
from utils.other import endpoints
from database import episode_log as store
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.episodes.log.clock import home_clock
from config.episodes import CLOSE_GAP_SECONDS

NOW = datetime(2026, 11, 4, tzinfo=timezone.utc)


def setup(monkeypatch):
    monkeypatch.setattr(api, '_admitted', lambda uid, channel: True)
    monkeypatch.setattr(reads, 'ready', lambda uid: {'home_version': 7})
    monkeypatch.setattr(worker, 'sample_read', lambda *args: None)
    query = Mock(return_value=([], [], None))
    monkeypatch.setattr(reads, 'list_window', query)
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[endpoints.get_current_user_uid] = lambda: 'test'
    return TestClient(app), query


def test_real_route_returns_304_before_home_page_or_member_reads(monkeypatch):
    http, query = setup(monkeypatch)
    params = {'from': NOW.isoformat(), 'to': (NOW + timedelta(days=1)).isoformat()}
    response = http.get('/v1/episodes', params=params)
    assert response.status_code == 200 and response.headers['x-omi-home-version'] == '7'
    etag = response.headers['etag']
    query.reset_mock()
    response = http.get('/v1/episodes', params=params, headers={'If-None-Match': etag})
    assert response.status_code == 304 and response.content == b''
    assert not query.called
    assert response.headers['cache-control'] == 'private, no-cache'
    changed = dict(params, to=(NOW + timedelta(days=2)).isoformat())
    assert http.get('/v1/episodes', params=changed, headers={'If-None-Match': etag}).status_code == 200
    assert query.called


def test_not_ready_and_policy_changed_use_legacy_projection(monkeypatch):
    http, query = setup(monkeypatch)
    legacy = Mock(return_value=([], None))
    project = Mock(return_value=[])
    monkeypatch.setattr(api.home_read, 'list_episode_window', legacy)
    monkeypatch.setattr(api.home_read, 'project_episodes', project)
    params = {'from': NOW.isoformat(), 'to': NOW.isoformat()}
    query.side_effect = ValueError('episode_home_policy_changed')
    response = http.get('/v1/episodes', params=params)
    assert response.status_code == 200
    assert response.json() == {'enabled': True, 'episodes': [], 'next_cursor': None}
    assert legacy.called and project.called
    monkeypatch.setattr(reads, 'ready', lambda uid: None)
    query.reset_mock()
    assert http.get('/v1/episodes', params=params).status_code == 200
    assert not query.called


def test_expired_home_etag_falls_back_and_queues_one_urgent_refresh(monkeypatch):
    real_ready = reads.ready
    http, query = setup(monkeypatch)
    for key in ('EPISODES_ENABLED', 'EPISODES_LOG_ENABLED', 'EPISODES_HOME_ROWS_ENABLED'):
        monkeypatch.setenv(key, 'on')
    monkeypatch.setenv('EPISODES_PERCENT', '100')
    monkeypatch.setattr(reads, 'selected', lambda uid: True)
    monkeypatch.setattr(worker, 'wake', Mock())
    client = StrictFirestore()
    path = ('users', 'test', 'episode_log_state', 'owner')
    client.rows[path] = {
        'cursor': 0,
        'next_seq': 0,
        'home_version': 7,
        'backfill_complete': True,
        'home_rows_ready': True,
        'home_valid_until': NOW + timedelta(seconds=10),
        'home_refresh_cid': 'c',
    }
    clock = [NOW]
    monkeypatch.setattr(reads, 'ready', lambda uid: real_ready(uid, firestore_client=client, now=clock[0]))
    params = {'from': NOW.isoformat(), 'to': NOW.isoformat()}
    first = http.get('/v1/episodes', params=params)
    assert first.status_code == 200 and query.called
    legacy = Mock(return_value=([], None))
    monkeypatch.setattr(api.home_read, 'list_episode_window', legacy)
    monkeypatch.setattr(api.home_read, 'project_episodes', lambda *args: [])
    clock[0] = NOW + timedelta(minutes=1)
    expired = http.get('/v1/episodes', params=params, headers={'If-None-Match': first.headers['etag']})
    assert expired.status_code == 200 and legacy.called
    assert 'home_version' not in expired.json()
    assert client.rows[path]['next_seq'] == 1 and client.rows[path]['drain_at'] == clock[0]
    worker.note_home_clock('test', client.rows[path], firestore_client=client, now=clock[0])
    assert client.rows[path]['next_seq'] == 1  # Same clock replays without another fact.


def test_home_clock_preserves_live_close_and_settling_expiry(monkeypatch):
    monkeypatch.setenv('HOME_HIDE_BELOW_FLOOR_ROWS', 'on')
    rows = {'e': {'id': 'e', 'status': 'live', 'last_activity_at': NOW, 'conversation_ids': ['c', 'd']}}
    member = {
        'status': 'completed',
        'started_at': NOW - timedelta(seconds=60),
        'finished_at': NOW,
        'structured': {'title_provenance': 'server_minimum'},
    }
    clock = home_clock(rows, {'c': member}, {'d': NOW + timedelta(hours=3)}, {'c'}, NOW)
    assert clock['deadline_at'] == NOW + timedelta(seconds=CLOSE_GAP_SECONDS)
    assert clock['members']['c'] == NOW + timedelta(hours=2)
    rows['e']['status'] = 'closed'
    clock = home_clock(rows, {'c': member}, clock['members'], {'c'}, NOW + timedelta(hours=2))
    assert clock['deadline_at'] == NOW + timedelta(hours=3) and clock['cid'] == 'd'
    assert 'c' not in clock['members']


def test_conditional_home_accepts_rfc_weak_list_and_star_validators(monkeypatch):
    http, query = setup(monkeypatch)
    params = {'from': NOW.isoformat(), 'to': NOW.isoformat()}
    etag = http.get('/v1/episodes', params=params).headers['etag']
    for validator in ('W/' + etag, '"unrelated", W/' + etag, '*'):
        query.reset_mock()
        assert http.get('/v1/episodes', params=params, headers={'If-None-Match': validator}).status_code == 304
        query.assert_not_called()


def test_cached_home_read_keeps_batch_one_compose_recovery(monkeypatch):
    http, query = setup(monkeypatch)
    row, wire = {'id': 'e', 'compose_dirty': True}, {
        'id': 'e',
        'status': 'closed',
        'started_at': NOW,
        'last_activity_at': NOW,
    }
    query.return_value = ([row], [wire], None)
    repair = Mock()
    monkeypatch.setattr(api.home_read, 'schedule_missed_composes', repair)
    params = {'from': NOW.isoformat(), 'to': NOW.isoformat()}
    assert http.get('/v1/episodes', params=params).status_code == 200
    repair.assert_called_once_with('test', [row], [wire])


def test_pending_compose_caps_conditional_cache_age_after_restart():
    from config.episodes import COMPOSER_MAX_SETTLE_SECONDS

    row = {'id': 'e', 'status': 'closed', 'conversation_ids': ['c'], 'compose_pending_since': NOW}
    clock = home_clock({'e': row}, {}, {}, set(), NOW)
    assert clock['deadline_at'] == NOW + timedelta(seconds=COMPOSER_MAX_SETTLE_SECONDS)
    assert clock['cid'] == 'c'


def test_read_flip_live_row_still_uses_canonical_member_visibility(monkeypatch):
    from utils.episodes import visibility

    http, _ = setup(monkeypatch)
    client = StrictFirestore()
    client.rows[('users', 'test', 'episode_view_links', 'current')] = {'episode_id': 'e'}
    client.rows[('users', 'test', 'episode_views', 'e')] = {
        'id': 'e',
        'status': 'live',
        'started_at': NOW,
        'last_activity_at': NOW,
        'conversation_ids': ['hidden'],
        'title': 'must not render',
    }
    monkeypatch.setattr(reads, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(reads.episodes, 'unseal', lambda uid, row: row)
    monkeypatch.setattr(
        visibility.conversations, 'get_conversation_raw_snapshot', lambda *args, **kwargs: {'discarded': True}
    )
    monkeypatch.setattr(api.service, 'live_episode', lambda uid: None)
    response = http.get('/v1/episodes/live')
    assert response.status_code == 200 and response.json() == {'enabled': True, 'episode': None}


def test_batch_transcription_deadline_expires_cache_and_late_receipt_clears_clock():
    row = {'id': 'e', 'status': 'closed', 'conversation_ids': ['c']}
    deadline = NOW + timedelta(hours=2)
    member = {'episode_transcription_deadline_at': deadline, 'status': 'processing'}
    clock = home_clock({'e': row}, {'c': member}, {}, {'c'}, NOW)
    assert clock['deadline_at'] == deadline and clock['cid'] == 'c'
    assert home_clock({'e': row}, {'c': member}, clock['members'], {'c'}, deadline)['deadline_at'] is None
    member['record_projection_revision'] = 1
    assert home_clock({'e': row}, {'c': member}, clock['members'], {'c'}, NOW)['deadline_at'] is None
