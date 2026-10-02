"""Stored PCM iteration and invocation-scoped I/O shared by speaker readers."""

import threading
import time
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

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
        self.compatibility_escape = False

    @property
    def chunks(self):
        if self._chunks is None:
            self._chunks = storage.list_audio_chunks(
                self.uid, self.conversation_id, timeout=max(0.001, self.deadline - time.monotonic())
            )
        return self._chunks

    def fetch(self, path: str) -> Optional[bytes]:
        return self._fetch(path, limited=True)

    def compatibility_fetch(self, path: str) -> Optional[bytes]:
        """Preserve main's clips after the improved search spends its budget.

        Only main's selected paths may call this. Count and byte/time caps bound
        the new search, not this explicitly measured compatibility exception.
        """
        self.compatibility_escape = True
        return self._fetch(path, limited=False)

    def _fetch(self, path: str, *, limited: bool) -> Optional[bytes]:
        # The compatibility merger fans out; cache and budget are shared there,
        # too. Serializing these short reads avoids duplicate pooled downloads.
        with self.lock:
            if path in self.cache:
                pcm, reason = self.cache[path]
                if pcm is None:
                    self.reason = reason
                return pcm
            chunk = next((c for c in self.chunks if c['path'] == path), None)
            if chunk is None:
                return None
            size = chunk.get('size')
            remaining = self.deadline - time.monotonic()
            if limited and (
                self.downloads >= MAX_SPEAKER_DOWNLOADS
                or remaining <= 0
                or (size is not None and self.bytes + size > MAX_SPEAKER_BYTES)
            ):
                self.reason = 'download_limit'
                self.limit_hit = True
                return None
            acquired = (
                storage.get_storage_chunk_semaphore().acquire(timeout=max(0, remaining))
                if limited
                else storage.get_storage_chunk_semaphore().acquire()
            )
            if not acquired:
                self.reason = 'download_limit'
                self.limit_hit = True
                return None
            try:
                remaining = self.deadline - time.monotonic()
                if limited and remaining <= 0:
                    self.reason = 'download_limit'
                    self.limit_hit = True
                    return None
                self.downloads += 1
                # Listing sizes are authoritative GCS object lengths. Unknown
                # sizes use a capped range so they cannot evade the byte budget.
                maximum = MAX_SPEAKER_BYTES - self.bytes
                kwargs = {'timeout': remaining, 'retry': None} if limited else {}
                if limited and size is None:
                    kwargs['end'] = maximum - 1
                self.bytes += size if size is not None else (maximum if limited else 0)
                pcm = storage.download_and_decode_chunk_blob(
                    storage.get_private_cloud_sync_bucket(),
                    path,
                    self.uid,
                    self.sample_rate,
                    download_kwargs=kwargs,
                    on_failure=self._failure,
                )
                if limited and size is None and pcm is not None and len(pcm) >= maximum:
                    self.reason = 'download_limit'
                    self.limit_hit = True
                    pcm = None
                # Budget/time failures can retry only through main's compatibility
                # path. Real missing/decode failures remain cached across windows.
                if pcm is not None or self.reason != 'download_limit':
                    self.cache[path] = (pcm, self.reason)
                return pcm
            except Exception:
                self.reason = 'download_limit' if limited and time.monotonic() >= self.deadline else 'download_failed'
                self.limit_hit = self.limit_hit or self.reason == 'download_limit'
                if self.reason != 'download_limit':
                    self.cache[path] = (None, self.reason)
                return None
            finally:
                storage.get_storage_chunk_semaphore().release()

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
