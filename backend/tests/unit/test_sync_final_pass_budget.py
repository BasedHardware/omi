"""Admission must preserve legacy speakers under pressure and infrastructure failure."""

import io
import socket
import time
import threading
import wave
from concurrent.futures import ThreadPoolExecutor

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
    inspector = fakeredis.FakeRedis(server=server)
    monkeypatch.setenv('TRANSCRIPTION_SYNC_FINAL_PASS_HOURLY_REQUESTS', '3')
    monkeypatch.setattr(sync, 'create_bounded_redis_client', lambda timeout: fakeredis.FakeRedis(server=server))
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: sync._reserve_budget(1), range(32)))
    assert sum(results) == 3
    assert not sync._reserve_budget(1)
    assert 0 < inspector.ttl(inspector.keys()[0]) <= 7200


def test_audio_budget_charges_before_work_and_does_not_refund(monkeypatch):
    server = fakeredis.FakeServer()
    monkeypatch.setattr(sync, 'create_bounded_redis_client', lambda timeout: fakeredis.FakeRedis(server=server))
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

    monkeypatch.setattr(sync, 'create_bounded_redis_client', unavailable)
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


def test_stalled_redis_socket_returns_legacy_and_releases_slot(monkeypatch):
    """A peer accepts AUTH/EVAL but never replies; exercise real Redis socket I/O."""
    accepted, release = threading.Event(), threading.Event()
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(1)
    listener.settimeout(3)
    port = listener.getsockname()[1]

    def silent_peer():
        with listener:
            connection, _ = listener.accept()
            with connection:
                accepted.set()
                release.wait(3)

    # This test hosts its own fake Redis peer and must exercise the real
    # socket I/O against it, so opt out of the unit-session Redis block.
    monkeypatch.setenv('OMI_HERMETIC_ALLOW_FAKE_REDIS', '1')
    monkeypatch.setenv('REDIS_DB_HOST', '127.0.0.1')
    monkeypatch.setenv('REDIS_DB_PORT', str(port))
    monkeypatch.delenv('REDIS_DB_PASSWORD', raising=False)
    monkeypatch.setattr(sync, 'speaker_embedding_configured', lambda: pytest.fail('embedding work admitted'))
    peer = threading.Thread(target=silent_peer)
    peer.start()
    try:
        started = time.monotonic()
        assert sync.run_sync_final_pass('synthetic', wav(), [], [], {}, scope='job', owner_reserved=False) == (
            None,
            {'outcome': 'skipped_budget'},
        )
        assert accepted.is_set()
        assert time.monotonic() - started < 2
        # A timed-out reservation cannot strand the one local slot.
        monkeypatch.setattr(sync, '_run_sync_final_pass', lambda *a, **kw: (None, {'outcome': 'synthetic'}))
        assert (
            sync.run_sync_final_pass('next', b'', [], [], {}, scope='job', owner_reserved=False)[1]['outcome']
            == 'synthetic'
        )
    finally:
        release.set()
        peer.join(3)


def test_sync_final_pass_exception_log_contains_class_without_message(caplog):
    with caplog.at_level('WARNING', logger=sync.__name__):
        assert sync.run_sync_final_pass(
            'synthetic', b'secret malformed audio', [], [], {}, scope='synthetic', owner_reserved=False
        ) == (None, {'outcome': 'failed:sync_audio'})
    matching = [record.getMessage() for record in caplog.records if 'exception_type=' in record.getMessage()]
    assert len(matching) == 1 and 'exception_type=' in matching[0]
    assert 'secret malformed audio' not in matching[0] and 'synthetic' not in matching[0]
