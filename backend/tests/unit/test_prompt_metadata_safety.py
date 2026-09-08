from pydantic import ValidationError

from models.geolocation import (
    Geolocation,
    GeolocationInput,
    geolocation_from_private_header,
    validated_geolocation_or_none,
)
from utils.llm.chat import get_current_datetime_block


def test_prompt_metadata_escapes_city_text():
    metadata = get_current_datetime_block('uid1', tz='UTC', location='A < B & C')

    assert 'Current city-level location: A &lt; B &amp; C' in metadata


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
