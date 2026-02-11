import json
import logging
import os
from typing import Optional

import requests

from database.redis_db import r
from models.conversation import Geolocation


def get_google_maps_location(latitude: float, longitude: float) -> Optional[Geolocation]:
    print('get_google_maps_location', latitude, longitude)

    # Round to ~100m precision for cache key
    rounded = f"{latitude:.3f},{longitude:.3f}"
    cache_key = f"geocode:{rounded}"

    # Check Redis cache
    try:
        cached = r.get(cache_key)
        if cached:
            data = json.loads(cached)
            return Geolocation(**data)
    except Exception as e:
        logging.warning('Failed to read geocode cache for key %s: %s', cache_key, e)

    key = os.getenv('GOOGLE_MAPS_API_KEY')
    url = f"https://maps.googleapis.com/maps/api/geocode/json?latlng={latitude},{longitude}&key={key}"
    response = requests.get(url)
    data = response.json()
    if data['status'] != 'OK' or not data.get('results'):
        return None
    place = data['results'][0]
    if not place.get('place_id'):
        return None

    geo = Geolocation(
        google_place_id=place['place_id'],
        latitude=latitude,
        longitude=longitude,
        address=place.get('formatted_address'),
        location_type=place['types'][0] if place.get('types') else None,
    )

    # Cache in Redis (48h TTL)
    try:
        r.set(cache_key, json.dumps(geo.model_dump()), ex=172800)
    except Exception as e:
        logging.warning('Failed to cache geocode for key %s: %s', cache_key, e)

    return geo
