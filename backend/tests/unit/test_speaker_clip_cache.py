import asyncio
import io
import wave
from types import SimpleNamespace

import numpy as np

from utils.speakers import embedding_cache as cache
from utils.stt import speaker_embedding as client


def audio():
    output = io.BytesIO()
    with wave.open(output, 'wb') as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(b'\0\0' * 16000)
    return output.getvalue()


def test_hash_model_isolation_copy_ttl_capacity_and_failures(monkeypatch):
    monkeypatch.setattr(cache, '_entries', cache.OrderedDict())
    clock = [1.0]
    monkeypatch.setattr(cache.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(cache, 'MAX_ENTRIES', 2)
    key = cache.key(b'clip', 'model-a')
    assert key != cache.key(b'clip', 'model-b')
    assert key != cache.key(b'other', 'model-a')
    cache.put(key, np.array([[1.0, 2.0]]))
    cache.get(key)[0, 0] = 999
    assert cache.get(key)[0, 0] == 1
    cache.put('bad', np.array([[float('nan')]]))
    assert cache.get('bad') is None
    cache.put('second', np.ones((1, 2)))
    cache.put('third', np.ones((1, 2)))
    assert cache.get(key) is None
    clock[0] += cache.TTL_SECONDS + 1
    assert cache.get('second') is None and cache.get('third') is None


def test_sync_file_bytes_and_async_pass_reuse_embedding(monkeypatch, tmp_path):
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', 'shadow')
    monkeypatch.setenv('HOSTED_SPEAKER_EMBEDDING_API_URL', 'https://embedding.invalid')
    monkeypatch.setattr(cache, '_entries', cache.OrderedDict())
    calls = []
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: [1.0, 0.0])
    monkeypatch.setattr(client.httpx, 'post', lambda *a, **k: calls.append(1) or response)
    path = tmp_path / 'clip.wav'
    path.write_bytes(audio())
    first = client.extract_embedding(str(path))
    assert np.array_equal(first, client.extract_embedding_from_bytes(audio()))
    assert np.array_equal(first, asyncio.run(client.async_extract_embedding_from_bytes(audio())))
    assert np.array_equal(first, asyncio.run(client.async_extract_embedding(str(path))))
    assert calls == [1]
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', 'off')
    client.extract_embedding_from_bytes(audio())
    assert calls == [1, 1]
