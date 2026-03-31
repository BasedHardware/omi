"""Degraded batch transcription processor (#6052).

When the DG streaming socket is unavailable, this class buffers PCM audio
and periodically flushes it to Deepgram's pre-recorded API.  Segments are
fed back into the realtime pipeline with correct timestamp offsets and
unique stt_session ULIDs per batch chunk.

Usage in transcribe.py:
    processor = DegradedBatchProcessor(sample_rate=16000, uid='...', session_id='...')
    processor.feed(pcm_chunk)                   # in flush_stt_buffer when DG is down
    await processor.flush(stream_start, sink)   # periodic or on recovery
"""

import asyncio
import logging
import struct
import time
from collections import deque
from typing import Optional

from ulid import ULID

from utils.stt.pre_recorded import deepgram_prerecorded_from_bytes, postprocess_words
from utils.fair_use import record_dg_usage_ms

logger = logging.getLogger(__name__)

BATCH_INTERVAL_SECONDS = 30


def build_wav_bytes(pcm_data: bytes, sample_rate: int, channels: int = 1, bits_per_sample: int = 16) -> bytes:
    """Wrap raw PCM data in a WAV container for the pre-recorded API."""
    data_size = len(pcm_data)
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF',
        36 + data_size,
        b'WAVE',
        b'fmt ',
        16,
        1,  # PCM format
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b'data',
        data_size,
    )
    return header + pcm_data


class DegradedBatchProcessor:
    """Buffers PCM audio during STT degraded mode and flushes to pre-recorded API.

    Asyncio-task-safe for single-writer (the receive_data loop) and single-reader
    (the flush timer / recovery path).  The flush() method atomically detaches
    the buffer so new audio immediately goes into a fresh buffer.  On API failure
    the detached chunk is restored so audio is never permanently lost.
    """

    def __init__(self, sample_rate: int, uid: str, session_id: str):
        self._sample_rate = sample_rate
        self._uid = uid
        self._session_id = session_id
        self._buffer = bytearray()
        self._buffer_start_time: Optional[float] = None

    @property
    def has_audio(self) -> bool:
        return bool(self._buffer)

    def feed(self, pcm_data: bytes) -> None:
        """Append PCM audio to the degraded buffer."""
        if self._buffer_start_time is None:
            self._buffer_start_time = time.time()
        self._buffer.extend(pcm_data)

    async def flush(
        self,
        *,
        stream_start_time: float,
        segment_sink: deque,
        budget_exhausted: bool = False,
        track_usage: bool = False,
    ) -> int:
        """Flush buffer to pre-recorded API and push segments into *segment_sink*.

        Args:
            stream_start_time: Wall-clock time when the first audio byte of
                               the session was received (``first_audio_byte_timestamp``).
            segment_sink:      The ``realtime_segment_buffers`` deque.
            budget_exhausted:  If True, skip the DG call (fair-use gate).
            track_usage:       If True, record DG usage via ``record_dg_usage_ms``.

        Returns:
            Number of segments produced (0 if nothing was flushed).
        """
        if not self._buffer or self._buffer_start_time is None:
            return 0

        # Atomic detach — new audio goes into a fresh buffer
        pcm_chunk = bytes(self._buffer)
        batch_start = self._buffer_start_time
        self._buffer = bytearray()
        self._buffer_start_time = None

        if budget_exhausted:
            logger.info('Degraded batch skipped: DG budget exhausted uid=%s session=%s', self._uid, self._session_id)
            del pcm_chunk
            return 0

        wav_data = build_wav_bytes(pcm_chunk, self._sample_rate)
        duration_s = len(pcm_chunk) / (self._sample_rate * 2)  # 16-bit mono

        batch_offset = batch_start - stream_start_time
        batch_session = str(ULID())

        try:
            words = await asyncio.to_thread(
                deepgram_prerecorded_from_bytes,
                wav_data,
                self._sample_rate,
                True,  # diarize
            )
            del wav_data

            if not words:
                logger.info('Degraded batch: no words returned uid=%s session=%s', self._uid, self._session_id)
                return 0

            segments = postprocess_words(words, int(duration_s))
            del words

            # Convert TranscriptSegment objects to dicts matching streaming pipeline format.
            # postprocess_words rebases start/end to 0 — add batch_offset to align with stream timeline.
            segment_dicts = []
            for seg in segments:
                segment_dicts.append(
                    {
                        'start': round(seg.start + batch_offset, 2),
                        'end': round(seg.end + batch_offset, 2),
                        'speaker': seg.speaker,
                        'text': seg.text,
                        'is_user': seg.is_user,
                        'person_id': None,
                        'stt_session': batch_session,
                    }
                )

            if segment_dicts:
                segment_sink.extend(segment_dicts)
                if track_usage:
                    batch_ms = int(duration_s * 1000)
                    try:
                        await asyncio.to_thread(record_dg_usage_ms, self._uid, batch_ms)
                    except Exception:
                        pass  # Non-critical
                logger.info(
                    'Degraded batch: %d segments, offset=%.1fs, duration=%.1fs, session=%s uid=%s',
                    len(segment_dicts),
                    batch_offset,
                    duration_s,
                    batch_session[:8],
                    self._uid,
                )
            return len(segment_dicts)

        except Exception as e:
            # Restore the detached chunk so audio is not permanently lost.
            # Prepend it to the current buffer (new audio may have arrived during the API call).
            self._buffer = bytearray(pcm_chunk) + self._buffer
            if self._buffer_start_time is None:
                self._buffer_start_time = batch_start
            else:
                self._buffer_start_time = min(self._buffer_start_time, batch_start)
            logger.error(
                'Degraded batch failed (audio restored to buffer): %s uid=%s session=%s', e, self._uid, self._session_id
            )
            return 0

    async def run_timer(self, *, is_active: callable, flush_kwargs: callable) -> None:
        """Periodic task — flushes every BATCH_INTERVAL_SECONDS while is_active() is True.

        Args:
            is_active:    Callable returning True while the timer should keep running
                          (typically ``lambda: websocket_active and stt_degraded``).
            flush_kwargs: Callable returning a dict of keyword arguments for flush()
                          (captures current session state at each tick).
        """
        while is_active():
            await asyncio.sleep(BATCH_INTERVAL_SECONDS)
            if not is_active():
                break
            await self.flush(**flush_kwargs())
