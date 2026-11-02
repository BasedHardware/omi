"""Actual read failures have closed outcomes and identity-free diagnostics."""

import hashlib
from types import SimpleNamespace

import pytest

from utils.other import audio_raw_read_metrics as metrics, raw_audio_read as reader


@pytest.fixture
def capture(monkeypatch):
    raw = b'\x01\x02' * 160
    metadata = {
        'sample_rate': '16000',
        'channels': '1',
        'format': 'pcm16le',
        'codec': 'pcm16',
        'capture_start': '100',
        'capture_end': '100.01',
        'sha256': hashlib.sha256(raw).hexdigest(),
    }
    blob = SimpleNamespace(metadata=metadata, reload=lambda **kw: None, download_as_bytes=lambda **kw: raw)
    bucket = SimpleNamespace(blob=lambda path: blob)
    return bucket, metadata, raw


@pytest.mark.parametrize('result', sorted(metrics.RESULTS))
def test_counter_has_only_closed_result_labels(result):
    before = metrics.RAW_READ.labels(result=result)._value.get()
    metrics.record(result)
    assert metrics.RAW_READ.labels(result=result)._value.get() == before + 1
    assert metrics.RAW_READ._labelnames == ('result',)


@pytest.mark.parametrize('failure', ['checksum_mismatch', 'coverage_mismatch', 'decode_error', 'decrypt_error'])
def test_read_failures_are_counted_without_path_or_error_text(capture, monkeypatch, caplog, failure):
    bucket, metadata, _ = capture
    if failure == 'checksum_mismatch':
        metadata['sha256'] = 'bad'
    elif failure == 'coverage_mismatch':
        metadata['capture_end'] = '101'
    else:

        def fail(*args, **kwargs):
            raise RuntimeError('private exception detail')

        if failure == 'decrypt_error':
            metadata['encrypted'] = 'true'
            monkeypatch.setattr(reader.encryption, 'decrypt_audio_file', fail)
        else:
            monkeypatch.setattr(reader, 'decode_capture', fail)
    before = metrics.RAW_READ.labels(result=failure)._value.get()
    with pytest.raises(ValueError):
        reader.read_pack(bucket, 'private-object-name', 'private-owner')
    assert metrics.RAW_READ.labels(result=failure)._value.get() == before + 1
    assert f'result={failure} codec=pcm16' in caplog.text
    assert 'private' not in caplog.text


def test_hash_miss_and_no_pack_are_terminal_outcomes(capture, monkeypatch):
    bucket, _, raw = capture
    pack = {'timestamp': 100, 'raw_end': 100.01, 'path': 'object'}
    monkeypatch.setattr(reader, 'list_packs', lambda *args: [pack])
    span = {'start': 100, 'samples': 160, 'sample_rate': 16000}
    before = metrics.RAW_READ.labels(result='identity_mismatch')._value.get()
    assert reader.pcm_for_span(bucket, 'owner', 'conv', span, expected_sha256='bad') is None
    assert metrics.RAW_READ.labels(result='identity_mismatch')._value.get() == before + 1
    before = metrics.RAW_READ.labels(result='ok')._value.get()
    assert reader.pcm_for_span(bucket, 'owner', 'conv', span, expected_sha256=hashlib.sha256(raw).hexdigest()) == raw
    assert metrics.RAW_READ.labels(result='ok')._value.get() == before + 1
    monkeypatch.setattr(reader, 'list_packs', lambda *args: [])
    before = metrics.RAW_READ.labels(result='no_pack')._value.get()
    assert reader.pcm_for_span(bucket, 'owner', 'conv', span, expected_sha256='bad') is None
    assert metrics.RAW_READ.labels(result='no_pack')._value.get() == before + 1


def test_unknown_labels_and_codec_are_closed(caplog):
    metrics.record('private reason', 'private codec')
    assert 'result=other codec=other' in caplog.text
    assert 'private' not in caplog.text


def test_chunk_decode_failure_does_not_log_object_or_exception(monkeypatch, caplog):
    from utils.other import storage

    bucket = SimpleNamespace(blob=lambda path: SimpleNamespace(download_as_bytes=lambda **kw: b'encoded'))
    monkeypatch.setattr(storage.audio_archive, 'admitted', lambda *args: False)

    def fail(*args, **kwargs):
        raise RuntimeError('private decoder detail')

    monkeypatch.setattr(storage, 'decode_opus_to_pcm', fail)
    assert storage.download_and_decode_chunk_blob(bucket, 'private-object.opus', 'private-owner', 16000) is None
    assert 'result=decode_error codec=opus' in caplog.text
    assert 'private' not in caplog.text
