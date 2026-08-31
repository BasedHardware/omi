"""Regression tests: a PCM16 chunk truncated mid-sample must not lose the artifact.

Prod signature (2026-08-17..19, backend-sync): ``POST /v2/audio-merge-jobs/run``
returned 500 four times for the same conv/file with
``data length must be a multiple of '(sample_width * channels)'`` — pydub
rejecting an odd-length buffer. The error is deterministic, so every retry
failed identically and the job then marked playback permanently unavailable.
"""

from unittest.mock import patch

import pytest
from pydub import AudioSegment

from tests.object_store_fakes import FakeObjectStore
from utils.other import storage as storage_mod
from utils.sync import playback as playback_mod


def _install_chunks(monkeypatch, chunks: dict) -> FakeObjectStore:
    """Seed the neutral object store with `{timestamp: pcm_bytes}` and install it on the seam.

    Upstream faked raw GCS blobs (`storage_client.bucket().blob().download_as_bytes()`), a surface
    this module no longer has: storage goes through the object-store port (ADR-0032/WP6). Seeding
    the store instead is also stronger coverage — the real `list_audio_chunks` path resolution and
    the real download run, and a missing object raises the neutral ObjectNotFound rather than a
    patched GCS exception.
    """
    store = FakeObjectStore()
    for ts, data in chunks.items():
        store.put(storage_mod.private_cloud_sync_bucket, f'chunks/uid/conv/{ts:.3f}.bin', data)
    monkeypatch.setattr(storage_mod, '_object_store', lambda: store)
    return store


def test_pydub_rejects_odd_length_pcm_control():
    """Control for the prod error: the encode step really does fail on odd input."""
    with pytest.raises(ValueError, match="multiple of"):
        AudioSegment(data=b'\x00' * 641, sample_width=2, frame_rate=16000, channels=1)


def test_truncated_chunk_is_frame_aligned(monkeypatch):
    """A chunk stored with a half sample is trimmed to whole PCM16 frames."""
    _install_chunks(monkeypatch, {1000.0: b'\x11\x22' * 320 + b'\x33'})

    merged = storage_mod.download_audio_chunks_and_merge('uid', 'conv', [1000.0], fill_gaps=False)

    assert len(merged) % 2 == 0
    assert merged == b'\x11\x22' * 320


def test_truncated_chunk_does_not_byte_shift_later_chunks(monkeypatch):
    """The trailing half sample must not push every later chunk off the frame grid."""
    _install_chunks(
        monkeypatch,
        {1000.0: b'\x11\x22' * 320 + b'\x33', 1000.02: b'\x44\x55' * 320},
    )

    merged = storage_mod.download_audio_chunks_and_merge('uid', 'conv', [1000.0, 1000.02], fill_gaps=False)

    assert len(merged) % 2 == 0
    # Second chunk still starts on an even offset, so its samples decode as stored.
    assert merged.endswith(b'\x44\x55' * 320)
    assert merged.index(b'\x44\x55' * 320) % 2 == 0


def test_build_playback_artifact_survives_truncated_chunk(monkeypatch):
    """The real merge-job path completes instead of raising the retried ValueError.

    Only the MP3 encode is stubbed — pydub shells out to ffmpeg, which the unit
    runner does not carry. The call that actually raised in production, the
    AudioSegment construction over the merged buffer, still runs for real.
    """
    _install_chunks(monkeypatch, {1000.0: b'\x00\x01' * 16000 + b'\x02'})

    encoded_lengths = []

    def fake_export(self, out_f, **kwargs):
        encoded_lengths.append(len(self.raw_data))
        out_f.write(b'mp3-stub')
        return out_f

    with patch.object(AudioSegment, 'export', fake_export):
        mp3_data = playback_mod.build_playback_artifact('uid', 'conv', [1000.0])

    assert mp3_data == b'mp3-stub'
    assert encoded_lengths == [32000]
