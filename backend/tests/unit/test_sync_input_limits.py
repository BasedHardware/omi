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
