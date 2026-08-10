"""Private-cloud audio backing for partial merge survivors (#4769).

When merge dedupe drops some lines but keeps others, full-WAV upload would
reintroduce duplicate private-cloud audio for the dropped ranges. Slice PCM to
each survivor's chunk-relative [start, end] so newly-appended lines keep
``segment present ⇒ chunk present`` without re-uploading already-represented audio.
"""

from __future__ import annotations

import io
import logging
from typing import Optional

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
) -> None:
    """Upload one private-cloud chunk per survivor range. Best-effort.

    Call only when some incoming lines were dropped and at least one survived.
    Survivors must still carry chunk-relative start/end and absolute timestamp
    (before conversation-relative rewrite).
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
            upload_audio_chunk(slice_pcm, uid, conversation_id, chunk_ts, data_protection_level)
        del pcm
    except Exception as e:
        logger.warning(
            f'sync: failed to store partial merge survivor audio for {conversation_id}@{file_timestamp}: {e}'
        )
