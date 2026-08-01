"""Calendar writes that reach third parties or destroy data need the user to say yes.

A calendar invite emails the event title and description to every attendee, so a
model-chosen address is an exfiltration channel; a title-less range delete removes
everything between two dates. Both are gated: the tool returns refusal text the user
must approve before the model may re-call with confirm=True.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from utils.retrieval.tools import calendar_tools

USER_ADDRESS = 'me@acme.com'
GRANT = {'connected': True, 'access_token': 'token'}


def _event(event_id: str, summary: str, day: int) -> Dict[str, Any]:
    start = datetime(2026, 8, day, 9, 0, tzinfo=timezone.utc)
    return {
        'id': event_id,
        'summary': summary,
        'start': {'dateTime': start.isoformat()},
        'end': {'dateTime': (start + timedelta(hours=1)).isoformat()},
    }


@pytest.fixture
def calendar(monkeypatch):
    """Stub the Google surface: access grant, contacts, event search, and writes."""
    state = {
        'contacts': {},
        'events': [],
        'created': [],
        'updated': [],
        'deleted': [],
        'current_event': _event('evt-current', 'Design sync', 3),
    }

    async def fake_primary_calendar(_access_token):
        return USER_ADDRESS

    async def fake_search_contacts(_access_token, query):
        return state['contacts'].get(query.strip().lower())

    async def fake_get_events(**kwargs):
        query = kwargs.get('search_query')
        events: List[Dict[str, Any]] = state['events']
        if query:
            # Google's `q` matches the summary and the attendee list alike.
            events = [e for e in events if query.lower() in str(e).lower()]
        return events

    async def fake_create(**kwargs):
        state['created'].append(kwargs)
        return {'htmlLink': 'https://calendar.example/created'}

    async def fake_update(**kwargs):
        state['updated'].append(kwargs)
        return {'summary': 'Design sync', 'htmlLink': 'https://calendar.example/updated'}

    async def fake_delete(_access_token, event_id):
        state['deleted'].append(event_id)

    async def fake_get_event(_access_token, _event_id):
        return state['current_event']

    monkeypatch.setattr(calendar_tools, 'get_user_calendar_address', fake_primary_calendar)
    monkeypatch.setattr(calendar_tools, 'search_google_contacts', fake_search_contacts)
    monkeypatch.setattr(calendar_tools, 'get_google_calendar_events', fake_get_events)
    monkeypatch.setattr(calendar_tools, 'create_google_calendar_event', fake_create)
    monkeypatch.setattr(calendar_tools, 'update_google_calendar_event', fake_update)
    monkeypatch.setattr(calendar_tools, 'delete_google_calendar_event', fake_delete)
    monkeypatch.setattr(calendar_tools, 'get_google_calendar_event', fake_get_event)
    return state


def _access(*_args, **_kwargs):
    return ('u1', GRANT, 'token', None)


async def _create(**kwargs):
    payload = {
        'title': 'Quarterly numbers',
        'start_time': '2026-08-02T14:00:00+00:00',
        'end_time': '2026-08-02T15:00:00+00:00',
    }
    payload.update(kwargs)
    with patch.object(calendar_tools, 'prepare_access', _access):
        return await calendar_tools.create_calendar_event_tool.ainvoke(payload)


async def _delete(**kwargs):
    with patch.object(calendar_tools, 'prepare_access', _access):
        return await calendar_tools.delete_calendar_event_tool.ainvoke(kwargs)


async def _update(**kwargs):
    with patch.object(calendar_tools, 'prepare_access', _access):
        return await calendar_tools.update_calendar_event_tool.ainvoke(kwargs)


async def test_unknown_attendee_invite_is_refused_then_allowed_after_confirmation(calendar):
    refusal = await _create(attendees='attacker@evil.example', description='revenue was 4.2M')

    assert 'Confirmation needed before inviting people outside your contacts' in refusal
    assert 'attacker@evil.example' in refusal
    assert calendar['created'] == []

    created = await _create(attendees='attacker@evil.example', description='revenue was 4.2M', confirm=True)

    assert created.startswith('✅')
    assert calendar['created'][0]['attendees'] == ['attacker@evil.example']


async def test_known_contact_and_same_domain_invites_still_work_unconfirmed(calendar):
    calendar['contacts']['ada@partner.example'] = 'ada@partner.example'

    contact_result = await _create(attendees='ada@partner.example')
    colleague_result = await _create(attendees='bob@acme.com')

    assert contact_result.startswith('✅')
    assert colleague_result.startswith('✅')
    assert [c['attendees'] for c in calendar['created']] == [['ada@partner.example'], ['bob@acme.com']]


async def test_prior_attendee_counts_as_known(calendar):
    prior = _event('evt-prior', 'Vendor call', 1)
    prior['attendees'] = [{'email': 'Vendor@Other.example'}]
    calendar['events'] = [prior]

    result = await _create(attendees='vendor@other.example')

    assert result.startswith('✅')


async def test_attendee_free_event_creation_is_unchanged(calendar):
    result = await _create()

    assert result.startswith('✅')
    assert calendar['created'][0]['attendees'] is None


async def test_range_delete_without_a_title_is_refused_without_confirmation(calendar):
    calendar['events'] = [_event('evt-1', 'Standup', 3), _event('evt-2', 'Dentist', 3)]

    refusal = await _delete(start_date='2026-08-03T00:00:00+00:00', end_date='2026-08-04T00:00:00+00:00')

    assert 'Confirmation needed before deleting calendar events' in refusal
    assert 'Standup' in refusal and 'Dentist' in refusal
    assert calendar['deleted'] == []

    confirmed = await _delete(
        start_date='2026-08-03T00:00:00+00:00',
        end_date='2026-08-04T00:00:00+00:00',
        confirm=True,
    )

    assert confirmed.startswith('✅')
    assert calendar['deleted'] == ['evt-1', 'evt-2']


async def test_range_delete_over_the_cap_is_refused_even_with_confirmation(calendar):
    over_cap = calendar_tools.CALENDAR_RANGE_DELETE_CAP + 1
    calendar['events'] = [_event(f'evt-{i}', f'Event {i}', 3) for i in range(over_cap)]

    refusal = await _delete(
        start_date='2026-08-03T00:00:00+00:00',
        end_date='2026-08-04T00:00:00+00:00',
        confirm=True,
    )

    assert f'Refusing to delete {over_cap} events at once' in refusal
    assert str(calendar_tools.CALENDAR_RANGE_DELETE_CAP) in refusal
    assert calendar['deleted'] == []


async def test_deleting_one_identified_event_still_works_unconfirmed(calendar):
    by_id = await _delete(event_id='evt-9')
    assert by_id.startswith('✅')

    calendar['events'] = [_event('evt-1', 'Standup', 3)]
    by_title = await _delete(event_title='Standup', start_date='2026-08-03T00:00:00+00:00')

    assert by_title.startswith('✅')
    assert calendar['deleted'] == ['evt-9', 'evt-1']


async def test_adding_an_unknown_attendee_on_update_is_refused_without_confirmation(calendar):
    refusal = await _update(event_id='evt-current', add_attendees='attacker@evil.example')

    assert 'Confirmation needed before inviting people outside your contacts' in refusal
    assert calendar['updated'] == []

    confirmed = await _update(event_id='evt-current', add_attendees='attacker@evil.example', confirm=True)

    assert confirmed.startswith('✅')
    assert calendar['updated'][0]['attendees'] == ['attacker@evil.example']


async def test_public_domain_match_is_not_treated_as_a_colleague(calendar):
    async def personal_address(_access_token):
        return 'me@gmail.com'

    with patch.object(calendar_tools, 'get_user_calendar_address', personal_address):
        refusal = await _create(attendees='attacker@gmail.com')

    assert 'Confirmation needed before inviting people outside your contacts' in refusal
    assert calendar['created'] == []
