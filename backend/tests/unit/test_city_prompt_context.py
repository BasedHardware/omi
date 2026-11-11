import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from utils.conversations.location import async_get_google_maps_city


def test_city_context_uses_cached_value_without_calling_maps():
    with patch('utils.conversations.location.r') as redis, patch(
        'utils.conversations.location.get_maps_client'
    ) as client:
        redis.get.return_value = b'New York, New York, United States'

        assert asyncio.run(async_get_google_maps_city(40.7128, -74.006)) == 'New York, New York, United States'
        client.assert_not_called()


def test_city_context_uses_locality_and_never_returns_coordinates():
    @asynccontextmanager
    async def semaphore():
        yield

    response = MagicMock()
    response.json.return_value = {
        'status': 'OK',
        'results': [
            {
                'address_components': [
                    {'long_name': 'New York', 'types': ['locality']},
                    {'long_name': 'New York', 'types': ['administrative_area_level_1']},
                    {'long_name': 'United States', 'types': ['country']},
                ]
            }
        ],
    }
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    with patch('utils.conversations.location.r') as redis, patch(
        'utils.conversations.location.get_maps_client', return_value=client
    ), patch('utils.conversations.location.get_maps_semaphore', return_value=semaphore()):
        redis.get.return_value = None

        assert asyncio.run(async_get_google_maps_city(40.7128, -74.006)) == 'New York, New York, United States'
        assert '40.7128' not in redis.set.call_args.args[1]
        assert redis.set.call_args.kwargs['ex'] == 172800
