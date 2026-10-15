"""Stored PCM iteration and invocation-scoped I/O shared by speaker readers."""

import threading
import time
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from google.api_core.exceptions import (
    DeadlineExceeded,
    InternalServerError,
    RetryError,
    ServiceUnavailable,
    TooManyRequests,
)

from utils.other import storage

MAX_SPEAKER_DOWNLOADS = 32
MAX_SPEAKER_BYTES = 64 * 1024 * 1024
MAX_SPEAKER_READ_SECONDS = 30.0


class AudioChunkReadSession:
    """One lazy listing, decoded cache and storage budget per teaching invocation."""

    def __init__(self, uid: str, conversation_id: str, sample_rate: int = 16000):
        self.uid, self.conversation_id, self.sample_rate = uid, conversation_id, sample_rate
        self._chunks: Optional[List[Dict[str, Any]]] = None
        self.cache: Dict[str, Tuple[Optional[bytes], str]] = {}
        self.last_chunk: Optional[Dict[str, Any]] = None
        self.reason = 'missing_blob'
        self.downloads = 0
        self.bytes = 0
        self.deadline = time.monotonic() + MAX_SPEAKER_READ_SECONDS
        self.lock = threading.Lock()
        self.limit_hit = False

    def in_budget(self):
        if self.limit_hit or time.monotonic() >= self.deadline:
            self.reason = 'download_limit'
            self.limit_hit = True
            return False
        return True

    @property
    def chunks(self):
        from google.cloud.storage.retry import DEFAULT_RETRY

        if self._chunks is None:
            if not self.in_budget():
                return []
            remaining = self.deadline - time.monotonic()
            try:
                listed = storage.list_audio_chunks(
                    self.uid,
                    self.conversation_id,
                    timeout=min(1.0, remaining),
                    retry=DEFAULT_RETRY.with_timeout(min(1.0, remaining)),
                    deadline=self.deadline,
                )
                self._chunks = [
                    {**chunk, 'span': dict(chunk['span'])} if isinstance(chunk.get('span'), dict) else dict(chunk)
                    for chunk in listed
                ]
            except (
                TimeoutError,
                RetryError,
                DeadlineExceeded,
                InternalServerError,
                ServiceUnavailable,
                TooManyRequests,
            ):
                self.reason = 'download_limit'
                self.limit_hit = True
                self._chunks = []
        return self._chunks

    def fetch(self, path: str) -> Optional[bytes]:
        from google.cloud.storage.retry import DEFAULT_RETRY

        # Main's merger fans out. One lock serializes actual I/O and budget
        # reservations; retries consume the same count and byte allowance.
        with self.lock:
            if not self.in_budget():
                return None
            if path in self.cache:
                pcm, reason = self.cache[path]
                if pcm is None:
                    self.reason = reason
                return pcm
            chunk = next((c for c in self.chunks if c['path'] == path), None)
            if chunk is None:
                self.reason = 'missing_blob'
                self.cache[path] = (None, self.reason)
                return None
            size = chunk.get('size')
            remaining = self.deadline - time.monotonic()
            semaphore = storage.get_storage_chunk_semaphore()
            if not semaphore.acquire(timeout=max(0, remaining)):
                self.reason, self.limit_hit = 'download_limit', True
                return None
            try:
                # Wrap the leaf with the SDK default transient predicate/backoff,
                # refreshing timeout and charging every attempt, including 503s.
                session = self
                bucket = storage.get_private_cloud_sync_bucket()

                class BudgetedBlob:
                    def download_as_bytes(self, **kwargs):
                        maximum = MAX_SPEAKER_BYTES - session.bytes
                        if (
                            not session.in_budget()
                            or session.downloads >= MAX_SPEAKER_DOWNLOADS
                            or maximum <= 0
                            or (size is not None and size > maximum)
                        ):
                            session.reason, session.limit_hit = 'download_limit', True
                            raise TimeoutError('speaker audio budget exhausted')
                        session.downloads += 1
                        # Reserve the maximum transferable bytes on each attempt,
                        # including failed attempts. Unknown sizes read a bounded
                        # range to detect budget truncation, never decode it.
                        allowance = size if size is not None else maximum
                        session.bytes += allowance
                        download_kwargs: Dict[str, Any] = {
                            'timeout': max(0.001, session.deadline - time.monotonic()),
                            'retry': None,
                            'end': allowance - 1,
                        }
                        generation = chunk.get('generation')
                        if generation is not None:
                            download_kwargs['if_generation_match'] = generation
                        data = bucket.blob(path).download_as_bytes(**download_kwargs)
                        if size is None and len(data) >= allowance:
                            session.reason, session.limit_hit = 'download_limit', True
                            raise TimeoutError('unknown object exceeds speaker byte allowance')
                        return data

                retry = DEFAULT_RETRY.with_timeout(max(0.001, self.deadline - time.monotonic()))
                # Retry the download, not decode/decrypt failures.
                proxy = BudgetedBlob()
                downloaded = retry(proxy.download_as_bytes)()

                class DownloadedBlob:
                    def download_as_bytes(self, **kwargs):
                        return downloaded

                class DownloadedBucket:
                    def blob(self, name):
                        return DownloadedBlob()

                self.reason = 'missing_blob'
                pcm = storage.download_and_decode_chunk_blob(
                    DownloadedBucket(),
                    path,
                    self.uid,
                    self.sample_rate,
                    on_failure=self._failure,
                )
                if not self.in_budget():
                    return None
                self.cache[path] = (pcm, self.reason)
                return pcm
            except storage.NotFound:
                self.reason = 'missing_blob'
                self.cache[path] = (None, self.reason)
                return None
            except Exception:
                if not self.in_budget():
                    self.reason = 'download_limit'
                else:
                    self.reason = 'download_failed'
                # Transient failures never become permanent missing-audio cache entries.
                return None
            finally:
                semaphore.release()

    def _failure(self, reason: str):
        self.reason = reason


def chunk_start(chunk) -> float:
    return chunk.get('span', {}).get('start', chunk['timestamp'])


def chunk_end_upper_bound(chunk, sample_rate: int) -> Optional[float]:
    span = chunk.get('span')
    if span:
        return span['start'] + span['samples'] / span['sample_rate']
    # Ciphertext adds framing/authentication bytes, so its size is a safe
    # upper bound on raw PCM duration. Encoded Opus size is not a duration.
    if chunk['path'].endswith(('.bin', '.enc')) and not chunk['path'].endswith('.opus.enc'):
        if chunk.get('size') is not None:
            return chunk['timestamp'] + chunk['size'] / (2 * sample_rate) + 0.000501
    return None


def iter_audio_chunk_pcm(
    uid: str,
    conversation_id: str,
    wanted: Callable[[float, Optional[float]], bool],
    sample_rate: int = 16000,
    *,
    single_chunks_only: bool = False,
    newest_first: bool = False,
    max_downloads: Optional[int] = None,
    session: Optional[AudioChunkReadSession] = None,
    window_start: Optional[float] = None,
) -> Iterator[Tuple[float, bytes]]:
    """Yield individual decoded blobs; an optional session shares listing/cache/budget.

    Other transcription/matching readers retain their existing admission policy.
    """
    bucket = storage.get_private_cloud_sync_bucket()
    chunks = session.chunks if session is not None else storage.list_audio_chunks(uid, conversation_id)
    chunks = sorted(chunks, key=chunk_start)
    indexes = range(len(chunks) - 1, -1, -1) if newest_first else range(len(chunks))
    downloads = 0
    for index in indexes:
        chunk = chunks[index]
        next_start = chunk_start(chunks[index + 1]) if index + 1 < len(chunks) else None
        if not wanted(chunk_start(chunk), next_start):
            continue
        if single_chunks_only and chunk.get('is_batch') and not chunk.get('span'):
            if session is not None:
                session.reason = 'unverified_batch'
            continue
        upper_end = chunk_end_upper_bound(chunk, sample_rate)
        if window_start is not None and upper_end is not None and upper_end <= window_start:
            continue
        if max_downloads is not None and downloads >= max_downloads:
            if session is not None:
                session.reason = 'download_limit'
            break
        downloads += 1
        if session is not None:
            session.last_chunk = chunk
            pcm = session.fetch(chunk['path'])
        else:
            with storage.get_storage_chunk_semaphore():
                pcm = storage.download_and_decode_chunk_blob(bucket, chunk['path'], uid, sample_rate)
        if pcm:
            yield chunk_start(chunk), pcm
