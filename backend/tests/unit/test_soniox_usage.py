from __future__ import annotations

from datetime import datetime, timezone

import pytest

from utils.stt import soniox_usage as usage


@pytest.mark.parametrize(
    ('payload', 'expected'),
    [
        ({'total': {'total_cost_usd': '7000.25'}}, 7000.25),
        ({'total': {'total_cost_usd': 0}}, 0.0),
    ],
)
def test_parse_usage_summary_accepts_valid_cost(payload, expected):
    assert usage.parse_usage_summary(payload) == expected


@pytest.mark.parametrize(
    'payload',
    [
        {},
        {'total': []},
        {'total': {}},
        {'total': {'total_cost_usd': '-1'}},
        {'total': {'total_cost_usd': 'NaN'}},
        {'total': {'total_cost_usd': 'Infinity'}},
        {'total': {'total_cost_usd': '1e10000'}},
    ],
)
def test_parse_usage_summary_rejects_invalid_cost(payload):
    with pytest.raises(ValueError):
        usage.parse_usage_summary(payload)


@pytest.mark.asyncio
async def test_vendor_reads_month_summary_with_bearer_key(monkeypatch):
    request = {}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {'total': {'total_cost_usd': '19.75'}}

    class AsyncClient:
        def __init__(self, **kwargs):
            request['timeout'] = kwargs['timeout']

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def get(self, url, *, headers, params):
            request.update(url=url, headers=headers, params=params)
            return Response()

    monkeypatch.setenv('SONIOX_API_KEY', 'test-key')
    monkeypatch.setattr(usage.httpx, 'AsyncClient', AsyncClient)
    now = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)

    assert await usage._vendor_month_spend(now) == 19.75
    assert request['url'] == 'https://api.soniox.com/v1/usage/summary'
    assert request['headers'] == {'Authorization': 'Bearer test-key'}
    assert request['params'] == {
        'start_time': '2026-10-01T00:00:00Z',
        'end_time': '2026-10-20T12:00:00Z',
    }


@pytest.mark.asyncio
async def test_success_updates_usage_gauges(monkeypatch):
    async def vendor(_now):
        return 19.75

    monkeypatch.setattr(usage, '_vendor_month_spend', vendor)
    now = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)

    assert await usage.poll_once(now) == 19.75
    assert usage.SONIOX_MONTH_SPEND._value.get() == 19.75
    assert usage.SONIOX_USAGE_SOURCE.labels(source='vendor')._value.get() == 1
    assert usage.SONIOX_USAGE_SOURCE.labels(source='unavailable')._value.get() == 0
    assert usage.SONIOX_USAGE_SAMPLE_TIMESTAMP._value.get() == now.timestamp()


@pytest.mark.asyncio
async def test_vendor_failure_keeps_last_sample_and_sets_unavailable(monkeypatch):
    usage.SONIOX_MONTH_SPEND.set(42.5)
    usage.SONIOX_USAGE_SAMPLE_TIMESTAMP.set(123.0)

    async def fail(_now):
        raise ConnectionError('vendor response omitted')

    monkeypatch.setattr(usage, '_vendor_month_spend', fail)
    result = await usage.poll_once(datetime(2026, 10, 20, tzinfo=timezone.utc))

    assert result is None
    assert usage.SONIOX_MONTH_SPEND._value.get() == 42.5
    assert usage.SONIOX_USAGE_SAMPLE_TIMESTAMP._value.get() == 123.0
    assert usage.SONIOX_USAGE_SOURCE.labels(source='vendor')._value.get() == 0
    assert usage.SONIOX_USAGE_SOURCE.labels(source='unavailable')._value.get() == 1


def test_poller_does_not_start_without_api_key(monkeypatch):
    started = []

    def start(task, *, name):
        started.append(name)
        task.close()

    monkeypatch.delenv('SONIOX_API_KEY', raising=False)
    usage.start_if_configured(start)
    assert started == []

    monkeypatch.setenv('SONIOX_API_KEY', 'test-key')
    usage.start_if_configured(start)
    assert started == ['soniox_usage']
