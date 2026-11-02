"""Usage-only Soniox spend sample for the backend-listen cost receipt."""

from __future__ import annotations

import asyncio
import logging
import math
import os
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import httpx
from prometheus_client import Gauge

logger = logging.getLogger(__name__)

SONIOX_MONTH_SPEND = Gauge('omi_soniox_month_spend_usd', 'Current-month Soniox spend in USD')
SONIOX_USAGE_SOURCE = Gauge('omi_soniox_usage_source', 'Active Soniox usage source', ['source'])
SONIOX_USAGE_SAMPLE_TIMESTAMP = Gauge('omi_soniox_usage_sample_timestamp_seconds', 'Last successful spend sample')


def parse_usage_summary(payload: object) -> float:
    if not isinstance(payload, dict) or not isinstance(payload.get('total'), dict):
        raise ValueError('Soniox usage summary missing total')
    try:
        amount = Decimal(str(payload['total']['total_cost_usd']))
    except (KeyError, InvalidOperation) as error:
        raise ValueError('Soniox usage summary missing cost') from error
    if not amount.is_finite() or amount < 0 or not math.isfinite(float(amount)):
        raise ValueError('Soniox usage summary invalid cost')
    return float(amount)


async def _vendor_month_spend(now: datetime) -> float:
    key = os.getenv('SONIOX_API_KEY', '').strip()
    if not key:
        raise ValueError('Soniox API key unavailable')
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    async with httpx.AsyncClient(timeout=httpx.Timeout(3.0, connect=1.0)) as client:
        response = await asyncio.wait_for(
            client.get(
                'https://api.soniox.com/v1/usage/summary',
                headers={'Authorization': f'Bearer {key}'},
                params={
                    'start_time': month_start.isoformat().replace('+00:00', 'Z'),
                    'end_time': now.isoformat().replace('+00:00', 'Z'),
                },
            ),
            timeout=5.0,
        )
        response.raise_for_status()
        return parse_usage_summary(response.json())


async def poll_once(now: datetime | None = None) -> float | None:
    now = now or datetime.now(timezone.utc)
    try:
        spent = await _vendor_month_spend(now)
    except Exception:
        SONIOX_USAGE_SOURCE.labels(source='vendor').set(0)
        SONIOX_USAGE_SOURCE.labels(source='unavailable').set(1)
        logger.warning('Soniox usage API read failed; retaining last successful spend sample')
        return None
    SONIOX_MONTH_SPEND.set(spent)
    SONIOX_USAGE_SOURCE.labels(source='vendor').set(1)
    SONIOX_USAGE_SOURCE.labels(source='unavailable').set(0)
    SONIOX_USAGE_SAMPLE_TIMESTAMP.set(now.timestamp())
    return spent


async def poll_forever() -> None:
    while True:
        await poll_once()
        await asyncio.sleep(3600)


def start_if_configured(start_background_task: Callable[..., object]) -> None:
    if os.getenv('SONIOX_API_KEY', '').strip():
        start_background_task(poll_forever(), name='soniox_usage')
