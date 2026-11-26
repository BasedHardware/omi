"""Pipeline lab speaker peer (``speakers/peer.py``): cassette keys, replay hits and misses, the multipart upload
parse, and record-local through a fake local worker. Loopback HTTP only; no model, no torch, no network."""

import json
import struct

import httpx
import pytest

from testing.pipeline_lab.speakers import peer as peer_module
from testing.pipeline_lab.speakers.peer import (
    CassetteStore,
    SpeakerPeer,
    _multipart_file,
    cassette_key,
    model_pins,
)

PCM = struct.pack('<8h', 0, 100, -100, 200, -200, 300, -300, 0) * 400  # synthetic samples, 0.2 s


def _wav(pcm: bytes) -> bytes:
    from testing.pipeline_lab.cassette.adapters import pcm16_to_wav

    return pcm16_to_wav(pcm)


class FakeLocal:
    """Stands in for the local-models worker: answers every request and counts them."""

    def __init__(self, body):
        self.body = body
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        return {'ok': True, 'body': self.body}

    def close(self):
        pass


@pytest.fixture()
def store(tmp_path):
    (tmp_path / 'private').mkdir(mode=0o700)
    return CassetteStore(tmp_path / 'private', public_root=tmp_path / 'public')


def _peer(tmp_path, store, mode='replay', local=None):
    work = tmp_path / 'work'
    work.mkdir(mode=0o700, exist_ok=True)
    return SpeakerPeer(mode, store=store, workdir=work, local=local).start()


def _put(store, route, params, body, answer, pins):
    key = cassette_key(route, params, body, pins)
    store.write_public = True
    store.put(route, key, {'route': route, 'params': params, 'status': 200, 'body': answer})
    store.write_public = False
    return key


def test_model_pins_are_read_from_source_without_torch():
    pins = model_pins()
    assert set(pins) == {'diarization', 'embedding'}
    assert all(len(value) == 40 for value in pins.values())


def test_cassette_key_changes_with_audio_params_and_pins():
    pins = {'diarization': 'a' * 40, 'embedding': 'b' * 40}
    base = cassette_key('/v2/diarization', {'content_type': 'audio/pcm'}, PCM, pins)
    assert base == cassette_key('/v2/diarization', {'content_type': 'audio/pcm'}, PCM, pins)
    assert base != cassette_key('/v2/diarization', {'content_type': 'audio/pcm'}, PCM + b'\0\0', pins)
    assert base != cassette_key('/v2/diarization', {'content_type': 'audio/pcm', 'max_speakers': 2}, PCM, pins)
    assert base != cassette_key(
        '/v2/diarization', {'content_type': 'audio/pcm'}, PCM, {**pins, 'diarization': 'c' * 40}
    )
    assert base != cassette_key('/v2/embedding', {'content_type': 'audio/pcm'}, PCM, pins)


def test_multipart_upload_yields_the_file_part_bytes():
    wav = _wav(PCM)
    request = httpx.Request('POST', 'http://127.0.0.1/v2/embedding', files={'file': ('voice.wav', wav, 'audio/wav')})
    body = request.read()
    assert _multipart_file(request.headers['content-type'], body) == wav
    with pytest.raises(ValueError):
        other = httpx.Request('POST', 'http://127.0.0.1/', files={'other': ('x.wav', wav, 'audio/wav')})
        _multipart_file(other.headers['content-type'], other.read())


def test_replay_serves_a_hit_and_refuses_a_miss_with_409(tmp_path, store):
    peer = _peer(tmp_path, store)
    try:
        answer = {'turns': [{'start': 0.0, 'end': 0.2, 'speaker': 'SPEAKER_00'}], 'provenance': {'backend': 'pyannote'}}
        _put(store, '/v2/diarization', {'content_type': 'audio/pcm'}, PCM, answer, peer.pins)
        hit = httpx.post(peer.url + '/v2/diarization', content=PCM, headers={'Content-Type': 'audio/pcm'})
        assert hit.status_code == 200 and hit.json() == answer
        miss = httpx.post(peer.url + '/v2/diarization', content=PCM[:-2], headers={'Content-Type': 'audio/pcm'})
        assert miss.status_code == 409 and 'record-local' in miss.json()['detail']
        assert peer.stats.summary() == {'/v2/diarization': {'hit': 1, 'miss': 1}}
    finally:
        peer.stop()


def test_replay_embedding_is_keyed_on_the_uploaded_file_bytes(tmp_path, store):
    peer = _peer(tmp_path, store)
    try:
        wav = _wav(PCM)
        _put(store, '/v2/embedding', {}, wav, {'embedding': [0.5] * 4}, peer.pins)
        reply = httpx.post(peer.url + '/v2/embedding', files={'file': ('any-name.wav', wav, 'audio/wav')})
        assert reply.status_code == 200 and reply.json() == {'embedding': [0.5] * 4}
        assert httpx.post(peer.url + '/v2/other', content=b'').status_code == 404
    finally:
        peer.stop()


def test_record_local_runs_the_worker_on_a_miss_files_a_local_cassette_and_then_hits(tmp_path, store):
    local = FakeLocal({'embedding': [0.25] * 4})
    peer = _peer(tmp_path, store, mode='record-local', local=local)
    try:
        wav = _wav(PCM)
        first = httpx.post(peer.url + '/v2/embedding', files={'file': ('v.wav', wav, 'audio/wav')})
        second = httpx.post(peer.url + '/v2/embedding', files={'file': ('v.wav', wav, 'audio/wav')})
        assert first.json() == second.json() == {'embedding': [0.25] * 4}
        assert len(local.requests) == 1 and local.requests[0]['op'] == 'embedding'
        assert peer.stats.summary() == {'/v2/embedding': {'recorded': 1, 'hit': 1}}
        files = list((tmp_path / 'private').rglob('*.json'))
        assert len(files) == 1 and not (tmp_path / 'public').exists()
        entry = json.loads(files[0].read_text())
        assert entry['source'] == 'local' and entry['device'] == 'cpu-fp32' and entry['status'] == 200
        assert not list((tmp_path / 'work').glob('req-*'))  # the request audio is removed after the call
    finally:
        peer.stop()


def test_peer_env_points_both_product_urls_at_the_peer(tmp_path, store):
    peer = _peer(tmp_path, store)
    try:
        assert peer.env() == {'HOSTED_DIARIZATION_API_URL': peer.url, 'HOSTED_SPEAKER_EMBEDDING_API_URL': peer.url}
        assert peer.url.startswith('http://127.0.0.1:')
    finally:
        peer.stop()
    with pytest.raises(ValueError):
        SpeakerPeer('record-vendor', store=store, workdir=tmp_path)
    assert peer_module.MODES == ('replay', 'record-local')
