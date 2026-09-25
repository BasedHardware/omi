from collections import deque
from typing import Deque, Optional, Tuple


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
        # A non-positive sample_rate or duration yields a zero (or, unclamped, negative) capacity.
        # sample_rate reaches here straight from the /v4/listen query param, which is only range
        # checked for opus codecs, so a pcm client can send 0 or a negative value. Clamp so
        # bytearray() cannot raise "negative count" at construction. Mirrors resample_pcm, which
        # guards the same non-positive rate.
        self.capacity = max(0, int(duration_seconds * self.bytes_per_second))
        self.buffer = bytearray(self.capacity)
        self.write_pos = 0
        self.total_bytes_written = 0
        self.last_write_timestamp: Optional[float] = None
        # Logical spans of the audio currently retained: (first-sample wall
        # time, byte count), oldest first.
        self._spans: Deque[Tuple[float, int]] = deque()
        self._buffered_bytes = 0

    def _append_bytes(self, data: bytes) -> None:
        for byte in data:
            self.buffer[self.write_pos] = byte
            self.write_pos = (self.write_pos + 1) % self.capacity
        self.total_bytes_written += len(data)

    def _record_span(self, start_ts: float, n_bytes: int) -> None:
        if n_bytes <= 0:
            return
        self._spans.append((start_ts, n_bytes))
        self._buffered_bytes += n_bytes
        excess = self._buffered_bytes - self.capacity
        while excess > 0 and self._spans:
            front_ts, front_bytes = self._spans[0]
            if front_bytes > excess:
                self._spans[0] = (front_ts + excess / self.bytes_per_second, front_bytes - excess)
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
        front_ts, _ = self._spans[0]
        back_ts, back_bytes = self._spans[-1]
        return (front_ts, back_ts + back_bytes / self.bytes_per_second)

    def extract(self, start_ts: float, end_ts: float) -> Optional[bytes]:
        """Extract audio for absolute timestamp range."""
        time_range = self.get_time_range()
        if time_range is None:
            return None

        buffer_start_ts, buffer_end_ts = time_range
        actual_start = max(start_ts, buffer_start_ts)
        actual_end = min(end_ts, buffer_end_ts)

        if actual_start >= actual_end:
            return None

        bytes_in_buffer = min(self.total_bytes_written, self.capacity)
        buffer_logical_start = (self.write_pos - bytes_in_buffer) % self.capacity

        start_offset = int((actual_start - buffer_start_ts) * self.bytes_per_second)
        end_offset = int((actual_end - buffer_start_ts) * self.bytes_per_second)

        # Align the start to the PCM16 2-byte sample boundary. actual_start is an arbitrary float
        # timestamp, so start_offset is odd roughly half the time; an odd offset begins the copy on a
        # sample's high byte and byte-shifts every int16 sample into noise. length below is already
        # forced even, so flooring the start to an even offset is what keeps whole samples intact.
        start_offset -= start_offset % 2

        # Ensure even number of bytes (PCM16)
        length = ((end_offset - start_offset) // 2) * 2
        if length <= 0:
            return None

        result = bytearray(length)
        for i in range(length):
            pos = (buffer_logical_start + start_offset + i) % self.capacity
            result[i] = self.buffer[pos]

        return bytes(result)
