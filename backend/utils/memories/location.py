import os
from typing import Optional

import requests

from models.memory import Geolocation


def get_google_maps_location(latitude: float, longitude: float) -> Optional[Geolocation]:
    print('get_google_maps_location', latitude, longitude)
    # TODO: cache this
    key = os.getenv('GOOGLE_MAPS_API_KEY')
    url = f"https://maps.googleapis.com/maps/api/geocode/json?latlng={latitude},{longitude}&key={key}"
    response = requests.get(url)
    data = response.json()
    print('get_google_maps_location', data)
    if data['status'] != 'OK' or not data.get('results'):
        return None
    place = data['results'][0]
    if not place['place_id']:
        return None

    return Geolocation(
        google_place_id=place['place_id'],
        latitude=latitude,
        longitude=longitude,
        address=place.get('formatted_address'),
        location_type=place['types'][0] if place.get('types') else None,
    )
