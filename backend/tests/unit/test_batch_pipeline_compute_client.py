"""GPU-safe RPC composition: bounded receipts, OIDC and no user/audio payloads."""

import io
import json
from unittest.mock import Mock

import pytest

from utils.batch_pipeline.compute_client import ComputeClient
from utils.batch_pipeline.contracts import LeasedWork
from tests.unit.test_batch_pipeline_scheduler import item


def lease():
    return LeasedWork(item('segment', owner='synthetic'), 'lease-token', 1, 100)


def test_oidc_client_sends_only_fenced_ids_and_reuses_short_lived_cached_token():
    token = Mock(return_value='synthetic-service-token')
    seen = []

    def send(request, timeout):
        seen.append((request, timeout))
        return io.BytesIO(json.dumps({'allowed': ['segment'], 'retry_after': {}}).encode())

    client = ComputeClient('https://synthetic.invalid', 'service-audience', 'dev', token=token, send=send)
    assert client([lease()])['allowed'] == ['segment']
    assert client([lease()])['allowed'] == ['segment']
    token.assert_called_once()
    request, timeout = seen[0]
    assert timeout == 5 and request.full_url.endswith('/v2/batch-pipeline/authorize-compute')
    assert request.get_header('Authorization') == 'Bearer synthetic-service-token'
    assert json.loads(request.data) == {'stage': 'dev', 'leases': [{'segment_id': 'segment', 'token': 'lease-token'}]}
    assert b'synthetic/segment' not in request.data and b'owner_id' not in request.data


@pytest.mark.parametrize(
    'body',
    [
        {'allowed': ['foreign']},
        {'allowed': 'segment'},
        {'allowed': [], 'retry_after': {'segment': float('nan')}},
        {'allowed': [], 'retry_after': {'segment': -1}},
        {'allowed': [], 'retry_after': {'foreign': 30}},
        {'allowed': [], 'held_reason': {'foreign': 'allowance_exhausted'}},
        {'allowed': [], 'held_reason': {'segment': ''}},
        {'allowed': [], 'held_reason': {'segment': 'unbounded ' * 13}},
        {'allowed': [], 'held_reason': {'segment': 60}},
    ],
)
def test_invalid_authorization_receipt_never_permits_compute(body):
    client = ComputeClient(
        'https://synthetic.invalid',
        'audience',
        'dev',
        token=lambda: 'synthetic',
        send=lambda *args, **kwargs: io.BytesIO(json.dumps(body).encode()),
    )
    with pytest.raises(ValueError):
        client([lease()])


def test_hold_reason_receipt_round_trips_for_the_durable_decision():
    body = {'allowed': [], 'retry_after': {'segment': 60}, 'held_reason': {'segment': 'allowance_exhausted'}}
    client = ComputeClient(
        'https://synthetic.invalid',
        'audience',
        'dev',
        token=lambda: 'synthetic',
        send=lambda *args, **kwargs: io.BytesIO(json.dumps(body).encode()),
    )
    assert client([lease()])['held_reason'] == {'segment': 'allowance_exhausted'}


@pytest.mark.parametrize(
    'url,audience,stage',
    [
        ('', 'aud', 'dev'),
        ('http://example.invalid', 'aud', 'dev'),
        ('https://host.invalid?token=bad', 'aud', 'dev'),
        ('https://user@host.invalid', 'aud', 'dev'),
        ('https://host.invalid', '', 'dev'),
        ('https://host.invalid', 'aud', 'local'),
    ],
)
def test_missing_or_unsafe_configuration_refuses_before_any_network(url, audience, stage):
    with pytest.raises(ValueError):
        ComputeClient(url, audience, stage)
