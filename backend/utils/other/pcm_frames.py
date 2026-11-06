"""PCM16 alignment shared by stored chunk decoders."""

import logging
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

# PCM16 mono: one sample is 2 bytes. A chunk whose byte count is not a multiple
# of this is truncated mid-sample.
_PCM16_FRAME_BYTES = 2


def align_pcm16_frames(pcm_data: bytes, source: str) -> bytes:
    """Drop a trailing partial PCM16 sample so decoded chunks stay frame-aligned.

    A chunk stored truncated mid-sample (interrupted upload) makes every later
    chunk in the merge byte-misaligned and leaves the merged buffer an odd byte
    count, which pydub rejects with a deterministic ValueError. The audio-merge
    Cloud Task retried that unretryable error to exhaustion and then marked
    playback permanently unavailable, losing the artifact for the conversation.
    Trimming the partial sample costs 1/32000s and keeps the merge buildable.
    """
    remainder = len(pcm_data) % _PCM16_FRAME_BYTES
    if not remainder:
        return pcm_data
    record_fallback(
        component='audio_merge',
        from_mode='pcm16_frames',
        to_mode='pcm16_frames_truncated',
        reason='malformed_doc',
        outcome='recovered',
        log=logger,
    )
    logger.warning(f'audio chunk not PCM16 frame-aligned, trimming {remainder} trailing byte(s): {source}')
    return pcm_data[:-remainder]
