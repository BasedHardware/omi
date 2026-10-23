"""Word offsets shared by sync transcription and its VAD file clock."""

from typing import Any
from models.transcript_segment import TranscriptSegment


def first_word_offset(words: list[Any]) -> float:
    """Seconds from the start of a VAD file to its first word.

    postprocess_words starts the transcript clock at this word, while the file's
    timestamp, stored audio and capture evidence start where VAD did. A word
    without a start time keeps the file clock.
    """
    first = words[0] if words else None
    timing = first.get('timestamp') if isinstance(first, dict) else None
    return round(float(timing[0]), 2) if timing else 0.0


def shift_to_vad_file_clock(segments: list[TranscriptSegment], offset: float) -> None:
    """Put lines timed from the first word back on the VAD file clock.

    started_at, the stored audio chunk and capture evidence share that clock. The
    file can open on a cough or noise well before the first word.
    """
    if offset:
        for segment in segments:
            segment.start = round(segment.start + offset, 2)
            segment.end = round(segment.end + offset, 2)
