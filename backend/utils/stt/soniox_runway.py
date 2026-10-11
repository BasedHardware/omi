"""Monthly Soniox runway from its usage API, with metered-audio fallback.

The poller runs outside listen requests. Every vendor and Redis operation has a
deadline; failed reads never alter provider admission or session delivery.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import threading
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
import redis.asyncio as aioredis
from prometheus_client import Gauge

logger = logging.getLogger(__name__)

SONIOX_MONTH_SPEND = Gauge('omi_soniox_month_spend_usd', 'Current-month Soniox spend in USD')
SONIOX_MONTH_CEILING = Gauge('omi_soniox_month_ceiling_usd', 'Configured monthly Soniox spend ceiling in USD')
SONIOX_USAGE_SOURCE = Gauge('omi_soniox_usage_source', 'Active Soniox usage source', ['source'])
SONIOX_USAGE_SAMPLE_TIMESTAMP = Gauge('omi_soniox_usage_sample_timestamp_seconds', 'Last successful spend sample')

_local_lock = threading.Lock()
_local_month = ''
_local_seconds = 0.0
_poll_loop: asyncio.AbstractEventLoop | None = None
_redis_client: Any = None


def _month(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime('%Y%m')


def _ceiling() -> float:
    try:
        value = float(os.getenv('SONIOX_MONTHLY_CEILING_USD', '0'))
        return value if math.isfinite(value) and value > 0 else 0.0
    except ValueError:
        return 0.0


def _price() -> float:
    try:
        value = float(os.getenv('SONIOX_ESTIMATED_USD_PER_HOUR', '0.07537'))
        return value if math.isfinite(value) and value >= 0 else 0.07537
    except ValueError:
        return 0.07537


def _redis() -> Any:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.Redis(
            host=os.getenv('REDIS_DB_HOST') or 'localhost',
            port=int(os.getenv('REDIS_DB_PORT', '6379')),
            password=os.getenv('REDIS_DB_PASSWORD'),
            socket_connect_timeout=0.075,
            socket_timeout=0.075,
            retry_on_timeout=False,
            decode_responses=True,
        )
    return _redis_client


async def _bounded(operation: Any) -> Any:
    return await asyncio.wait_for(operation, timeout=0.1)


def meter_audio_seconds(seconds: float) -> None:
    """Record Omi-served Soniox speech only; no blocking I/O on the usage path."""
    global _local_month, _local_seconds
    if seconds <= 0 or not math.isfinite(seconds):
        return
    month = _month()
    with _local_lock:
        if _local_month != month:
            _local_month, _local_seconds = month, 0.0
        _local_seconds += seconds
    loop = _poll_loop
    if loop is not None and not loop.is_closed() and _ceiling():
        try:
            loop.call_soon_threadsafe(lambda: loop.create_task(_write_meter(month, seconds)))
        except RuntimeError:
            pass


async def _write_meter(month: str, seconds: float) -> None:
    key = f'omi:live-stt:v1:soniox-meter:{month}'
    try:
        pipe = _redis().pipeline(transaction=False)
        pipe.incrbyfloat(key, seconds)
        pipe.expire(key, 65 * 24 * 3600)
        await _bounded(pipe.execute())
    except Exception:
        logger.debug('Soniox audio meter Redis write unavailable', exc_info=True)


def parse_usage_summary(payload: object) -> float:
    if not isinstance(payload, dict) or not isinstance(payload.get('total'), dict):
        raise ValueError('Soniox usage summary missing total')
    try:
        amount = Decimal(str(payload['total']['total_cost_usd']))
    except (KeyError, InvalidOperation) as error:
        raise ValueError('Soniox usage summary missing cost') from error
    if not amount.is_finite() or amount < 0:
        raise ValueError('Soniox usage summary invalid cost')
    return float(amount)


async def _vendor_month_spend(now: datetime) -> float:
    key = os.getenv('SONIOX_API_KEY')
    if not key:
        raise ValueError('Soniox API key unavailable')
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    async with httpx.AsyncClient(timeout=httpx.Timeout(3.0, connect=1.0)) as client:
        response = await client.get(
            'https://api.soniox.com/v1/usage/summary',
            headers={'Authorization': f'Bearer {key}'},
            params={
                'start_time': month_start.isoformat().replace('+00:00', 'Z'),
                'end_time': now.isoformat().replace('+00:00', 'Z'),
            },
        )
        response.raise_for_status()
        return parse_usage_summary(response.json())


async def _estimated_month_spend(month: str) -> float:
    try:
        raw = await _bounded(_redis().get(f'omi:live-stt:v1:soniox-meter:{month}'))
        if raw is not None:
            return max(0.0, float(raw)) / 3600 * _price()
    except Exception:
        logger.debug('Soniox fleet meter read unavailable', exc_info=True)
    with _local_lock:
        seconds = _local_seconds if _local_month == month else 0.0
    return seconds / 3600 * _price()


async def poll_once(now: datetime | None = None) -> tuple[float, str] | None:
    """Refresh metrics; a Redis lease keeps vendor reads to one pod per hour."""
    ceiling = _ceiling()
    if not ceiling:
        return None
    now = now or datetime.now(timezone.utc)
    month = _month(now)
    SONIOX_MONTH_CEILING.set(ceiling)
    source = 'estimated'
    spent: float | None = None
    try:
        leader = await _bounded(_redis().set(f'omi:live-stt:v1:soniox-poll:{month}', '1', nx=True, ex=3300))
        if leader:
            try:
                spent = await _vendor_month_spend(now)
                source = 'vendor'
                await _bounded(_redis().set(f'omi:live-stt:v1:soniox-usage:{month}', spent, ex=3600))
            except Exception:
                logger.warning('Soniox usage API read failed; using metered audio estimate')
        else:
            cached = await _bounded(_redis().get(f'omi:live-stt:v1:soniox-usage:{month}'))
            if cached is not None:
                spent, source = float(cached), 'vendor'
    except Exception:
        # Redis does not gate the poller. A transient failure may cause more
        # than one pod to query Soniox, but cannot hold up a listen session.
        try:
            spent, source = await _vendor_month_spend(now), 'vendor'
        except Exception:
            logger.warning('Soniox usage API read failed; using metered audio estimate')
    if spent is None:
        spent = await _estimated_month_spend(month)
    if not math.isfinite(spent) or spent < 0:
        return None
    SONIOX_MONTH_SPEND.set(spent)
    SONIOX_USAGE_SOURCE.labels(source='vendor').set(1 if source == 'vendor' else 0)
    SONIOX_USAGE_SOURCE.labels(source='estimated').set(1 if source == 'estimated' else 0)
    SONIOX_USAGE_SAMPLE_TIMESTAMP.set(now.timestamp())
    return spent, source


async def poll_forever() -> None:
    global _poll_loop
    _poll_loop = asyncio.get_running_loop()
    while True:
        try:
            await poll_once()
        except Exception:
            logger.exception('Soniox runway poll failed')
        await asyncio.sleep(3600)
