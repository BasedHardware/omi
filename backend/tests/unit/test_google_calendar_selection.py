"""Behavioral selection, pagination, account isolation and event-reference coverage."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from database import google_calendar_preferences as prefs
from routers import google_calendar as routes
from utils.retrieval import google_calendar_selection as selection
from utils.retrieval.tools import calendar_tools as tools
from utils.retrieval.tools.google_utils import GoogleAPIError


def calendar(identifier, *, primary=False, role='reader'):
    return {'id': identifier, 'primary': primary, 'accessRole': role, 'summary': identifier}


def event(identifier, hour):
    return {
        'id': identifier,
        'summary': identifier,
        'start': {'dateTime': f'2026-11-01T{hour:02}:00:00Z'},
        'end': {'dateTime': f'2026-11-01T{hour+1:02}:00:00Z'},
    }


@pytest.fixture
def provider(monkeypatch):
    # Persistence is owned by the real database helper; this fixture substitutes
    # its I/O only. Emulator integration separately checks its Firestore merge.
    store = {}
    owner = {'primary': 'personal@example.test'}
    calendars = [calendar(owner['primary'], primary=True, role='owner'), calendar('team/#?@group.test')]
    calls = []

    async def request(method, url, token, params=None, body=None, **kwargs):
        calls.append((method, url, dict(params or {})))
        if url.endswith('/calendarList'):
            rows = [dict(row) for row in calendars]
            rows[0]['id'] = owner['primary']
            return {'items': rows}
        if '/calendars/primary/events' in url:
            return {'items': [event('same-id', 12)]}
        if '/events/' in url:
            return event(url.rsplit('/', 1)[-1], 9)
        return {'items': [event('same-id', 9)]}

    monkeypatch.setattr(selection, 'google_api_request', request)
    monkeypatch.setattr(tools, 'google_api_request', request)
    monkeypatch.setattr(prefs, 'get_selections', lambda uid: store.get(uid, {}))

    def save(uid, primary, ids):
        store.setdefault(uid, {})[prefs.account_key(primary)] = ids

    monkeypatch.setattr(prefs, 'save_selection', save)
    monkeypatch.setattr(routes, '_get_google_calendar_token', lambda uid: ('synthetic-token', {'connected': True}))
    return store, owner, calendars, calls


@pytest.mark.asyncio
async def test_default_does_not_enumerate_or_expand_existing_primary_reads(provider):
    _, _, _, calls = provider
    rows = await tools.get_google_calendar_events('synthetic-token', uid='omi-A')
    assert [row['id'] for row in rows] == ['same-id']
    assert len(calls) == 1 and calls[0][1].endswith('/calendars/primary/events')


@pytest.mark.asyncio
@pytest.mark.parametrize('primary', ['personal@example.test', 'person@workspace.test'])
async def test_save_read_link_and_mutate_selected_calendar_with_colliding_ids(provider, primary):
    _, owner, _, calls = provider
    owner['primary'] = primary
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.auth.get_current_user_uid] = lambda: 'omi-A'
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://omi.test') as client:
        catalog = (await client.get('/v1/calendar/google/calendars')).json()
        assert catalog['selected_ids'] == [primary]
        assert catalog['write_calendar_id'] == 'primary'
        saved = await client.put(
            '/v1/calendar/google/calendars',
            json={
                'account_id': primary,
                'selected_ids': [primary, 'team/#?@group.test'],
            },
        )
        assert saved.status_code == 200
        response = await client.get(
            '/v1/calendar/google/events',
            params={
                'time_min': '2026-11-01T00:00:00Z',
                'time_max': '2026-11-02T00:00:00Z',
            },
        )
        assert response.status_code == 200
        rows = response.json()
        assert len(rows) == 2 and rows[0]['event_id'] != rows[1]['event_id']
        assert rows[1]['event_id'] == 'same-id'
        reference = rows[0]['event_id']
        linked = await tools.get_google_calendar_event('synthetic-token', reference)
        assert linked['id'] == reference
        await tools.update_google_calendar_event('synthetic-token', reference, summary='Edited')
        await tools.delete_google_calendar_event('synthetic-token', reference)
        assert calls[-1][0] == 'DELETE'
        assert calls[-1][1].endswith('/calendars/team%2F%23%3F%40group.test/events/same-id')
        assert all('/primary/' not in call[1] for call in calls[-3:])


@pytest.mark.asyncio
async def test_reconnect_same_google_account_preserves_selection_other_accounts_do_not_inherit(provider):
    store, owner, _, calls = provider
    store['omi-A'] = {prefs.account_key(owner['primary']): ['team/#?@group.test']}
    first = await tools.get_google_calendar_events('old-token', uid='omi-A')
    again = await tools.get_google_calendar_events('reconnected-token', uid='omi-A')
    assert first == again
    assert not any('/calendars/primary/events' in call[1] for call in calls)
    owner['primary'] = 'other@workspace.test'
    assert (await tools.get_google_calendar_events('other-google-token', uid='omi-A'))[0]['id'] == 'same-id'
    owner['primary'] = 'personal@example.test'
    assert (await tools.get_google_calendar_events('token', uid='omi-B'))[0]['id'] == 'same-id'
    assert (await tools.get_google_calendar_events('token', uid='omi-A')) == first


@pytest.mark.asyncio
async def test_unavailable_selection_is_visible_and_never_replaced_with_primary(provider):
    store, owner, calendars, calls = provider
    store['omi-A'] = {prefs.account_key(owner['primary']): ['removed-calendar']}
    data = await selection.catalog('omi-A', 'token')
    missing = next(row for row in data['calendars'] if row['id'] == 'removed-calendar')
    assert missing['available'] is False
    assert await tools.get_google_calendar_events('token', uid='omi-A') == []
    assert not any('/events' in call[1] for call in calls)
    data = await routes.save_google_calendar_selection(
        routes.CalendarSelectionUpdate(account_id=owner['primary'], selected_ids=[calendars[1]['id']]), uid='omi-A'
    )
    assert data['selected_ids'] == [calendars[1]['id']]


@pytest.mark.asyncio
async def test_stale_account_or_unreadable_calendar_cannot_change_preferences(provider):
    store, owner, _, _ = provider
    for account, ids in [('old-account', ['team/#?@group.test']), (owner['primary'], ['not-granted'])]:
        with pytest.raises(routes.HTTPException) as error:
            await routes.save_google_calendar_selection(
                routes.CalendarSelectionUpdate(account_id=account, selected_ids=ids), uid='omi-A'
            )
        assert error.value.status_code == 409
    assert store == {}


@pytest.mark.asyncio
async def test_saved_unavailable_calendar_can_be_retained_but_not_newly_added(provider):
    store, owner, _, _ = provider
    store['omi-A'] = {prefs.account_key(owner['primary']): ['removed-calendar']}
    saved = await routes.save_google_calendar_selection(
        routes.CalendarSelectionUpdate(
            account_id=owner['primary'], selected_ids=['removed-calendar', 'team/#?@group.test']
        ),
        uid='omi-A',
    )
    assert saved['selected_ids'] == ['removed-calendar', 'team/#?@group.test']
    with pytest.raises(routes.HTTPException) as error:
        await routes.save_google_calendar_selection(
            routes.CalendarSelectionUpdate(account_id=owner['primary'], selected_ids=['different-removed-calendar']),
            uid='omi-A',
        )
    assert error.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize('corrupt', [None, [], ['']])
async def test_corrupt_saved_scope_fails_closed_instead_of_reading_primary(provider, corrupt):
    store, owner, _, calls = provider
    store['omi-A'] = {prefs.account_key(owner['primary']): corrupt}
    with pytest.raises(ValueError):
        await tools.get_google_calendar_events('token', uid='omi-A')
    assert not any('/events' in call[1] for call in calls)


@pytest.mark.asyncio
async def test_catalog_and_each_calendar_have_independent_pagination(provider, monkeypatch):
    store, owner, _, _ = provider
    store['omi-A'] = {prefs.account_key(owner['primary']): ['primary', 'secondary']}
    calls = []

    async def request(method, url, token, params=None, **kwargs):
        page = (params or {}).get('pageToken')
        calls.append((url, page))
        if url.endswith('/calendarList'):
            return (
                {'items': [calendar(owner['primary'], primary=True, role='owner')], 'nextPageToken': 'catalog-2'}
                if not page
                else {'items': [calendar('secondary')]}
            )
        if url.endswith('/primary/events'):
            return (
                {'items': [event('primary-1', 11)], 'nextPageToken': 'primary-2'}
                if not page
                else {'items': [event('primary-2', 13)]}
            )
        return {'items': [], 'nextPageToken': 'secondary-2'} if not page else {'items': [event('secondary-2', 8)]}

    monkeypatch.setattr(selection, 'google_api_request', request)
    monkeypatch.setattr(tools, 'google_api_request', request)
    result = await tools.get_google_calendar_events('token', uid='omi-A', max_results=3)
    assert [row['start']['dateTime'][11:13] for row in result] == ['08', '11', '13']
    assert calls[-2][1] is None and calls[-1][1] == 'secondary-2'


@pytest.mark.asyncio
async def test_revocation_after_catalog_keeps_other_selected_calendars_but_auth_and_5xx_fail(provider, monkeypatch):
    store, owner, _, _ = provider
    store['omi-A'] = {prefs.account_key(owner['primary']): ['primary', 'team/#?@group.test']}
    status = {'value': 403}

    async def events(method, url, token, **kwargs):
        if '/calendars/primary/events' in url:
            return {'items': [event('kept', 10)]}
        raise GoogleAPIError(status['value'], 'provider-private-detail')

    monkeypatch.setattr(tools, 'google_api_request', events)
    assert [row['id'] for row in await tools.get_google_calendar_events('token', uid='omi-A')] == ['kept']
    for code in [401, 500]:
        status['value'] = code
        with pytest.raises(GoogleAPIError):
            await tools.get_google_calendar_events('token', uid='omi-A')


@pytest.mark.parametrize('value', ['omi-gcal:!!', 'omi-gcal:bnVsbA', 'omi-gcal:WyJhIl0'])
def test_malformed_reference_fails_before_any_provider_write(value):
    with pytest.raises(ValueError):
        selection.event_path(value)


def test_legacy_event_id_is_escaped_and_stays_on_primary():
    assert selection.event_path('event/#?') == selection.BASE + '/calendars/primary/events/event%2F%23%3F'


def test_disconnected_grant_status_keeps_explicit_scope_and_owner_isolation(provider, monkeypatch):
    from routers import integrations

    store, owner, _, _ = provider
    monkeypatch.setattr(integrations.users_db, 'get_integration', lambda *_: {'connected': False})
    status = integrations.get_integration('google_calendar', uid='omi-A')
    assert status.connected is False and status.read_selection_configured is False
    store['omi-A'] = {prefs.account_key(owner['primary']): ['team/#?@group.test']}
    status = integrations.get_integration('google_calendar', uid='omi-A')
    assert status.connected is False and status.read_selection_configured is True
    assert integrations.get_integration('google_calendar', uid='omi-B').read_selection_configured is False
