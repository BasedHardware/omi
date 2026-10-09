"""Actual Soniox monthly cost wins; metered audio estimates when it is unavailable."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from utils.stt import soniox_runway as runway


def test_usage_summary_rejects_missing_or_invalid_money():
    assert runway.parse_usage_summary({'total': {'total_cost_usd': '7000.25'}}) == 7000.25
    for payload in ({}, {'total': {}}, {'total': {'total_cost_usd': '-1'}}, {'total': {'total_cost_usd': 'NaN'}}):
        with pytest.raises(ValueError):
            runway.parse_usage_summary(payload)


class BrokenRedis:
    async def set(self, *_args, **_kwargs):
        raise ConnectionError('Redis down')

    async def get(self, *_args, **_kwargs):
        raise ConnectionError('Redis down')


@pytest.mark.asyncio
async def test_vendor_usage_succeeds_when_redis_is_down(monkeypatch):
    monkeypatch.setenv('SONIOX_MONTHLY_CEILING_USD', '10000')
    monkeypatch.setattr(runway, '_redis', lambda: BrokenRedis())

    async def vendor(_now):
        return 7000.25

    monkeypatch.setattr(runway, '_vendor_month_spend', vendor)
    value = await runway.poll_once(datetime(2026, 9, 28, tzinfo=timezone.utc))
    assert value == (7000.25, 'vendor')
    assert runway.SONIOX_MONTH_SPEND._value.get() == 7000.25
    assert runway.SONIOX_USAGE_SOURCE.labels(source='vendor')._value.get() == 1


@pytest.mark.asyncio
async def test_metered_audio_fallback_when_vendor_and_redis_are_down(monkeypatch):
    monkeypatch.setenv('SONIOX_MONTHLY_CEILING_USD', '10000')
    monkeypatch.setenv('SONIOX_ESTIMATED_USD_PER_HOUR', '0.075')
    monkeypatch.setattr(runway, '_redis', lambda: BrokenRedis())
    monkeypatch.setattr(runway, '_month', lambda _now=None: '202609')
    monkeypatch.setattr(runway, '_poll_loop', None)

    async def fail(_now):
        raise ConnectionError('vendor down')

    monkeypatch.setattr(runway, '_vendor_month_spend', fail)
    with runway._local_lock:
        runway._local_month, runway._local_seconds = '202609', 0.0
    runway.meter_audio_seconds(3600)
    value = await runway.poll_once(datetime(2026, 9, 28, tzinfo=timezone.utc))
    assert value == (0.075, 'estimated')
    assert runway.SONIOX_USAGE_SOURCE.labels(source='estimated')._value.get() == 1
