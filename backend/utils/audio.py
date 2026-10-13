from collections import deque
from typing import Deque, Optional, Tuple

# Highest rate /v4/listen admits (utils.transcribe_decisions.SUPPORTED_SAMPLE_RATES). The ring
# buffer never sizes itself past this rate, so a caller that skips validation cannot make it
# allocate an unbounded bytearray.
MAX_RING_BUFFER_SAMPLE_RATE = 48000


class ExtractedPCM(bytes):
    """PCM bytes plus a count of samples restored at known full-span ends."""

    restored_samples: int

    def __new__(cls, pcm: bytearray, restored_samples: int) -> 'ExtractedPCM':
        result = super().__new__(cls, pcm)
        result.restored_samples = restored_samples
        return result


class AudioRingBuffer:
    """Circular buffer storing last N seconds of PCM16 mono audio.

    Positions are tracked with a per-write span ledger: each buffered chunk
    remembers the wall time of its first sample (``write_positioned``, the
    audio-timeline v2 path) or its end-of-arrival approximation (``write``,
    the legacy path), so ``get_time_range``/``extract`` never assume that a
    long arrival gap means continuous audio.
    """

    def __init__(self, duration_seconds: float, sample_rate: int):
        self.sample_rate = sample_rate
        self.bytes_per_second = sample_rate * 2  # PCM16 mono
        # sample_rate comes from the /v4/listen query param. validate_audio_format restricts it to
        # standard rates, but this buffer is the allocation an unchecked rate would blow up, so it
        # also guards itself: a non-positive rate or duration yields a zero capacity (bytearray()
        # cannot raise "negative count"; mirrors resample_pcm), and an oversized rate is capped at
        # MAX_RING_BUFFER_SAMPLE_RATE (the buffer then retains fewer seconds rather than OOM the pod).
        capped_bytes_per_second = min(self.bytes_per_second, MAX_RING_BUFFER_SAMPLE_RATE * 2)
        self.capacity = max(0, int(duration_seconds * capped_bytes_per_second))
        self.buffer = bytearray(self.capacity)
        self.write_pos = 0
        self.total_bytes_written = 0
        self.last_write_timestamp: Optional[float] = None
        # Logical spans of the audio currently retained: (first-sample wall
        # time, byte count, absolute byte index of the span's first byte),
        # oldest first. The absolute index locates the span inside the byte
        # ring (position = absolute % capacity) even after wraparound.
        self._spans: Deque[Tuple[float, int, int]] = deque()
        self._buffered_bytes = 0

    def _append_bytes(self, data: bytes) -> None:
        n = len(data)
        copy = min(n, self.capacity)
        source_offset = n - copy
        start = (self.write_pos + source_offset) % self.capacity
        dest = memoryview(self.buffer)
        source = memoryview(data)[source_offset:]
        first = min(copy, self.capacity - start)
        dest[start : start + first] = source[:first]
        if first < copy:
            dest[: copy - first] = source[first:]
        self.write_pos = (self.write_pos + n) % self.capacity
        self.total_bytes_written += n

    def _record_span(self, start_ts: float, n_bytes: int) -> None:
        if n_bytes <= 0:
            return
        self._spans.append((start_ts, n_bytes, self.total_bytes_written - n_bytes))
        self._buffered_bytes += n_bytes
        excess = self._buffered_bytes - self.capacity
        while excess > 0 and self._spans:
            front_ts, front_bytes, front_abs = self._spans[0]
            if front_bytes > excess:
                self._spans[0] = (
                    front_ts + excess / self.bytes_per_second,
                    front_bytes - excess,
                    front_abs + excess,
                )
                self._buffered_bytes -= excess
                excess = 0
            else:
                self._spans.popleft()
                self._buffered_bytes -= front_bytes
                excess -= front_bytes

    def write(self, data: bytes, timestamp: float):
        """Append audio data; ``timestamp`` is the chunk's arrival (its end)."""
        if self.capacity <= 0:
            # Zero-capacity buffer (non-positive sample_rate/duration): skip rather than IndexError
            # on buffer[0] or ZeroDivisionError on % capacity when the first audio frame arrives.
            # last_write_timestamp stays None, so get_time_range()/extract() report nothing buffered
            # and speaker matching handles that, keeping the live session alive.
            return
        self._append_bytes(data)
        self.last_write_timestamp = timestamp
        self._record_span(timestamp - len(data) / self.bytes_per_second, len(data))

    def write_positioned(self, data: bytes, start_ts: float):
        """Append audio whose first sample is at ``start_ts`` (capture projection)."""
        if self.capacity <= 0:
            return
        self._append_bytes(data)
        self.last_write_timestamp = start_ts + len(data) / self.bytes_per_second
        self._record_span(start_ts, len(data))

    def get_time_range(self) -> Optional[Tuple[float, float]]:
        """Return (start_ts, end_ts) of audio currently in buffer."""
        if not self._spans:
            return None
        front_ts, _, _ = self._spans[0]
        back_ts, back_bytes, _ = self._spans[-1]
        return (front_ts, back_ts + back_bytes / self.bytes_per_second)

    def _byte_window(self, lo: float, hi: float, span_start: float, span_bytes: int) -> tuple[int, int, int]:
        offset = int((lo - span_start) * self.bytes_per_second)
        offset -= offset % 2
        end_offset = int((hi - span_start) * self.bytes_per_second)
        old_length = ((end_offset - offset) // 2) * 2
        # An exact stored span end names its physical byte count. Subtracting
        # epoch floats and truncating can otherwise discard a whole sample.
        # Interior ends keep the existing floor; no tolerance or padding.
        if hi == span_start + span_bytes / self.bytes_per_second:
            end_offset = span_bytes
        length = ((end_offset - offset) // 2) * 2
        return offset, length, max(0, length - old_length) // 2

    def extract(self, start_ts: float, end_ts: float) -> Optional[bytes]:
        """Extract the audio overlapping ``[start_ts, end_ts)`` by walking the span ledger.

        Bytes are copied span by span, so a wall-clock arrival gap inside the
        window is skipped rather than misread as continuous audio: the byte
        ring holds only the bytes actually written, never the silence of a
        client stall, and a window crossing a stall must not translate the
        whole wall delta into one byte offset.
        """
        if not self._spans:
            return None
        result = bytearray()
        restored_samples = 0
        for span_start_ts, n_bytes, start_abs in self._spans:
            span_end_ts = span_start_ts + n_bytes / self.bytes_per_second
            lo = max(start_ts, span_start_ts)
            hi = min(end_ts, span_end_ts)
            if hi <= lo:
                continue
            lo_off, length, restored = self._byte_window(lo, hi, span_start_ts, n_bytes)
            restored_samples += restored
            if length <= 0:
                continue
            src = (start_abs + lo_off) % self.capacity
            if src + length <= self.capacity:
                result += self.buffer[src : src + length]
            else:
                first = self.capacity - src
                result += self.buffer[src:]
                result += self.buffer[: length - first]
        if not result:
            return None
        return ExtractedPCM(result, restored_samples)

    def proven_byte_ranges(self, start_ts: float, end_ts: float) -> list[tuple[int, int]]:
        """Physical PCM positions intersecting a window; timestamps cannot invent bytes.

        Use the same sample alignment as extraction. Absolute append positions
        survive ring wrap and distinguish new buffered PCM from segment replays.
        """
        result = []
        cursor = start_ts
        for span_start, n_bytes, start_abs in self._spans:
            lo, hi = max(cursor, span_start), min(end_ts, span_start + n_bytes / self.bytes_per_second)
            if hi <= lo:
                continue
            offset, length, _ = self._byte_window(lo, hi, span_start, n_bytes)
            if length > 0:
                result.append((start_abs + offset, start_abs + offset + length))
                cursor = hi
        return result
