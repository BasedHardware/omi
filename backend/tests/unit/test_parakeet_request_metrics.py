"""Parakeet request time is attributed to the caller that bought it (cost lever G1)."""

import asyncio
import os
import re
import wave
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from prometheus_client import REGISTRY

os.environ.setdefault('DEEPGRAM_API_KEY', 'x')
os.environ.setdefault('HOSTED_PARAKEET_API_URL', 'http://fake-parakeet:8080')

import utils.stt.pre_recorded as pr  # noqa: E402
from utils.observability.sync_phases import current_sync_lane, sync_attempt  # noqa: E402
from utils.stt.parakeet_request_metrics import (  # noqa: E402
    current_parakeet_caller,
    observe_parakeet_request,
    parakeet_caller,
)

BACKEND = Path(__file__).resolve().parents[2]


def _count(caller: str, route: str) -> float:
    value = REGISTRY.get_sample_value('omi_parakeet_request_seconds_count', {'caller': caller, 'route': route})
    return value or 0.0


def _wav() -> bytes:
    buf = BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b'\x00\x01' * 16000)
    return buf.getvalue()


def _response(status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {'text': 'hi', 'segments': [{'text': 'hi', 'start': 0.0, 'end': 1.0, 'speaker': '0'}]}
    return resp


def _patched_client(*responses):
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.post.side_effect = list(responses)
    return client


def test_caller_resolution_explicit_then_sync_lane_then_other():
    assert current_parakeet_caller() == 'other'
    with parakeet_caller('shadow'):
        assert current_parakeet_caller() == 'shadow'
    with parakeet_caller('not-a-caller'):
        assert current_parakeet_caller() == 'other'
    assert current_sync_lane() is None

    seen = {}

    @sync_attempt
    async def attempt(sync_lane: str):
        seen['lane'] = current_parakeet_caller()
        with parakeet_caller('batch_recovery'):
            seen['explicit'] = current_parakeet_caller()

    asyncio.run(attempt(sync_lane='backfill'))
    assert seen == {'lane': 'sync_backfill', 'explicit': 'batch_recovery'}
    asyncio.run(attempt(sync_lane='fresh'))
    assert seen['lane'] == 'sync_fresh'
    asyncio.run(attempt(sync_lane='bogus'))
    assert seen['lane'] == 'sync_unknown'


def test_failed_request_is_still_observed():
    before = _count('app_proxy', 'v2')
    with pytest.raises(httpx.ConnectError):
        with observe_parakeet_request('v2', caller='app_proxy'):
            raise httpx.ConnectError('down')
    assert _count('app_proxy', 'v2') == before + 1


def test_prerecorded_v2_request_is_labelled_with_the_context_caller():
    client = _patched_client(_response())
    before = _count('shadow', 'v2')
    with patch('httpx.Client', return_value=client), parakeet_caller('shadow'):
        pr.parakeet_prerecorded_from_bytes(_wav(), diarize=True)
    assert client.post.call_args.args[0].endswith('/v2/transcribe')
    assert _count('shadow', 'v2') == before + 1


def test_prerecorded_v1_fallback_after_404_counts_both_routes():
    client = _patched_client(_response(404), _response())
    before_v2, before_v1 = _count('batch_recovery', 'v2'), _count('batch_recovery', 'v1')
    with patch('httpx.Client', return_value=client), parakeet_caller('batch_recovery'):
        pr.parakeet_prerecorded_from_bytes(_wav(), diarize=True)
    assert _count('batch_recovery', 'v2') == before_v2 + 1
    assert _count('batch_recovery', 'v1') == before_v1 + 1


def test_prerecorded_inside_sync_attempt_is_labelled_by_lane():
    client = _patched_client(_response())
    before = _count('sync_backfill', 'v2')

    @sync_attempt
    async def attempt(sync_lane: str):
        pr.parakeet_prerecorded_from_bytes(_wav(), diarize=True)

    with patch('httpx.Client', return_value=client):
        asyncio.run(attempt(sync_lane='backfill'))
    assert _count('sync_backfill', 'v2') == before + 1


@pytest.mark.parametrize('config_name', ['cloud_run_gmp_sidecar.yaml', 'cloud_run_gmp_sync.yaml'])
def test_metric_survives_both_cloud_run_scrape_keep_rules(config_name):
    config = (BACKEND / 'deploy' / config_name).read_text(encoding='utf-8')
    keep = re.search(r'action: keep.*?regex: (\S+)', config, re.S).group(1).strip("'")
    for suffix in ('_bucket', '_sum', '_count'):
        assert re.fullmatch(keep, 'omi_parakeet_request_seconds' + suffix), (config_name, keep)
