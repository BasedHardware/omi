"""Bound upload retries and retain deletion references beyond possible cloud IO."""

from io import BytesIO
import time

UPLOAD_CHUNK_BYTES = 8 * 1024 * 1024
UPLOAD_TIMEOUT = (10, 120)
UPLOAD_RETRY_SECONDS = 120
UPLOAD_STREAM_SECONDS = 15 * 60
# A last request may start just before the stream deadline. Include retry budget,
# socket timeouts, the 30s registration grace, and scheduling/cleanup margin.
UPLOAD_PENDING_SECONDS = 30 * 60


class UploadStream(BytesIO):
    def __init__(self, body: bytes):
        super().__init__(body)
        self.deadline = time.monotonic() + UPLOAD_STREAM_SECONDS

    def read(self, size: int | None = -1) -> bytes:
        if time.monotonic() >= self.deadline:
            raise TimeoutError('batch artifact upload deadline exceeded')
        return super().read(size)
