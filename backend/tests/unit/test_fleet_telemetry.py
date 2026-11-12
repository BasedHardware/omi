"""Fleet ingestion contract, actual ASGI boundary and Prometheus deltas."""

import copy
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import generate_latest
from redis.exceptions import ConnectionError

from config.fleet_telemetry import FleetValidationError, MAX_BYTES, ROOT, max_series, registry, validate_summary
from routers import fleet_telemetry as route
from utils.observability import fleet
from utils.other.endpoints import get_current_user_uid
from utils.other import endpoints
from starlette.requests import Request
from unittest.mock import Mock
from scripts.generate_fleet_schema import schema


def summary():
    end = datetime.now(timezone.utc)
    return {
        'schema_version': 1,
        'platform': 'ios',
        'build_channel': 'stable',
        'app_version': '1.2.3',
        'window_start': (end - timedelta(minutes=15)).isoformat(),
        'window_end': end.isoformat(),
        'counters': [{'event': 'Device Connected', 'outcome': 'observed', 'count': 7}],
        'histograms': [],
    }


def histogram():
    name, spec = next(iter(registry()['histograms'].items()))
    return {'name': name, 'buckets': [{'le': edge, 'count': i + 1} for i, edge in enumerate(spec['buckets'])]}


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[get_current_user_uid] = lambda: 'test-user-never-a-label'
    monkeypatch.setattr(route, 'reserve_rate_limit', lambda *args, **kwargs: (True, 11, 3600))
    with TestClient(app) as client:
        yield client


def test_cardinality_and_generated_contract():
    assert json.loads((ROOT / 'fleet_schema.json').read_text()) == schema(registry())
    assert max_series() == 3842
    assert max_series() < 5000
    assert not set(registry()['server_observed_events']) & set(registry()['events'])


@pytest.mark.parametrize(
    'change,reason',
    [
        (lambda p: p.update(uid='bad'), 'invalid_schema'),
        (lambda p: p.update(platform='unbounded'), 'invalid_schema'),
        (lambda p: p.update(build_channel='user-generated'), 'invalid_schema'),
        (lambda p: p.update(schema_version=True), 'invalid_schema'),
        (lambda p: p['counters'][0].update(event='unknown'), 'unknown_event'),
        (lambda p: p['counters'][0].update(event='Recording Upload Started'), 'unknown_event'),
        (lambda p: p['counters'][0].update(outcome='raw error'), 'unknown_outcome'),
        (lambda p: p['counters'][0].update(count=-1), 'invalid_schema'),
        (lambda p: p['counters'][0].update(count=True), 'invalid_schema'),
        (lambda p: p['counters'][0].update(count=1.5), 'invalid_schema'),
        (lambda p: p['counters'][0].update(count=1_000_001), 'invalid_schema'),
        (lambda p: p['counters'].append(copy.deepcopy(p['counters'][0])), 'invalid_schema'),
        (lambda p: p.update(window_start=p['window_end']), 'invalid_window'),
        (lambda p: p.update(window_end='2026-10-15T00:00:00'), 'invalid_schema'),
        (lambda p: p.update(window_end=p['window_end'].replace('T', 'X')), 'invalid_schema'),
        (lambda p: p.update(window_end=p['window_end'].replace('+00:00', '+00:99')), 'invalid_schema'),
        (lambda p: p['histograms'].append({'name': 'raw', 'buckets': []}), 'unknown_histogram'),
    ],
)
def test_strict_rejection(change, reason):
    payload = summary()
    change(payload)
    with pytest.raises(FleetValidationError, match=reason):
        validate_summary(payload)


def test_window_age_duration_and_future_limits():
    now = datetime.now(timezone.utc)
    for start, end in [
        (now - timedelta(days=2), now),
        (now - timedelta(hours=2), now),
        (now, now + timedelta(minutes=10)),
    ]:
        payload = summary()
        payload.update(window_start=start.isoformat(), window_end=end.isoformat())
        with pytest.raises(FleetValidationError, match='invalid_window'):
            validate_summary(payload, now=now)


def test_clamp_then_increment_by_delta(client):
    payload = summary()
    payload['counters'][0]['count'] = 10_001
    child = fleet.EVENTS.labels('Device Connected', 'observed', 'ios', 'stable')
    before = child._value.get()
    response = client.post('/v1/telemetry/fleet', json=payload)
    assert response.status_code == 200
    assert response.json()['clamped'] is True
    assert child._value.get() - before == 10_000
    assert 'test-user-never-a-label' not in generate_latest().decode()
    assert '1.2.3' not in str(list(fleet.EVENTS.collect()))


def test_rejected_request_does_not_increment_events(client):
    payload = summary()
    payload['counters'].append({'event': 'not registered', 'outcome': 'observed', 'count': 1})
    child = fleet.EVENTS.labels('Device Connected', 'observed', 'ios', 'stable')
    before = child._value.get()
    rejected = fleet.REJECTED.labels('unknown_event')._value.get()
    response = client.post('/v1/telemetry/fleet', json=payload)
    assert response.status_code == 422
    assert fleet.REJECTED.labels('unknown_event')._value.get() == rejected + 1
    assert child._value.get() == before


def test_histogram_conservation_and_cumulative_deltas(client):
    payload = summary()
    payload['histograms'] = [histogram()]
    payload['counters'][0]['event'] = registry()['histograms'][payload['histograms'][0]['name']]['event']
    collector = fleet.FleetHistograms()
    h = payload['histograms'][0]
    for _ in range(2):
        collector.add(h['name'], 'ios', 'stable', h['buckets'])
    samples = [sample for family in collector.collect() for sample in family.samples]
    buckets = [sample for sample in samples if sample.name.endswith('_bucket_total')]
    assert [s.value for s in buckets] == [2 * b['count'] for b in h['buckets']]
    assert samples[-1].name.endswith('_count_total')
    assert samples[-1].value == h['buckets'][-1]['count'] * 2
    assert not any(s.name.endswith('_sum') for s in samples)
    assert client.post('/v1/telemetry/fleet', json=payload).status_code == 200
    for bad in ('decreasing', 'duplicate', 'edges', 'missing_event'):
        invalid = copy.deepcopy(payload)
        if bad == 'decreasing':
            invalid['histograms'][0]['buckets'][0]['count'] = 999
        elif bad == 'duplicate':
            invalid['histograms'].append(copy.deepcopy(h))
        elif bad == 'edges':
            invalid['histograms'][0]['buckets'][0]['le'] = 123
        else:
            invalid['counters'] = []
        assert client.post('/v1/telemetry/fleet', json=invalid).status_code == 422


def test_rate_limit_is_hard_twelve_per_uid_without_denial_amplification(client, monkeypatch):
    calls = []
    accepted = 0

    def reserve(uid, policy, maximum, window, **kwargs):
        nonlocal accepted
        calls.append((uid, policy, maximum, window))
        if accepted >= maximum:
            return False, 0, 100
        accepted += 1
        return True, maximum - accepted, 3600

    monkeypatch.setattr(route, 'reserve_rate_limit', reserve)
    for _ in range(12):
        assert client.post('/v1/telemetry/fleet', json=summary()).status_code == 200
    for _ in range(3):
        response = client.post('/v1/telemetry/fleet', content=b'not parsed')
        assert response.status_code == 429
        assert response.headers['retry-after'] == '100'
    assert accepted == 12
    assert set(calls) == {('test-user-never-a-label', 'telemetry:fleet', 12, 3600)}


def test_limiter_failure_is_closed(client, monkeypatch):
    def broken(*args, **kwargs):
        raise ConnectionError('never expose this')

    monkeypatch.setattr(route, 'reserve_rate_limit', broken)
    response = client.post('/v1/telemetry/fleet', json=summary())
    assert response.status_code == 503
    assert 'never expose' not in response.text


def test_unauthenticated_and_size_boundaries(client):
    app = FastAPI()
    app.include_router(route.router)
    with TestClient(app) as unauthenticated:
        assert unauthenticated.post('/v1/telemetry/fleet', json=summary()).status_code == 401
    for headers in ({}, {'content-length': '1'}):
        response = client.post('/v1/telemetry/fleet', content=b'x' * (MAX_BYTES + 1), headers=headers)
        assert response.status_code == 413
    assert (
        client.post('/v1/telemetry/fleet', json=summary(), headers={'content-encoding': 'Identity'}).status_code == 200
    )
    assert client.post('/v1/telemetry/fleet', content=b'{').status_code == 422
    assert client.post('/v1/telemetry/fleet', content=b'{}', headers={'content-encoding': 'gzip'}).status_code == 415


def test_fleet_auth_preserves_security_without_registration_or_recovery(monkeypatch):
    monkeypatch.setattr(endpoints, 'verify_token', lambda token: 'synthetic-local-user')
    hooks = {}
    for name in (
        'enforce_account_deletion_http_access',
        '_enforce_cutover_http_if_request',
        'validate_byok_request',
        'record_user_platform',
        'record_client_device',
        '_recover_locked_content_if_request',
    ):
        hooks[name] = Mock()
        monkeypatch.setattr(endpoints, name, hooks[name])
    request = Request({'type': 'http', 'path': '/v1/telemetry/fleet', 'headers': [], 'query_string': b''})
    assert endpoints.get_current_user_uid(authorization='Bearer local-token', request=request) == 'synthetic-local-user'
    for name in (
        'enforce_account_deletion_http_access',
        '_enforce_cutover_http_if_request',
        'validate_byok_request',
    ):
        hooks[name].assert_called_once()
    for name in ('record_user_platform', 'record_client_device', '_recover_locked_content_if_request'):
        hooks[name].assert_not_called()


def test_maximum_registered_summary_is_accepted(client):
    payload = summary()
    payload['counters'] = [
        {'event': event, 'outcome': outcome, 'count': 1}
        for event, outcomes in registry()['events'].items()
        for outcome in outcomes
    ]
    payload['histograms'] = [
        {'name': name, 'buckets': [{'le': edge, 'count': 1} for edge in spec['buckets']]}
        for name, spec in registry()['histograms'].items()
    ]
    assert len(json.dumps(payload)) < MAX_BYTES
    response = client.post('/v1/telemetry/fleet', json=payload)
    assert response.status_code == 200
    assert response.json()['clamped'] is False
