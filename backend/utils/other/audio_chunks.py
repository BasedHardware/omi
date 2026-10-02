"""Stored PCM iteration policies shared by speaker and transcription readers."""

from typing import Callable, Iterator, Optional, Tuple

from utils.other import storage


def iter_audio_chunk_pcm(
    uid: str,
    conversation_id: str,
    wanted: Callable[[float, Optional[float]], bool],
    sample_rate: int = 16000,
    *,
    single_chunks_only: bool = False,
    newest_first: bool = False,
    max_downloads: Optional[int] = None,
) -> Iterator[Tuple[float, bytes]]:
    """Yield ``(start_timestamp, pcm16)`` for each stored chunk blob, oldest first.

    One listing serves the whole pass, and each blob is decoded on its own so a
    caller can place audio by the blob's own start: merging several chunks drifts
    wherever stored chunks overlap. ``wanted(start, next_start)`` skips a blob
    before it is downloaded; ``next_start`` is the next chronological start,
    even when ``newest_first`` is requested. Speaker teaching opts into single
    chunks only (legacy batch interiors lost their timestamps), newest-first
    search, and a download-attempt cap. Other callers keep their existing policy.
    """
    bucket = storage.get_private_cloud_sync_bucket()
    chunks = storage.list_audio_chunks(uid, conversation_id)
    indexes = range(len(chunks) - 1, -1, -1) if newest_first else range(len(chunks))
    downloads = 0
    for index in indexes:
        chunk = chunks[index]
        # Legacy batches discard interior chunk timing. Their byte length is
        # not continuity evidence for a speaker-training window.
        if single_chunks_only and chunk.get('is_batch'):
            continue
        next_start = chunks[index + 1]['timestamp'] if index + 1 < len(chunks) else None
        if not wanted(chunk['timestamp'], next_start):
            continue
        if max_downloads is not None and downloads >= max_downloads:
            break
        downloads += 1
        pcm = storage.download_and_decode_chunk_blob(bucket, chunk['path'], uid, sample_rate)
        if pcm:
            yield chunk['timestamp'], pcm
