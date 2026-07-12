"""get_google_maps_location returns None on a lookup failure instead of raising (-> HTTP 500).

The sync helper called httpx.get(url).json() unguarded, so a Maps network error or a non-JSON 5xx
response raised and surfaced as HTTP 500 on conversation create/finalize. Its async twin already
guards this and returns None; this mirrors it. location.py is light, so the test drives it directly
with the Redis cache patched to a miss and httpx.get patched to fail.
"""

import os

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

from unittest.mock import MagicMock, patch

import httpx

import utils.conversations.location as location


def _cache_miss():
    # r.get returns None so the helper proceeds past the cache to the HTTP lookup.
    return patch.object(location, 'r', MagicMock(get=MagicMock(return_value=None), set=MagicMock()))


def test_returns_none_on_http_error():
    with _cache_miss(), patch.object(location.httpx, 'get', side_effect=httpx.ConnectError('boom')):
        assert location.get_google_maps_location(1.0, 2.0) is None


def test_returns_none_on_non_json_response():
    resp = MagicMock()
    resp.json.side_effect = ValueError('not json')  # e.g. an HTML 5xx error page
    with _cache_miss(), patch.object(location.httpx, 'get', return_value=resp):
        assert location.get_google_maps_location(1.0, 2.0) is None
