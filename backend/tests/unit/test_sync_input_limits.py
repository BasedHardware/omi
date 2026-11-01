import io
import struct

from fastapi import HTTPException, UploadFile
import pytest

from utils.sync import input_limits as limits


def uploaded(codec='pcm16_16000', *, data=b'\0' * 320, name=None):
    return UploadFile(
        filename=name or f'audio_phonemic_{codec}_1_fs160_1710000000.bin',
        file=io.BytesIO(struct.pack('<I', len(data)) + data),
    )


def test_admission_preserves_stream_position_and_accepts_exact_bounds(monkeypatch):
    file = uploaded()
    monkeypatch.setattr(limits, 'MAX_BACKFILL_RAW_BYTES', 324)
    monkeypatch.setattr(limits, 'MAX_BACKFILL_AUDIO_BYTES', 320)
    limits.validate_backfill_uploads([file])
    assert file.file.tell() == 0
    assert len(file.file.read()) == 324


@pytest.mark.parametrize(
    'bound,value',
    [
        ('MAX_BACKFILL_FILES', 1),
        ('MAX_BACKFILL_RAW_BYTES', 647),
        ('MAX_BACKFILL_AUDIO_BYTES', 639),
        ('MAX_BACKFILL_FRAMES', 1),
        ('MAX_BACKFILL_SECONDS', 0.019),
    ],
)
def test_batch_caps_accumulate_across_files_before_acknowledgment(monkeypatch, bound, value):
    monkeypatch.setattr(limits, bound, value)
    files = [uploaded(), uploaded()]
    with pytest.raises(HTTPException) as error:
        limits.validate_backfill_uploads(files)
    assert error.value.status_code == 413
    assert all(file.file.tell() == 0 for file in files)


def test_pcm8_expansion_includes_resampling_and_rounds_up(monkeypatch):
    monkeypatch.setattr(limits, 'MAX_BACKFILL_AUDIO_BYTES', 1)
    with pytest.raises(HTTPException) as error:
        limits.validate_backfill_uploads([uploaded('pcm8_24000', data=b'\0')])
    assert error.value.status_code == 413


def test_compressed_frames_are_bounded_by_maximum_decoded_output(monkeypatch):
    monkeypatch.setattr(limits, 'MAX_BACKFILL_AUDIO_BYTES', 319)
    with pytest.raises(HTTPException):
        limits.validate_backfill_uploads([uploaded('opus_16000', data=b'\0')])


@pytest.mark.parametrize(
    'filename',
    [
        'audio_omi_opus_16000_1_fs999999999_1710000000.bin',
        'audio_phonemic_pcm16_1_1_fs160_1710000000.bin',
    ],
)
def test_untrusted_codec_metadata_cannot_allocate_unbounded_buffers(filename):
    with pytest.raises(HTTPException):
        limits.validate_backfill_uploads([uploaded(name=filename)])


def test_staged_attempt_revalidates_the_actual_bytes(tmp_path, monkeypatch):
    path = tmp_path / 'audio_phonemic_pcm16_16000_1_fs160_1710000000.bin'
    path.write_bytes(uploaded().file.read())
    limits.validate_backfill_paths([str(path)])
    monkeypatch.setattr(limits, 'MAX_BACKFILL_AUDIO_BYTES', 319)
    with pytest.raises(limits.BackfillInputLimitExceeded):
        limits.validate_backfill_paths([str(path)])
    assert path.exists()  # Validation never deletes durable or local source audio.


def test_language_probe_profile_refuses_compressed_expansion_before_decode(tmp_path):
    path = tmp_path / 'audio_omi_opus_16000_1_fs1920_1710000000.bin'
    path.write_bytes((struct.pack('<I', 1) + b'\0') * 501)
    limits.validate_backfill_paths([str(path)])
    with pytest.raises(limits.BackfillInputLimitExceeded):
        limits.validate_language_probe_paths([str(path)])
    assert path.exists()


@pytest.mark.parametrize('bound', ['raw', 'files', 'frames', 'duration'])
def test_language_probe_profile_bounds_the_whole_upload(tmp_path, bound):
    path = tmp_path / 'audio_phonemic_pcm16_16000_1_fs160_1710000000.bin'
    paths = [str(path)]
    if bound == 'raw':
        path.write_bytes(b'\0' * (limits.PROBE_MAX_RAW_BYTES + 1))
    elif bound == 'files':
        path.write_bytes(uploaded().file.read())
        paths *= limits.PROBE_MAX_FILES + 1
    elif bound == 'frames':
        path = tmp_path / 'audio_omi_opus_16000_1_fs40_1710000000.bin'
        path.write_bytes((struct.pack('<I', 1) + b'\0') * (limits.PROBE_MAX_FRAMES + 1))
        paths = [str(path)]
    else:
        path.write_bytes((struct.pack('<I', 65536) + b'\0' * 65536) * 30)
    with pytest.raises(limits.BackfillInputLimitExceeded):
        limits.validate_language_probe_paths(paths)


def test_full_tmpfs_is_capacity_pressure_and_other_errors_keep_their_class():
    import errno

    with pytest.raises(limits.BackfillStoragePressure):
        limits.raise_sync_storage_pressure(OSError(errno.ENOSPC, 'synthetic'))
    limits.raise_sync_storage_pressure(OSError(errno.EIO, 'synthetic'))


@pytest.mark.parametrize(
    'name',
    [
        'audio_pcm8_unknown_fs160_1710000000.bin',
        'audio_pcm16_8000_pcm8_unknown_fs160_1710000000.bin',
    ],
)
def test_legacy_pcm_names_and_mixed_codec_markers_use_actual_decoder_expansion(monkeypatch, name):
    assert limits.sync_pcm_format(name) == (8000, 1)
    monkeypatch.setattr(limits, 'MAX_BACKFILL_AUDIO_BYTES', 1279)
    with pytest.raises(HTTPException):
        limits.validate_backfill_uploads([uploaded(name=name)])


def test_opus_disk_full_mid_file_raises_capacity_pressure_and_keeps_no_prefix(tmp_path, monkeypatch):
    import errno
    import wave

    from utils.sync import files

    class FakeDecoder:
        def __init__(self, *args):
            pass

        def decode(self, data, frame_size):
            return b'\0' * 320

    raw = tmp_path / 'audio.opus'
    raw.write_bytes((struct.pack('<I', 4) + b'abcd') * 3)
    wav_path = tmp_path / 'audio.wav'
    real_writeframes = wave.Wave_write.writeframes
    calls = {'n': 0}

    def flaky_writeframes(self, data):
        calls['n'] += 1
        if calls['n'] == 2:
            raise OSError(errno.ENOSPC, 'synthetic tmpfs full')
        return real_writeframes(self, data)

    monkeypatch.setattr(files, 'Decoder', FakeDecoder)
    monkeypatch.setattr(wave.Wave_write, 'writeframes', flaky_writeframes)
    with pytest.raises(limits.BackfillStoragePressure):
        files.decode_opus_file_to_wav(str(raw), str(wav_path))
    assert not wav_path.exists()
    assert raw.exists()


class _Blob:
    def __init__(self, size, generation=7, data=b''):
        self.size = size
        self.generation = generation
        self.content_encoding = None
        self._data = data

    def reload(self, *args, **kwargs):
        pass

    def open(self, mode, chunk_size=None):
        return io.BytesIO(self._data)


def _storage_with(monkeypatch, blob, prepared=None):
    from utils.other import storage

    monkeypatch.setattr(storage, 'syncing_local_bucket', 'bucket', raising=False)
    monkeypatch.delenv('BUCKET_AUDIO_DERIVED', raising=False)
    client = type('C', (), {'bucket': lambda self, name: type('B', (), {'blob': lambda self, path: blob})()})()
    monkeypatch.setattr(storage, '_get_storage_client', lambda: client)
    monkeypatch.setattr(storage.staged_prefetch, 'take', lambda path: prepared)
    return storage


def test_prefetch_hit_short_write_is_cleaned_up_and_mapped_to_capacity_pressure(tmp_path, monkeypatch):
    import builtins
    import errno

    from utils.other import storage

    blob = _Blob(size=4)
    prepared = storage.StagedBytes(b'abcd', 'bucket', 7)
    mod = _storage_with(monkeypatch, blob, prepared)
    target = tmp_path / 'staged.bin'
    real_open = builtins.open

    class FullFile:
        def __init__(self, path):
            self._f = real_open(path, 'wb')

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self._f.close()

        def write(self, data):
            self._f.write(data[:1])
            raise OSError(errno.ENOSPC, 'synthetic full')

    monkeypatch.setattr(
        mod,
        'open',
        lambda path, mode='r': FullFile(path) if str(path) == str(target) else real_open(path, mode),
        raising=False,
    )
    with pytest.raises(limits.BackfillStoragePressure):
        mod.download_syncing_temporal_file(str(target), max_bytes=1024)
    assert not target.exists()


def test_unknown_blob_size_falls_through_to_the_capped_read(tmp_path, monkeypatch):
    blob = _Blob(size=None, data=b'x' * 10)
    mod = _storage_with(monkeypatch, blob)
    target = tmp_path / 'ok.bin'
    assert mod.download_syncing_temporal_file(str(target), max_bytes=1024) is True
    assert target.read_bytes() == b'x' * 10

    big = tmp_path / 'big.bin'
    blob = _Blob(size=None, data=b'x' * 2048)
    mod = _storage_with(monkeypatch, blob)
    with pytest.raises(limits.BackfillInputLimitExceeded):
        mod.download_syncing_temporal_file(str(big), max_bytes=1024)
    assert not big.exists()


def test_batch_storage_pressure_removes_earlier_local_files_but_not_staged_objects(tmp_path, monkeypatch):
    from utils.sync import pipeline

    first = tmp_path / 'first.bin'
    second = tmp_path / 'second.bin'

    def download(path, max_bytes=None):
        if path == str(first):
            first.write_bytes(b'ok')
            return True
        raise limits.BackfillStoragePressure('full')

    monkeypatch.setattr(pipeline, 'download_syncing_temporal_file', download)
    with pytest.raises(limits.BackfillStoragePressure):
        pipeline._download_staged_files([str(first), str(second)], bounded_backfill=True)
    assert not first.exists()
