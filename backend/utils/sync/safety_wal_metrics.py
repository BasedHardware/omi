"""Low-cardinality safety-WAL dual-write measurements."""

import io
import wave

from prometheus_client import REGISTRY, Counter


def _counter(name: str, description: str) -> Counter:
    try:
        return Counter(name, description, ['reason'])
    except ValueError:
        return REGISTRY._names_to_collectors[name]  # type: ignore[attr-defined]


WAL_SECONDS_SKIPPED = _counter('sync_safety_wal_seconds_skipped', 'WAL seconds covered by live audio')
AUDIO_BYTES_NOT_STORED = _counter('sync_safety_wal_audio_bytes_not_stored', 'Decoded PCM bytes suppressed')
SEGMENTS_DEDUPED = _counter('sync_safety_wal_segments_deduped', 'Sync segments already represented by live text')


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
