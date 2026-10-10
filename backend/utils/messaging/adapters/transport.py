"""Bounded provider IO. Exceptions contain no URL, token, body or message content."""

import asyncio
import logging
from urllib.parse import urlparse
from typing import Any

import httpx
from utils.http_client import get_webhook_client


class ProviderError(RuntimeError):
    pass


class DeliveryUncertain(ProviderError):
    """The provider may have accepted the send; operator reconciliation required."""


class ProviderLogFilter(logging.Filter):
    def filter(self, record):
        # HTTPX's INFO request receipt includes Telegram tokens and signed CDN
        # URLs. Suppress receipts for the provider hosts rather than log credentials.
        message = record.getMessage()
        return not any(host in message for host in ('api.telegram.org', 'linqapp.com'))


class Transport:
    def __init__(self):
        for name in ('httpx', 'httpcore'):
            logger = logging.getLogger(name)
            if not any(isinstance(f, ProviderLogFilter) for f in logger.filters):
                logger.addFilter(ProviderLogFilter())

    async def request(self, method, url, **kwargs):
        client = get_webhook_client()
        try:
            return await client.request(method, url, timeout=30, follow_redirects=False, **kwargs)
        except httpx.HTTPError:
            raise DeliveryUncertain('Provider transport outcome unknown') from None

    async def download(self, url, *, allowed_hosts, max_bytes=20_000_000, headers=None):
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.hostname not in allowed_hosts or parsed.username or parsed.port:
            raise PermissionError('Untrusted media location')
        client = get_webhook_client()
        try:
            async with client.stream('GET', url, headers=headers, timeout=30, follow_redirects=False) as response:
                if response.status_code != 200:
                    raise ProviderError('Media unavailable')
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > max_bytes:
                        raise ValueError('Media too large')
                return bytes(data)
        except httpx.HTTPError:
            raise ProviderError('Media transport failed') from None


async def request_json(transport, method, url, *, idempotent=False, sleep=asyncio.sleep, **kwargs) -> dict[str, Any]:
    from utils.messaging.delivery_context import send_guard

    for attempt in range(4):
        guard = send_guard.get()
        if guard is not None:
            await guard()
        try:
            response = await transport.request(method, url, **kwargs)
        except DeliveryUncertain:
            if not idempotent or attempt == 3:
                raise
            await sleep(2**attempt)
            continue
        try:
            value = response.json() if response.content else {}
        except ValueError:
            raise ProviderError('Invalid provider response') from None
        if not isinstance(value, dict):
            raise ProviderError('Invalid provider response shape')
        status = response.status_code
        if status == 429 or value.get('error_code') == 429:
            delay = value.get('parameters', {}).get('retry_after', response.headers.get('Retry-After', 1))
            try:
                delay = float(delay)
            except (TypeError, ValueError):
                delay = 1
            if not 0 <= delay <= 60 or attempt == 3:
                raise ProviderError('Provider rate limit; retry later')
            await sleep(max(delay, 0.1))
            continue
        if status >= 500:
            if not idempotent:
                raise DeliveryUncertain('Provider send outcome unknown')
            if attempt < 3:
                await sleep(2**attempt)
                continue
        if status >= 400 or value.get('ok') is False:
            raise ProviderError('Provider rejected request')
        return value
    raise ProviderError('Provider retry budget exhausted')
