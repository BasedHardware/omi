"""Bark delivery of preconfigured, counts-only operations pages."""

import httpx

from .publisher import REDIS

BARK_ENDPOINT = 'https://api.day.app/push'
REDIS_PANEL = 'https://monitor.omi.me/d/omi-resilience-fallbacks?viewPanel=2'


class Bark:
    def __init__(self, device_key, client):
        self.device_key = device_key
        self.client = client

    def send(self, route, recipient, channel):
        if (route, recipient, channel) != (REDIS.route_id, REDIS.recipient, REDIS.channel):
            return 'failed', 'destination_unconfigured'
        body = {
            'device_key': self.device_key,
            'title': 'Serving Redis degraded',
            'body': 'Check the serving-network Redis probe and cache-write failures.',
            'group': 'page-wake',
            'level': 'critical',
            'volume': '5',
            'call': '1',
            'url': REDIS_PANEL,
        }
        try:
            response = self.client.post(BARK_ENDPOINT, json=body, timeout=5, follow_redirects=False)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
            return 'retryable', 'no_connection'
        except httpx.HTTPError:
            return 'unknown', 'transport_ambiguous'

        if response.status_code == 429:
            return 'retryable', 'rate_limited'
        if response.status_code in (400, 401, 403, 404, 410, 422):
            return 'failed', 'provider_rejected'
        if response.status_code == 200:
            try:
                result = response.json()
                if isinstance(result, dict) and result.get('code') == 200:
                    return 'provider_accepted', 'bark_ok'
            except ValueError:
                pass
        return 'unknown', 'provider_response_ambiguous'
