"""Real Firestore / real route / Google HTTP-adapter integration with synthetic calendars."""

import os
import uuid

import httpx
import pytest
from google.api_core.exceptions import NotFound

from database import google_calendar_preferences as preferences
from testing.google_calendar_fixture import calendar_fixture

pytestmark = pytest.mark.skipif(
    not os.environ.get('FIRESTORE_EMULATOR_HOST', '').startswith(('127.0.0.1:', 'localhost:')),
    reason='requires an explicitly started local Firestore emulator',
)


@pytest.mark.asyncio
async def test_selection_persists_reconnects_and_never_crosses_google_or_omi_accounts():
    uid = 'calendar-qa-' + uuid.uuid4().hex
    async with calendar_fixture(uid=uid) as (app, state, calls, db):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://omi.test') as client:
            path = '/v1/calendar/google/calendars'
            initial = (await client.get(path)).json()
            assert initial['selected_ids'] == [state['google_account']]
            result = await client.put(
                path, json={'account_id': state['google_account'], 'selected_ids': ['work@group.calendar.test']}
            )
            assert result.status_code == 200
            events = (await client.get('/v1/calendar/google/events')).json()
            assert [row['title'] for row in events] == ['Team meeting']
            # New helper invocation reads the actual stored document, not fixture
            # memory. A reconnected Google grant uses that same account key.
            assert preferences.get_selections(uid)[preferences.account_key(state['google_account'])] == [
                'work@group.calendar.test'
            ]
            assert (await client.get(path)).json()['selected_ids'] == ['work@group.calendar.test']
            state['google_account'] = 'other@workspace.test'
            assert (await client.get(path)).json()['selected_ids'] == ['other@workspace.test']
            # A stale picker cannot save Personal's selection to this grant.
            stale = await client.put(
                path, json={'account_id': initial['account_id'], 'selected_ids': ['work@group.calendar.test']}
            )
            assert stale.status_code == 409
            state['google_account'] = initial['account_id']
            state['secondary_available'] = False
            assert (await client.get('/v1/calendar/google/events')).json() == []
            unavailable = (await client.get(path)).json()
            assert any(not row['available'] for row in unavailable['calendars'])
            state['uid'] = uid + '-other'
            assert (await client.get(path)).json()['selected_ids'] == [initial['account_id']]
            state['uid'] = uid
            state['secondary_available'] = True
            assert (await client.get(path)).json()['selected_ids'] == ['work@group.calendar.test']
            assert any('/users/me/calendarList' in url for _, url in calls)
        db.collection('users').document(uid).delete()


@pytest.mark.asyncio
async def test_nested_field_update_preserves_other_google_accounts_and_cannot_recreate_deleted_owner():
    uid = 'calendar-qa-' + uuid.uuid4().hex
    async with calendar_fixture(uid=uid) as (_, _, _, db):
        preferences.save_selection(uid, 'first@example.test', ['primary'])
        preferences.save_selection(uid, 'second@workspace.test', ['team'])
        assert preferences.get_selections(uid) == {
            preferences.account_key('first@example.test'): ['primary'],
            preferences.account_key('second@workspace.test'): ['team'],
        }
        db.collection('users').document(uid).delete()
        with pytest.raises(NotFound):
            preferences.save_selection(uid, 'first@example.test', ['primary'])
        assert not db.collection('users').document(uid).get().exists
