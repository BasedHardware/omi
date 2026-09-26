"""The desktop connector reads calendar events through the OAuth grant instead of
scraping browser cookies, so the event payload has to carry the fields the
memory extractor used to get straight from Google: location, description, and
whether the event is all-day.
"""

from routers.google_calendar import _event_to_response


def _timed_event(**overrides):
    event = {
        'id': 'evt-1',
        'summary': 'Design review',
        'start': {'dateTime': '2026-08-26T15:00:00Z'},
        'end': {'dateTime': '2026-08-26T16:00:00Z'},
        'location': 'Room 4',
        'description': 'Walk through the new connector flow.',
    }
    event.update(overrides)
    return event


def test_timed_event_carries_location_and_description():
    response = _event_to_response(_timed_event())

    assert response is not None
    assert response.location == 'Room 4'
    assert response.description == 'Walk through the new connector flow.'
    assert response.all_day is False


def test_all_day_event_is_flagged():
    response = _event_to_response(_timed_event(start={'date': '2026-08-26'}, end={'date': '2026-08-27'}))

    assert response is not None
    assert response.all_day is True


def test_missing_optional_fields_become_empty_strings():
    event = _timed_event()
    del event['location']
    event['description'] = None

    response = _event_to_response(event)

    assert response is not None
    assert response.location == ''
    assert response.description == ''


def test_long_free_text_is_truncated_for_transport():
    response = _event_to_response(_timed_event(location='L' * 500, description='D' * 900))

    assert response is not None
    assert len(response.location) == 200
    assert len(response.description) == 300
