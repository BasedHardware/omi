from contextlib import nullcontext
from datetime import datetime, timezone
from unittest.mock import patch

from pydantic import ValidationError

from models.conversation_photo import ConversationPhoto
from models.geolocation import (
    Geolocation,
    GeolocationInput,
    geolocation_from_private_header,
    validated_geolocation_or_none,
)
import utils.llm.chat as llm_chat
from utils.llm.chat import get_current_datetime_block


def test_prompt_metadata_escapes_city_text():
    metadata = get_current_datetime_block('uid1', tz='UTC', location='A < B & C')

    assert 'Current city-level location: A &lt; B &amp; C' in metadata


def test_current_datetime_block_mentions_relative_time_words():
    metadata = get_current_datetime_block('uid1', tz='America/Los_Angeles')

    assert 'tonight' in metadata
    assert 'America/Los_Angeles' in metadata


def test_current_datetime_block_marks_tool_times_as_already_converted():
    metadata = get_current_datetime_block('uid1', tz='Asia/Ho_Chi_Minh')

    assert 'Asia/Ho_Chi_Minh' in metadata
    assert 'already converted and labelled with their zone' in metadata
    assert 'report them as written and do not convert them again' in metadata
    assert '[+H:MM:SS] are elapsed offsets, not clock times' in metadata
    assert 'Relative time words' in metadata and 'are in Asia/Ho_Chi_Minh' in metadata


def test_transcript_photo_timestamps_use_the_users_timezone():
    photo = ConversationPhoto(
        id='photo-1',
        base64='image',
        description='meeting notes',
        created_at=datetime(2026, 9, 26, 7, 18, tzinfo=timezone.utc),
    )
    rendered: dict[str, str] = {}
    original_formatter = ConversationPhoto.photos_as_string

    def capture_photo_clock(photos, include_timestamps=False, *, started_at=None, clock=None):
        assert clock is not None
        rendered['zone'] = clock.name
        rendered['text'] = original_formatter(photos, include_timestamps, started_at=started_at, clock=clock)
        return rendered['text']

    with (
        patch.object(ConversationPhoto, 'photos_as_string', side_effect=capture_photo_clock),
        patch.object(llm_chat, 'track_usage', return_value=nullcontext()),
        patch.object(llm_chat, 'get_llm', side_effect=RuntimeError('offline')),
    ):
        result = llm_chat.retrieve_metadata_fields_from_transcript(
            'uid-1',
            datetime(2026, 9, 26, tzinfo=timezone.utc),
            [],
            'Asia/Ho_Chi_Minh',
            photos=[photo],
        )

    assert rendered['zone'] == 'Asia/Ho_Chi_Minh'
    assert '14:18 Asia/Ho_Chi_Minh (UTC+07:00)' in rendered['text']
    assert result == {'people': [], 'topics': [], 'entities': [], 'dates': []}


def test_geolocation_rejects_coordinates_outside_the_earth():
    for latitude, longitude in ((90.1, 0), (0, 180.1), (float('nan'), 0)):
        try:
            Geolocation(latitude=latitude, longitude=longitude)
        except ValidationError:
            continue
        raise AssertionError('invalid geolocation was accepted')


def test_released_geolocation_input_remains_accepted_but_invalid_values_are_never_usable():
    legacy_input = GeolocationInput(latitude=90.1, longitude=180.1)

    assert validated_geolocation_or_none(legacy_input) is None


def test_private_location_header_is_bounded_and_fails_soft():
    assert geolocation_from_private_header('{not json') is None
    assert geolocation_from_private_header('{"latitude":91,"longitude":0}') is None
    assert geolocation_from_private_header('x' * 4097) is None


def test_private_location_header_keeps_capture_provenance():
    result = geolocation_from_private_header(
        '{"latitude":40.7,"longitude":-74.0,"captured_at":"2026-08-01T12:00:00Z",'
        '"capture_source":"last_known_position","accuracy":12}'
    )

    assert result is not None
    assert result.capture_source == 'last_known_position'
    assert result.accuracy == 12
