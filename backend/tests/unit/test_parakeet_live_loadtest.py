"""Safety and measurement contracts for the direct dev capacity probe."""

import asyncio
import io
from types import SimpleNamespace

import httpx
import wave

import pytest

from scripts.parakeet_live_loadtest import audio, fixture_pcm, histogram, metrics, validate_url


@pytest.mark.parametrize(
    'url',
    [
        'https://api.omi.me',
        'http://parakeet.omi.me:8080',
        'http://127.0.0.1',
        'http://127.0.0.1:8080/v1/transcribe',
        'http://user:pass@127.0.0.1:8080',
        'http://127.0.0.1:8080?url=prod',
    ],
)
def test_capacity_probe_refuses_non_port_forward_targets(url):
    with pytest.raises(ValueError):
        validate_url(url)


def test_capacity_probe_checks_public_fixture_hashes_and_emits_pcm16_contexts():
    with wave.open(io.BytesIO(audio(fixture_pcm(), 24))) as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 16000)
        assert wav.getnframes() == 24 * 16000


def test_lane_histograms_use_step_deltas_and_preserve_lane_isolation():
    before = metrics('''# TYPE wait histogram
wait_bucket{lane="live",le="1"} 10
wait_bucket{lane="live",le="2"} 10
wait_bucket{lane="live",le="+Inf"} 10
wait_count{lane="live"} 10
wait_sum{lane="live"} 5
''')
    after = metrics('''# TYPE wait histogram
wait_bucket{lane="live",le="1"} 11
wait_bucket{lane="live",le="2"} 12
wait_bucket{lane="live",le="+Inf"} 12
wait_count{lane="live"} 12
wait_sum{lane="live"} 7
wait_bucket{lane="backfill",le="1"} 9999
wait_count{lane="backfill"} 9999
wait_sum{lane="backfill"} 9999
''')
    summary = histogram(before, after, 'wait', {'lane': 'live'})
    assert summary == {'count': 2, 'mean': 1, 'p50': 1, 'p95': pytest.approx(1.9), 'p99': pytest.approx(1.98)}


@pytest.mark.asyncio
async def test_live_probe_cancels_entire_post_at_wall_deadline(monkeypatch):
    from scripts import parakeet_live_loadtest as probe

    monkeypatch.setattr(probe, 'LIVE_POST_TIMEOUT_SECONDS', 0.02)
    cancelled = []

    async def handle(request):
        if request.method == 'POST':
            if request.headers.get('X-Omi-STT-Surface') == 'live-window':
                try:
                    await asyncio.sleep(0.1)
                except asyncio.CancelledError:
                    cancelled.append(True)
                    raise
            return httpx.Response(200, json={'text': 'synthetic'})
        if request.url.path == '/batch/metrics':
            return httpx.Response(200, json={'live_pending_requests': 0, 'live_oldest_pending_seconds': 0})
        return httpx.Response(200, text='')

    args = SimpleNamespace(
        url='http://127.0.0.1:28180',
        seconds=0.05,
        pace=6,
        batch_floor_rps=1,
        synchronized=True,
        live_context_seconds=24,
        diarize_backfill=True,
        keepalive_connections=0,
    )
    payloads = {duration: b'synthetic' for duration in (6, 12, 18, 24, 30, 60, 120, 240)}
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        receipt = await probe.step(client, args, 1, payloads)
    assert cancelled == [True]
    assert receipt['live']['statuses'] == {'transport_error': 1}
    assert receipt['backfill']['statuses'] == {'200': 1}
