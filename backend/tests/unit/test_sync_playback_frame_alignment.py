"""Regression tests: a PCM16 chunk truncated mid-sample must not lose the artifact.

Prod signature (2026-08-17..19, backend-sync): ``POST /v2/audio-merge-jobs/run``
returned 500 four times for the same conv/file with
``data length must be a multiple of '(sample_width * channels)'`` — pydub
rejecting an odd-length buffer. The error is deterministic, so every retry
failed identically and the job then marked playback permanently unavailable.
"""

from unittest.mock import MagicMock, patch

import pytest
from pydub import AudioSegment

from utils.other import storage as storage_mod
from utils.sync import playback as playback_mod


class _FakeNotFound(Exception):
    """storage_mod.NotFound is patched to this so the mocked blob can 404."""

    pass


def _blob_factory(ext_data_map):
    def factory(path):
        blob = MagicMock()
        for ext, data in ext_data_map.items():
            if path.endswith(f'.{ext}'):
                blob.download_as_bytes.return_value = data
                return blob
        blob.download_as_bytes.side_effect = _FakeNotFound('not found')
        return blob

    return factory


@pytest.fixture(autouse=True)
def _mock_storage_client(monkeypatch):
    monkeypatch.setattr(storage_mod, "storage_client", MagicMock())


def test_pydub_rejects_odd_length_pcm_control():
    """Control for the prod error: the encode step really does fail on odd input."""
    with pytest.raises(ValueError, match="multiple of"):
        AudioSegment(data=b'\x00' * 641, sample_width=2, frame_rate=16000, channels=1)


@patch.object(storage_mod, 'NotFound', _FakeNotFound)
def test_truncated_chunk_is_frame_aligned():
    """A chunk stored with a half sample is trimmed to whole PCM16 frames."""
    bucket = MagicMock()
    bucket.blob.side_effect = _blob_factory({'bin': b'\x11\x22' * 320 + b'\x33'})
    storage_mod.storage_client.bucket.return_value = bucket

    merged = storage_mod.download_audio_chunks_and_merge('uid', 'conv', [1000.0], fill_gaps=False)

    assert len(merged) % 2 == 0
    assert merged == b'\x11\x22' * 320


@patch.object(storage_mod, 'NotFound', _FakeNotFound)
def test_truncated_chunk_does_not_byte_shift_later_chunks():
    """The trailing half sample must not push every later chunk off the frame grid."""
    bucket = MagicMock()

    def factory(path):
        blob = MagicMock()
        if path.endswith('1000.000.bin'):
            blob.download_as_bytes.return_value = b'\x11\x22' * 320 + b'\x33'
        elif path.endswith('1000.020.bin'):
            blob.download_as_bytes.return_value = b'\x44\x55' * 320
        else:
            blob.download_as_bytes.side_effect = _FakeNotFound('not found')
        return blob

    bucket.blob.side_effect = factory
    storage_mod.storage_client.bucket.return_value = bucket

    merged = storage_mod.download_audio_chunks_and_merge('uid', 'conv', [1000.0, 1000.02], fill_gaps=False)

    assert len(merged) % 2 == 0
    # Second chunk still starts on an even offset, so its samples decode as stored.
    assert merged.endswith(b'\x44\x55' * 320)
    assert merged.index(b'\x44\x55' * 320) % 2 == 0


@patch.object(storage_mod, 'NotFound', _FakeNotFound)
def test_build_playback_artifact_survives_truncated_chunk():
    """The real merge-job path completes instead of raising the retried ValueError.

    Only the MP3 encode is stubbed — pydub shells out to ffmpeg, which the unit
    runner does not carry. The call that actually raised in production, the
    AudioSegment construction over the merged buffer, still runs for real.
    """
    bucket = MagicMock()
    bucket.blob.side_effect = _blob_factory({'bin': b'\x00\x01' * 16000 + b'\x02'})
    storage_mod.storage_client.bucket.return_value = bucket

    encoded_lengths = []

    def fake_export(self, out_f, **kwargs):
        encoded_lengths.append(len(self.raw_data))
        out_f.write(b'mp3-stub')
        return out_f

    with patch.object(AudioSegment, 'export', fake_export):
        mp3_data = playback_mod.build_playback_artifact('uid', 'conv', [1000.0])

    assert mp3_data == b'mp3-stub'
    assert encoded_lengths == [32000]
