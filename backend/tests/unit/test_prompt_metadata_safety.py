from pydantic import ValidationError

from models.geolocation import Geolocation
from utils.llm.chat import get_current_datetime_block


def test_prompt_metadata_escapes_city_text():
    metadata = get_current_datetime_block('uid1', tz='UTC', location='A < B & C')

    assert 'Recent city-level location: A &lt; B &amp; C' in metadata


def test_geolocation_rejects_coordinates_outside_the_earth():
    for latitude, longitude in ((90.1, 0), (0, 180.1), (float('nan'), 0)):
        try:
            Geolocation(latitude=latitude, longitude=longitude)
        except ValidationError:
            continue
        raise AssertionError('invalid geolocation was accepted')
