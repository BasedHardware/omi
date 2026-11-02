"""Actual read failures have closed outcomes and identity-free diagnostics."""

import hashlib
from types import SimpleNamespace

import pytest
from google.cloud.exceptions import NotFound

from utils.other import audio_raw_read_metrics as metrics, raw_audio_read as reader
from utils.other import storage


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
    handles = []

    def fresh_blob(path):
        blob = SimpleNamespace(metadata=None, download_as_bytes=lambda **kw: raw)

        def reload(**kwargs):
            blob.metadata = dict(metadata)

        blob.reload = reload
        handles.append(blob)
        return blob

    bucket = SimpleNamespace(blob=fresh_blob, handles=handles)
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


def test_hash_miss_is_a_terminal_outcome_but_absent_raw_is_not(capture, monkeypatch, caplog):
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
    before = metric_values()
    caplog.clear()
    assert reader.pcm_for_span(bucket, 'owner', 'conv', span, expected_sha256='bad') is None
    assert metric_values() == before
    assert not caplog.text


def metric_values():
    return {result: metrics.RAW_READ.labels(result=result)._value.get() for result in metrics.RESULTS}


@pytest.mark.parametrize(
    'metadata',
    [
        {},
        {'v2_start': '100', 'v2_samples': '160', 'v2_sample_rate': '16000'},
        {'v2_start': '100', 'v2_samples': '160', 'v2_sample_rate': '16000', 'pcm_sha256': 'hash'},
    ],
)
def test_normal_legacy_pcm_read_has_no_raw_outcome(monkeypatch, caplog, metadata):
    raw = b'\x01\x02' * 160
    bucket = SimpleNamespace(
        blob=lambda path: SimpleNamespace(
            metadata=dict(metadata), reload=lambda **kw: None, download_as_bytes=lambda **kw: raw
        )
    )
    monkeypatch.setattr(storage.audio_archive, 'admitted', lambda *args: True)
    monkeypatch.setattr(storage, '_get_storage_client', lambda: SimpleNamespace(bucket=lambda name: bucket))
    monkeypatch.setattr(reader, 'list_packs', lambda *args: [])
    before = metric_values()
    assert storage.download_and_decode_chunk_blob(bucket, 'chunks/owner/conv/100.bin', 'owner', 16000) == raw
    assert metric_values() == before
    assert not caplog.text


@pytest.mark.parametrize('through_span', [False, True])
def test_failure_codec_comes_from_the_read_handle(capture, monkeypatch, caplog, through_span):
    bucket, metadata, _ = capture
    metadata.update(codec='opus', sha256='bad')
    monkeypatch.setattr(
        reader, 'list_packs', lambda *args: [{'timestamp': 100, 'raw_end': 100.01, 'path': 'private-path'}]
    )
    before = metrics.RAW_READ.labels(result='checksum_mismatch')._value.get()
    with pytest.raises(metrics.ChecksumMismatch):
        if through_span:
            reader.pcm_for_span(
                bucket,
                'private-owner',
                'conv',
                {'start': 100, 'samples': 160, 'sample_rate': 16000},
                expected_sha256='hash',
            )
        else:
            reader.read_pack(bucket, 'private-path', 'private-owner')
    assert metrics.RAW_READ.labels(result='checksum_mismatch')._value.get() == before + 1
    assert 'result=checksum_mismatch codec=opus' in caplog.text
    assert 'private' not in caplog.text
    assert len(bucket.handles) == 1
    assert bucket.blob('private-path') is not bucket.handles[0]
    assert bucket.handles[-1].metadata is None


def test_explicit_missing_raw_pack_is_counted(monkeypatch, caplog):
    def missing(**kwargs):
        raise NotFound('private path')

    bucket = SimpleNamespace(blob=lambda path: SimpleNamespace(metadata=None, reload=missing))
    before = metrics.RAW_READ.labels(result='no_pack')._value.get()
    with pytest.raises(NotFound):
        reader.read_pack(bucket, 'private-path', 'private-owner')
    assert metrics.RAW_READ.labels(result='no_pack')._value.get() == before + 1
    assert 'result=no_pack codec=other' in caplog.text
    assert 'private' not in caplog.text


def test_unknown_labels_and_codec_are_closed(caplog):
    metrics.record('private reason', 'private codec')
    assert 'result=other codec=other' in caplog.text
    assert 'private' not in caplog.text


def test_chunk_decode_failure_does_not_log_object_or_exception(monkeypatch, caplog):
    bucket = SimpleNamespace(blob=lambda path: SimpleNamespace(download_as_bytes=lambda **kw: b'encoded'))
    monkeypatch.setattr(storage.audio_archive, 'admitted', lambda *args: False)

    def fail(*args, **kwargs):
        raise RuntimeError('private decoder detail')

    monkeypatch.setattr(storage, 'decode_opus_to_pcm', fail)
    assert storage.download_and_decode_chunk_blob(bucket, 'private-object.opus', 'private-owner', 16000) is None
    assert 'result=decode_error codec=opus' in caplog.text
    assert 'private' not in caplog.text
