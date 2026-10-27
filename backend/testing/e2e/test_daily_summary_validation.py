"""Real recap routes/auth/serialization/storage, with hermetic Firestore/Redis and LLM seams."""

from copy import deepcopy

import pytest


def _summary(summary_id, day='2026-10-01', **fields):
    return {'id': summary_id, 'date': day, 'headline': 'Productive day', **fields}


def _seed(db, record, uid='123'):
    ref = db.collection('users').document(uid).collection('daily_summaries').document(record['id'])
    ref.set(deepcopy(record))
    return ref


def _corrupt(summary_id='bad', day='2026-10-02'):
    return _summary(summary_id, day, memories_learned=[{'content': 'private memory without its id'}])


@pytest.fixture(params=['user', 'developer'])
def reader(request, client, auth_headers, live_user):
    if request.param == 'user':
        return '/v1/users/daily-summaries', auth_headers
    from database.dev_api_key import create_dev_key

    key, _ = create_dev_key('123', 'Recap integration fixture', scopes=['conversations:read'])
    return '/v1/dev/user/daily-summaries', {'Authorization': f'Bearer {key}'}


def test_pages_fill_before_offset_without_hiding_or_duplicating_older_recaps(client, fake_firestore, reader):
    path, headers = reader
    records = [
        _summary('new', '2026-10-05'),
        _corrupt('bad-a', '2026-10-04'),
        _summary('middle', '2026-10-03', memories_learned=[]),
        _corrupt('bad-b', '2026-10-02'),
        _summary('old', '2026-10-01', stats={'total_conversations': 4}, legacy_extra='kept'),
    ]
    refs = [_seed(fake_firestore, row) for row in records]
    _seed(fake_firestore, _summary('foreign', '2026-10-06'), uid='another-owner')
    first = client.get(path, params={'limit': 2, 'offset': 0}, headers=headers)
    second = client.get(path, params={'limit': 2, 'offset': 2}, headers=headers)
    end = client.get(path, params={'limit': 2, 'offset': 3}, headers=headers)
    assert first.status_code == second.status_code == end.status_code == 200
    assert [s['id'] for s in first.json()['summaries']] == ['new', 'middle']
    assert [s['id'] for s in second.json()['summaries']] == ['old']
    assert second.json()['summaries'][0]['legacy_extra'] == 'kept'
    assert end.json() == {'summaries': []}
    assert [ref.get().to_dict() for ref in refs] == records


def test_corrupt_read_is_unavailable_then_retry_recovers_and_missing_is_404(client, fake_firestore, reader):
    path, headers = reader
    ref = _seed(fake_firestore, _corrupt())
    for target in (path, f'{path}/bad'):
        response = client.get(target, headers=headers)
        assert response.status_code == 503, response.text
        assert 'private memory' not in response.text
    assert client.get(f'{path}/missing', headers=headers).status_code == 404
    ref.set(_summary('bad', '2026-10-02'))
    assert client.get(f'{path}/bad', headers=headers).status_code == 200
    assert client.get(path, headers=headers).json()['summaries'][0]['id'] == 'bad'


def test_non_utf8_legacy_extra_cannot_escape_validation_and_crash_json_serialization(client, fake_firestore, reader):
    path, headers = reader
    _seed(fake_firestore, _summary('bad-extra', '2026-10-02', extra=b'\xff'))
    _seed(fake_firestore, _summary('good'))
    response = client.get(path, headers=headers)
    assert response.status_code == 200, response.text
    assert [s['id'] for s in response.json()['summaries']] == ['good']
    assert client.get(f'{path}/bad-extra', headers=headers).status_code == 503


def test_search_skips_invalid_match_before_limit(client, auth_headers, fake_firestore):
    _seed(fake_firestore, _corrupt())
    _seed(fake_firestore, _summary('good'))
    response = client.get('/v1/users/daily-summaries/search?query=Productive&limit=1', headers=auth_headers)
    assert response.status_code == 200, response.text
    assert [s['id'] for s in response.json()['summaries']] == ['good']


def test_scan_exhaustion_cannot_look_like_an_empty_or_short_final_page(client, fake_firestore, reader, monkeypatch):
    path, headers = reader
    records = [_corrupt(), _summary('good')]
    refs = [_seed(fake_firestore, row) for row in records]
    monkeypatch.setenv('OMI_LIST_READ_MAX_DOCUMENTS', '1')
    assert client.get(path, params={'limit': 2}, headers=headers).status_code == 503
    assert [ref.get().to_dict() for ref in refs] == records
    monkeypatch.setenv('OMI_LIST_READ_MAX_DOCUMENTS', '100')
    retry = client.get(path, params={'limit': 2}, headers=headers)
    assert retry.status_code == 200, retry.text
    assert [s['id'] for s in retry.json()['summaries']] == ['good']


def test_developer_date_bounds_and_raw_store_pagination_keep_their_contract(client, fake_firestore, live_user):
    from database.dev_api_key import create_dev_key
    from database.daily_summaries import get_daily_summaries

    for row in (_summary('outside', '2026-10-05'), _corrupt(), _summary('good')):
        _seed(fake_firestore, row)
    # Other internal callers still get their raw window; filtering is opt-in.
    assert [r['id'] for r in get_daily_summaries('123', limit=1, offset=1)] == ['bad']
    key, _ = create_dev_key('123', 'Date bound fixture', scopes=['conversations:read'])
    response = client.get(
        '/v1/dev/user/daily-summaries?start_date=2026-10-01&end_date=2026-10-03&limit=1',
        headers={'Authorization': f'Bearer {key}'},
    )
    assert response.status_code == 200, response.text
    assert [s['id'] for s in response.json()['summaries']] == ['good']


def test_shared_projection_preserves_allowlist_and_private_records_stay_private(client, fake_firestore):
    from database.redis_db import store_daily_summary_to_uid

    record = _corrupt()
    record.update(visibility='shared', private_extra='never public', locations=[{'address': 'private place'}])
    ref = _seed(fake_firestore, record)
    store_daily_summary_to_uid('bad', '123')
    # Private malformed learned-memory fields must not disable a valid public projection.
    response = client.get('/v1/daily-summaries/bad/shared')
    assert response.status_code == 200, response.text
    assert response.json()['memories_learned'] == []
    assert 'private_extra' not in response.json()
    assert response.json()['locations'] is None
    assert 'private place' not in response.text
    ref.update({'stats': {'total_conversations': 'invalid private content'}})
    corrupt = client.get('/v1/daily-summaries/bad/shared')
    assert corrupt.status_code == 404
    assert 'invalid private content' not in corrupt.text
    ref.update({'visibility': 'private'})
    assert client.get('/v1/daily-summaries/bad/shared').status_code == 404


@pytest.fixture
def generation_seams(monkeypatch):
    import routers.users as users

    # Only paid-compute/provider seams are substituted. Route auth, DB, local-day parsing,
    # cooldowns, response schema and public sharing run through production implementations.
    monkeypatch.setattr(users, 'enforce_chat_quota', lambda *a, **k: None)
    monkeypatch.setattr(users, 'require_generated_compute', lambda *a, **k: None)
    monkeypatch.setattr(users.notification_db, 'get_user_time_zone', lambda uid: 'UTC')
    return users


def test_create_existing_corruption_does_not_rewrite_or_generate(
    client, auth_headers, fake_firestore, generation_seams, monkeypatch
):
    record = _corrupt(day='2026-10-01')
    ref = _seed(fake_firestore, record)

    def unexpected(*args):
        pytest.fail('Existing corrupt recap must not trigger paid automatic regeneration')

    monkeypatch.setattr(generation_seams, 'generate_daily_summary_on_demand', unexpected)
    result = client.post('/v1/users/daily-summaries', json={'date': '2026-10-01'}, headers=auth_headers)
    assert result.status_code == 503, result.text
    assert ref.get().to_dict() == record


def test_create_invalid_provider_result_is_explicit_and_retry_can_succeed(
    client, auth_headers, generation_seams, monkeypatch
):
    results = iter([(_corrupt(), None), (_summary('created'), None)])
    monkeypatch.setattr(generation_seams, 'generate_daily_summary_on_demand', lambda *a: next(results))
    path = '/v1/users/daily-summaries'
    first = client.post(path, json={'date': '2026-10-01'}, headers=auth_headers)
    assert first.status_code == 502, first.text
    second = client.post(path, json={'date': '2026-10-01'}, headers=auth_headers)
    assert second.status_code == 200, second.text
    assert second.json()['id'] == 'created'


def test_regenerate_invalid_output_preserves_stored_recap_then_retry_replaces_in_place(
    client, auth_headers, fake_firestore, fake_redis, generation_seams, monkeypatch
):
    original = _summary('original', visibility='shared', created_at='2026-10-01T22:00:00Z')
    ref = _seed(fake_firestore, original)
    monkeypatch.setattr(generation_seams.conversations_db, 'get_conversations', lambda *a, **k: [{'id': 'c'}])
    monkeypatch.setattr(generation_seams, 'deserialize_conversations', lambda rows: rows)
    monkeypatch.setattr(generation_seams, 'bound_daily_summary_conversations', lambda *a: a[-1])
    monkeypatch.setattr(generation_seams, '_memories_learned_payload', lambda *a: [])
    results = iter([_corrupt('fresh'), _summary('fresh', headline='Regenerated')])
    monkeypatch.setattr(generation_seams, 'generate_comprehensive_daily_summary', lambda *a, **k: next(results))
    path = '/v1/users/daily-summaries/original/regenerate'
    failed = client.post(path, headers=auth_headers)
    assert failed.status_code == 502, failed.text
    assert ref.get().to_dict() == original
    assert client.post(path, headers=auth_headers).status_code == 429
    # Expire the real Redis cooldown without sleeping/widening wall-clock budgets.
    from database.redis_db import delete_generic_cache

    delete_generic_cache('daily_summary_regen:123:original')
    success = client.post(path, headers=auth_headers)
    assert success.status_code == 200, success.text
    assert success.json()['id'] == 'original'
    assert success.json()['headline'] == 'Regenerated'
    assert ref.get().to_dict()['visibility'] == 'shared'
    assert ref.get().to_dict()['created_at'] == original['created_at']
    assert (
        not fake_firestore.collection('users')
        .document('123')
        .collection('daily_summaries')
        .document('fresh')
        .get()
        .exists
    )


def test_owner_routes_still_require_authentication(client):
    for path in ('/v1/users/daily-summaries', '/v1/dev/user/daily-summaries'):
        assert client.get(path).status_code == 401
