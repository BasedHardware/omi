"""Admission must preserve legacy speakers under pressure and infrastructure failure."""

import io
import threading
import wave
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import fakeredis
import pytest

from utils.conversations import final_pass_sync as sync


def wav(seconds=1):
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b'\x00\x00' * 16000 * seconds)
    return output.getvalue()


def test_shared_budget_is_atomic_across_workers_and_counts_retries(monkeypatch):
    server = fakeredis.FakeServer()
    clients = [fakeredis.FakeRedis(server=server) for _ in range(8)]
    monkeypatch.setenv('TRANSCRIPTION_SYNC_FINAL_PASS_HOURLY_REQUESTS', '3')
    monkeypatch.setattr(sync, 'redis_client', clients[0])
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: sync._reserve_budget(1), range(32)))
    assert sum(results) == 3
    assert not sync._reserve_budget(1)
    assert 0 < clients[0].ttl(clients[0].keys()[0]) <= 7200


def test_audio_budget_charges_before_work_and_does_not_refund(monkeypatch):
    client = fakeredis.FakeRedis()
    monkeypatch.setattr(sync, 'redis_client', client)
    monkeypatch.setenv('TRANSCRIPTION_SYNC_FINAL_PASS_HOURLY_AUDIO_HOURS', str(2 / 3600))
    assert sync._reserve_budget(1)
    assert sync._reserve_budget(1)
    assert not sync._reserve_budget(0.001)


@pytest.mark.parametrize('value', ['0', '-1', 'nan', 'inf', 'invalid'])
def test_invalid_budget_cannot_remove_bound(monkeypatch, value):
    monkeypatch.setenv('TRANSCRIPTION_SYNC_FINAL_PASS_HOURLY_AUDIO_HOURS', value)
    assert not sync._reserve_budget(1)


def test_redis_failure_skips_before_embeddings_or_gpu(monkeypatch):
    def unavailable(*args):
        raise ConnectionError('synthetic')

    monkeypatch.setattr(sync, 'redis_client', SimpleNamespace(eval=unavailable))
    monkeypatch.setattr(sync, 'speaker_embedding_configured', lambda: pytest.fail('embedding work admitted'))
    original = [object()]
    assert sync.run_sync_final_pass('synthetic', wav(), [], original, {}, scope='job', owner_reserved=False) == (
        None,
        {'outcome': 'skipped_budget'},
    )
    assert len(original) == 1


def test_concurrent_call_skips_without_waiting_and_exception_releases_slot(monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        raise RuntimeError('synthetic')

    monkeypatch.setattr(sync, '_run_sync_final_pass', blocked)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(sync.run_sync_final_pass, 'a', b'', [], [], {}, scope='job', owner_reserved=False)
        assert entered.wait(5)
        try:
            assert sync.run_sync_final_pass('b', b'', [], [], {}, scope='job', owner_reserved=False)[1] == {
                'outcome': 'skipped_budget'
            }
        finally:
            release.set()
        with pytest.raises(RuntimeError):
            future.result()
    monkeypatch.setattr(sync, '_run_sync_final_pass', lambda *a, **kw: (None, {'outcome': 'synthetic'}))
    assert (
        sync.run_sync_final_pass('c', b'', [], [], {}, scope='job', owner_reserved=False)[1]['outcome'] == 'synthetic'
    )
