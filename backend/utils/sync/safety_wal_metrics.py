"""Low-cardinality safety-WAL dual-write measurements."""

import io
import wave

from prometheus_client import Counter

WAL_SECONDS_SKIPPED = Counter('sync_safety_wal_seconds_skipped', 'WAL seconds covered by live audio', ['reason'])
AUDIO_BYTES_NOT_STORED = Counter('sync_safety_wal_audio_bytes_not_stored', 'Decoded PCM bytes suppressed', ['reason'])
SEGMENTS_DEDUPED = Counter(
    'sync_safety_wal_segments_deduped', 'Sync segments already represented by live text', ['reason']
)


def suppressed_pcm_bytes(audio_bytes: bytes, survivors: list) -> int:
    """Bytes omitted by the partial-survivor uploader, expressed as 16k PCM."""
    try:
        with wave.open(io.BytesIO(audio_bytes), 'rb') as source:
            duration = source.getnframes() / source.getframerate()
        kept = sum(
            max(0.0, min(duration, float(segment['end'])) - max(0.0, float(segment['start']))) for segment in survivors
        )
        return max(0, int((duration - kept) * 32000))
    except (wave.Error, EOFError, ValueError, ZeroDivisionError):
        return 0
