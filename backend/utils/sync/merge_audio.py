"""Private-cloud audio backing for partial merge survivors (#4769).

When merge dedupe drops some lines but keeps others, full-WAV upload would
reintroduce duplicate private-cloud audio for the dropped ranges. Slice PCM to
each survivor's chunk-relative [start, end] so newly-appended lines keep
``segment present ⇒ chunk present`` without re-uploading already-represented audio.
"""

from __future__ import annotations

import io
import logging
from typing import Optional, Callable

logger = logging.getLogger(__name__)

_PCM16_16K_BYTES_PER_SEC = 16000 * 2


def pcm16_16k_slice(pcm: bytes, start_s: float, end_s: float) -> bytes:
    """Return a sample-aligned PCM16 mono 16 kHz slice for [start_s, end_s)."""
    start_b = max(0, int(float(start_s) * _PCM16_16K_BYTES_PER_SEC))
    end_b = max(start_b, int(float(end_s) * _PCM16_16K_BYTES_PER_SEC))
    start_b -= start_b % 2
    end_b -= end_b % 2
    end_b = min(end_b, len(pcm))
    return pcm[start_b:end_b]


def _wav_bytes_to_pcm16_16k(audio_bytes: Optional[bytes]) -> Optional[bytes]:
    if not audio_bytes:
        return None
    from pydub import AudioSegment

    seg = AudioSegment.from_wav(io.BytesIO(audio_bytes))
    seg = seg.set_frame_rate(16000).set_channels(1).set_sample_width(2)
    return seg.raw_data


def store_partial_merge_survivor_audio(
    *,
    uid: str,
    conversation_id: str,
    file_timestamp: float,
    audio_bytes: Optional[bytes],
    data_protection_level: Optional[str],
    survivors: list,
    playback_clock_offset: float = 0.0,
) -> None:
    """Upload one private-cloud chunk per survivor range. Best-effort.

    Call only when some incoming lines were dropped and at least one survived.
    Survivors must still carry chunk-relative start/end and absolute timestamp
    (before conversation-relative rewrite). ``playback_clock_offset`` is the
    request-wide capture-skew offset; each survivor chunk persists its
    server-clock playback start beside its raw capture-clock key.
    """
    if not survivors or not audio_bytes:
        return
    try:
        from utils.other.storage import upload_audio_chunk

        pcm = _wav_bytes_to_pcm16_16k(audio_bytes)
        if not pcm:
            return
        for segment in survivors:
            slice_pcm = pcm16_16k_slice(pcm, float(segment['start']), float(segment['end']))
            if not slice_pcm:
                continue
            chunk_ts = float(segment.get('timestamp', float(file_timestamp) + float(segment['start'])))
            upload_audio_chunk(
                slice_pcm,
                uid,
                conversation_id,
                chunk_ts,
                data_protection_level,
                playback_start=chunk_ts - playback_clock_offset,
            )
        del pcm
    except Exception as e:
        logger.warning(
            f'sync: failed to store partial merge survivor audio for {conversation_id}@{file_timestamp}: {e}'
        )


def store_sync_audio_chunk(
    uid: str,
    conversation_id: str,
    timestamp: float,
    audio_bytes: Optional[bytes],
    data_protection_level: Optional[str],
    *,
    playback_start: Optional[float] = None,
    decode_audio: Callable[[Optional[bytes]], Optional[bytes]] | None = None,
    upload_audio: Callable[..., str] | None = None,
) -> None:
    """Legacy best-effort full chunk persistence with stable replay naming.

    ``playback_start`` is the server-clock (skew-normalized) start persisted
    beside the chunk for playback wall math; the blob key keeps the raw
    capture-clock ``timestamp``.
    """
    try:
        if upload_audio is None:
            from utils.other.storage import upload_audio_chunk

            upload_audio = upload_audio_chunk
        pcm = (decode_audio or _wav_bytes_to_pcm16_16k)(audio_bytes)
        if not pcm:
            return
        upload_audio(pcm, uid, conversation_id, float(timestamp), data_protection_level, playback_start=playback_start)
    except Exception as error:
        logger.warning('sync: failed to store audio chunk for %s@%s: %s', conversation_id, timestamp, error)


def store_intake_audio(
    uid: str,
    timestamp: float,
    audio_bytes: Optional[bytes],
    data_protection_level: str,
    survivors: list,
    transcript_segment_count: int,
    private_cloud_sync_enabled: bool,
    conversation_id: str,
    *,
    playback_start: Optional[float] = None,
    playback_clock_offset: float = 0.0,
    store_full: Callable[..., None] | None = None,
    store_partial: Callable[..., None] | None = None,
) -> None:
    """One shared legacy/batch full-vs-partial retained-audio policy.

    The playback timing pair follows the retained audio: the full chunk gets
    the caller's normalized ``playback_start``; survivor slices normalize
    their own chunk timestamps against ``playback_clock_offset``.
    """
    if private_cloud_sync_enabled and survivors:
        if len(survivors) == transcript_segment_count:
            (store_full or store_sync_audio_chunk)(
                uid, conversation_id, timestamp, audio_bytes, data_protection_level, playback_start=playback_start
            )
        else:
            (store_partial or store_partial_merge_survivor_audio)(
                uid=uid,
                conversation_id=conversation_id,
                file_timestamp=timestamp,
                audio_bytes=audio_bytes,
                data_protection_level=data_protection_level,
                survivors=survivors,
                playback_clock_offset=playback_clock_offset,
            )
