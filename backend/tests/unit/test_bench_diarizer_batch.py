import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from scripts import bench_diarizer_batch as bench


def test_real_loopback_transport_uses_pcm_contract(httpserver, monkeypatch):
    pcm = b'\0\0' * 16000
    httpserver.expect_request('/v2/diarization', method='POST', data=pcm).respond_with_json(
        {
            'turns': [],
            'embedding_space': 'test',
            'version': 'test',
            'provenance': {'backend': 'pyannote'},
            'audio_seconds': 1,
            'inference_seconds': 0.01,
        }
    )
    monkeypatch.setenv('HOSTED_DIARIZATION_API_URL', httpserver.url_for('/').rstrip('/'))
    result = bench.request(pcm, 5)
    assert result['outcome'] == 'ok'
    assert result['inference_seconds'] == 0.01
    assert result['wall_seconds'] > 0


def test_shipping_client_preserves_server_timing_without_recording_vectors(monkeypatch):
    def post(url, **kwargs):
        assert url == 'http://replica:8000/v2/diarization'
        assert kwargs['content'] == b'\0\0' * 16000
        assert kwargs['headers'] == {'Content-Type': 'audio/pcm'}
        assert kwargs['timeout'].read <= 600
        return httpx.Response(
            200,
            request=httpx.Request('POST', url),
            json={
                'turns': [{'start': 0, 'end': 1, 'speaker': 'public-speaker'}],
                'embedding_space': 'test',
                'version': 'test',
                'provenance': {'backend': 'pyannote'},
                'centroids': {'public-speaker': {'embedding': [0.123456789], 'evidence_seconds': 1}},
                'audio_seconds': 1,
                'inference_seconds': 0.25,
            },
        )

    monkeypatch.setenv('HOSTED_DIARIZATION_API_URL', 'http://replica:8000')
    monkeypatch.setattr(httpx, 'post', post)
    result = bench.request(b'\0\0' * 16000, 600)
    assert result['inference_rtf'] == 0.25
    assert result['server_audio_seconds'] == 1
    assert result['speakers'] == 1
    assert all(value is None for value in result['stage_seconds'].values())
    assert 'public-speaker' not in json.dumps(result)
    assert '0.123456789' not in json.dumps(result)


def test_legacy_server_missing_timing_is_unknown(monkeypatch):
    monkeypatch.setattr(
        bench.HttpDiarizer, 'diarize', lambda *a, **k: SimpleNamespace(centroids={}, turns=[], provenance={})
    )
    result = bench.request(b'\0\0' * 16000, 600)
    assert result['inference_seconds'] is None
    assert result['inference_rtf'] is None


def test_timeout_receipt_does_not_include_error_body(monkeypatch):
    def fail(*args, **kwargs):
        raise httpx.ReadTimeout('do not log body')

    monkeypatch.setattr(bench.HttpDiarizer, 'diarize', fail)
    result = bench.request(b'\0\0', 1)
    assert result['outcome'] == 'failed'
    assert result['error'] == 'ReadTimeout'
    assert 'do not log body' not in json.dumps(result)


def test_two_requests_are_concurrent_and_throughput_is_wave_based(monkeypatch):
    calls = []

    async def to_thread(fn, pcm, timeout):
        calls.append(len(pcm))
        await asyncio.sleep(0.01)
        assert len(calls) == 2
        return {'outcome': 'ok', 'audio_seconds': 1}

    monkeypatch.setattr(asyncio, 'to_thread', to_thread)
    result = asyncio.run(bench.wave(b'\0\0', 2, 600))
    assert len(result['requests']) == 2
    assert result['completed_audio_hours_per_hour'] == 2 / result['wave_seconds']
    assert result['gpu_measurement'] == 'unavailable'


def test_dcgm_matches_target_node_and_discards_invalid_sentinels():
    body = '\n'.join(
        [
            'DCGM_FI_DEV_GPU_UTIL{Hostname="target",gpu="0"} 42',
            'DCGM_FI_DEV_GPU_UTIL{Hostname="other",gpu="0"} 99',
            'DCGM_FI_DEV_GPU_UTIL{Hostname="target",gpu="1"} 9223372036854775794',
        ]
    )
    assert bench.metric_values(body, 'DCGM_FI_DEV_GPU_UTIL', 'target') == [42]


def test_wrong_corpus_provenance_refused_before_network(tmp_path):
    (tmp_path / 'manifest.json').write_text(json.dumps({'source': 'user-recording'}))
    with pytest.raises(ValueError, match='provenance'):
        bench.load_corpus(tmp_path)


def test_gcs_non_synthetic_prefix_refused_before_adc(tmp_path):
    with pytest.raises(ValueError, match='synthetic'):
        bench.stage_download('gs://bucket/recordings/', tmp_path)


def test_matrix_stops_after_failure_without_retry(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(bench, 'load_corpus', lambda _: {'sha256': 'fixture'})
    monkeypatch.setattr(bench, 'MINUTES', (5, 15))
    (tmp_path / 'corpus.pcm').write_bytes(b'\0\0')
    monkeypatch.setattr(
        httpx,
        'get',
        lambda url, **k: httpx.Response(
            200, request=httpx.Request('GET', url), text='omi_diarization_v2_queue_depth 0\n'
        ),
    )
    calls = []

    async def fail(*args):
        calls.append(args)
        return {'requests': [{'outcome': 'failed'}]}

    monkeypatch.setattr(bench, 'wave', fail)
    args = SimpleNamespace(
        corpus=tmp_path,
        base='http://replica',
        target_image='sha',
        client_image='sha',
        dcgm_node=None,
        dcgm_url=None,
        timeout=600,
        repeats=3,
    )
    with pytest.raises(RuntimeError, match='matrix aborted'):
        asyncio.run(bench.run(args))
    assert len(calls) == 1
