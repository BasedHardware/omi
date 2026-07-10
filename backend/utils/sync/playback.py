from __future__ import annotations

import io
import logging
import wave
from typing import Any

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydub import AudioSegment

from utils.cloud_tasks import is_audio_merge_dispatch_enabled
from utils.executors import postprocess_executor, storage_executor, submit_with_context
from utils.other.storage import (
    _PRECACHE_FILE_SEM,  # type: ignore[reportPrivateUsage]  # internal semaphore, intentional cross-module use
    compute_audio_files_fingerprint,
    download_audio_chunks_and_merge,
    download_legacy_merged_wav,
    download_playback_artifact,
    enqueue_conversation_artifact_build,
    enqueue_conversation_audio_merge,
    get_conversation_playback_signed_url,
    get_conversation_playback_unavailable_fingerprint,
    get_merged_audio_signed_url,
    get_or_create_merged_audio,
    get_playback_artifact_signed_url,
    is_playback_unavailable,
)

logger = logging.getLogger(__name__)

AUDIO_SAMPLE_RATE = 16000
AUDIO_URLS_POLL_AFTER_MS = 3000


def pcm_to_wav(pcm_data: bytes, sample_rate: int = 16000, channels: int = 1, sample_width: int = 2) -> bytes:
    """Convert raw PCM data to WAV format."""
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    return wav_buffer.getvalue()


def parse_range_header(range_header: str, file_size: int) -> tuple[int, int] | None:
    """
    Parse HTTP Range header and return (start, end) tuple.
    Returns None if the range is invalid.

    Example: "bytes=0-1023" -> (0, 1023)
    """
    if not range_header:
        return None

    try:
        # Parse "bytes=start-end" format
        if not range_header.startswith("bytes="):
            return None

        range_spec = range_header[6:]
        parts = range_spec.split("-")

        if len(parts) != 2:
            return None

        start_str, end_str = parts

        # Handle "bytes=start-" (from start to end of file)
        if start_str and not end_str:
            start = int(start_str)
            end = file_size - 1
        # Handle "bytes=-suffix" (last N bytes)
        elif not start_str and end_str:
            suffix_length = int(end_str)
            start = max(0, file_size - suffix_length)
            end = file_size - 1
        # Handle "bytes=start-end"
        else:
            start = int(start_str)
            end = int(end_str)

        # RFC 7233: start must be valid, end can exceed file size and gets clamped
        if start < 0 or start >= file_size or start > end:
            return None
        end = min(end, file_size - 1)
        return (start, end)
    except (ValueError, IndexError):
        return None


def precache_audio_file(
    uid: str,
    conversation_id: str,
    audio_file: dict[str, Any],
    fill_gaps: bool = True,
    caller: str = 'precache_endpoint',
) -> None:
    """Pre-cache a single audio file."""
    try:
        audio_file_id = audio_file.get('id')
        timestamps = audio_file.get('chunk_timestamps')
        if not audio_file_id or not timestamps:
            return

        get_or_create_merged_audio(
            uid=uid,
            conversation_id=conversation_id,
            audio_file_id=audio_file_id,
            timestamps=timestamps,
            pcm_to_wav_func=pcm_to_wav,
            fill_gaps=fill_gaps,
            sample_rate=AUDIO_SAMPLE_RATE,
            caller=caller,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error pre-caching audio file {audio_file.get('id')}: {e}")


def _run_parallel_precache(
    uid: str, conversation_id: str, audio_files: list[dict[str, Any]], caller: str, error_label: str
) -> None:
    futures: list[Any] = []
    for af in audio_files:
        _PRECACHE_FILE_SEM.acquire()
        try:
            f = submit_with_context(storage_executor, precache_audio_file, uid, conversation_id, af, caller=caller)
            f.add_done_callback(lambda _: _PRECACHE_FILE_SEM.release())
            futures.append(f)
        except Exception:
            _PRECACHE_FILE_SEM.release()
            raise
    for future in futures:
        try:
            future.result()
        except Exception as e:
            logger.error(f"Error in parallel {error_label}: {e}")


def precache_audio_files(uid: str, conversation_id: str, audio_files: list[dict[str, Any]]) -> dict[str, Any]:
    if not audio_files:
        return {"status": "no_audio", "message": "No audio files in conversation"}

    if is_audio_merge_dispatch_enabled():
        enqueue_conversation_audio_merge(uid, conversation_id, audio_files, caller='precache_endpoint')
        return {"status": "started", "audio_file_count": len(audio_files)}

    # Start background parallel pre-caching with bounded concurrency (#7387)
    def _precache_all_parallel():
        logger.info(f"Pre-caching all {len(audio_files)} audio files for conversation {conversation_id} (parallel)")
        _run_parallel_precache(uid, conversation_id, audio_files, caller='precache_endpoint', error_label='precache')
        logger.info(f"Completed pre-cache for conversation {conversation_id}")

    submit_with_context(postprocess_executor, _precache_all_parallel)

    return {"status": "started", "audio_file_count": len(audio_files)}


def _conversation_audio_urls_entry(
    uid: str, conversation_id: str, audio_files: list[dict[str, Any]], conversation: dict[str, Any] | None
) -> dict[str, Any]:
    """Conversation-level artifact entry for /urls.

    Cached only when the doc stamp's fingerprint matches the current audio_files
    AND the blob is servable; a mismatch (late chunks) or an expired blob (30-day
    lifecycle) falls through to pending + re-enqueue under a fingerprint-named
    task, making staleness self-healing.
    """
    fingerprint = compute_audio_files_fingerprint(audio_files)
    stamp = (conversation or {}).get('conversation_audio') or {}
    if stamp.get('audio_files_fingerprint') == fingerprint:
        signed_url = get_conversation_playback_signed_url(uid, conversation_id)
        if signed_url:
            return {
                "status": "cached",
                "signed_url": signed_url,
                "content_type": "audio/mpeg",
                "duration": stamp.get('duration'),
                "captured_duration": stamp.get('captured_duration'),
                "spans": stamp.get('spans', []),
            }
    if get_conversation_playback_unavailable_fingerprint(uid, conversation_id) == fingerprint:
        return {"status": "unavailable", "signed_url": None, "spans": []}
    enqueue_conversation_artifact_build(uid, conversation_id, fingerprint, caller='sync_urls')
    return {"status": "pending", "signed_url": None, "spans": []}


def _get_audio_urls_via_artifacts(
    uid: str,
    conversation_id: str,
    audio_files: list[dict[str, Any]],
    conversation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Artifact-backed /urls: a pure metadata read that never merges in-request.

    Cached = a playback MP3 artifact (or legacy unexpired WAV cache) exists.
    Everything else is reported pending and enqueued as an audio-merge task
    (named-task deduped); the app polls until cached.
    """
    result: list[dict[str, Any]] = []
    to_enqueue: list[dict[str, Any]] = []
    for af in audio_files:
        audio_file_id = af.get('id')
        if not audio_file_id:
            continue

        signed_url = get_playback_artifact_signed_url(uid, conversation_id, audio_file_id)
        content_type = 'audio/mpeg' if signed_url else None
        if not signed_url:
            signed_url = get_merged_audio_signed_url(uid, conversation_id, audio_file_id)
            content_type = 'audio/wav' if signed_url else None

        if signed_url:
            result.append(
                {
                    "id": audio_file_id,
                    "status": "cached",
                    "signed_url": signed_url,
                    "content_type": content_type,
                    "duration": af.get('duration', 0),
                }
            )
        elif is_playback_unavailable(uid, conversation_id, audio_file_id):
            result.append(
                {
                    "id": audio_file_id,
                    "status": "unavailable",
                    "signed_url": None,
                    "duration": af.get('duration', 0),
                }
            )
        else:
            result.append(
                {
                    "id": audio_file_id,
                    "status": "pending",
                    "signed_url": None,
                    "duration": af.get('duration', 0),
                }
            )
            to_enqueue.append(af)

    if to_enqueue:
        enqueue_conversation_audio_merge(uid, conversation_id, to_enqueue, caller='sync_urls')

    conversation_audio = _conversation_audio_urls_entry(uid, conversation_id, audio_files, conversation)

    return {
        "audio_files": result,
        "conversation_audio": conversation_audio,
        "poll_after_ms": (
            AUDIO_URLS_POLL_AFTER_MS if (to_enqueue or conversation_audio.get('status') == 'pending') else None
        ),
    }


def _get_audio_urls_inline(uid: str, conversation_id: str, audio_files: list[dict[str, Any]]) -> dict[str, Any]:
    result: list[dict[str, Any]] = []
    uncached_files: list[dict[str, Any]] = []
    first_uncached_handled = False

    for af in audio_files:
        audio_file_id = af.get('id')
        if not audio_file_id:
            continue

        signed_url = get_merged_audio_signed_url(uid, conversation_id, audio_file_id)

        if signed_url:
            result.append(
                {
                    "id": audio_file_id,
                    "status": "cached",
                    "signed_url": signed_url,
                    "duration": af.get('duration', 0),
                }
            )
        else:
            # First uncached file: cache synchronously for immediate playback
            if not first_uncached_handled:
                first_uncached_handled = True
                precache_audio_file(uid, conversation_id, af, caller='sync_urls_first')
                # Get signed URL after caching
                signed_url = get_merged_audio_signed_url(uid, conversation_id, audio_file_id)
                if signed_url:
                    result.append(
                        {
                            "id": audio_file_id,
                            "status": "cached",
                            "signed_url": signed_url,
                            "duration": af.get('duration', 0),
                        }
                    )
                else:
                    # Cache failed, return pending
                    result.append(
                        {
                            "id": audio_file_id,
                            "status": "pending",
                            "signed_url": None,
                            "duration": af.get('duration', 0),
                        }
                    )
            else:
                result.append(
                    {
                        "id": audio_file_id,
                        "status": "pending",
                        "signed_url": None,
                        "duration": af.get('duration', 0),
                    }
                )
                uncached_files.append(af)

    # Cache remaining files in background
    if uncached_files:

        def _cache_uncached_parallel():
            _run_parallel_precache(uid, conversation_id, uncached_files, caller='sync_urls_bg', error_label='cache')

        submit_with_context(postprocess_executor, _cache_uncached_parallel)

    return {"audio_files": result}


def get_audio_signed_urls(
    uid: str,
    conversation_id: str,
    audio_files: list[dict[str, Any]],
    conversation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not audio_files:
        return {"audio_files": []}

    if is_audio_merge_dispatch_enabled():
        return _get_audio_urls_via_artifacts(uid, conversation_id, audio_files, conversation)

    return _get_audio_urls_inline(uid, conversation_id, audio_files)


def _get_artifact_download_payload(
    uid: str, conversation_id: str, audio_file_id: str, audio_file: dict[str, Any]
) -> tuple[bytes, str, str] | None:
    # Artifact-backed mode: serve only prebuilt audio, never merge in-request. On
    # miss, enqueue the merge task and tell the client to poll /urls.
    audio_data = download_playback_artifact(uid, conversation_id, audio_file_id)
    if audio_data is not None:
        return audio_data, "audio/mpeg", "mp3"

    # Direct blob download: get_or_create_merged_audio would fall through to a
    # full inline merge for cached blobs missing expires_at metadata, violating
    # the no-merge guarantee.
    legacy_data = None
    if get_merged_audio_signed_url(uid, conversation_id, audio_file_id):
        legacy_data = download_legacy_merged_wav(uid, conversation_id, audio_file_id)
    if legacy_data is not None:
        return legacy_data, "audio/wav", "wav"

    enqueue_conversation_audio_merge(uid, conversation_id, [audio_file], caller='sync_download')
    return None


def _get_inline_download_payload(
    uid: str, conversation_id: str, audio_file_id: str, audio_file: dict[str, Any], format: str
) -> tuple[bytes, str, str]:
    if format == "wav":
        audio_data, _ = get_or_create_merged_audio(
            uid=uid,
            conversation_id=conversation_id,
            audio_file_id=audio_file_id,
            timestamps=audio_file['chunk_timestamps'],
            pcm_to_wav_func=pcm_to_wav,
            fill_gaps=True,
            sample_rate=AUDIO_SAMPLE_RATE,
            caller='sync_download',
        )
        return audio_data, "audio/wav", "wav"

    audio_data = download_audio_chunks_and_merge(
        uid, conversation_id, audio_file['chunk_timestamps'], fill_gaps=True, sample_rate=AUDIO_SAMPLE_RATE
    )
    return audio_data, "application/octet-stream", "pcm"


def _stream_audio_response(
    audio_data: bytes,
    content_type: str,
    extension: str,
    conversation_id: str,
    audio_file_id: str,
    range_header: str | None,
) -> Response:
    # Create descriptive filename
    filename = f"conversation_{conversation_id}_audio_{audio_file_id}.{extension}"
    file_size = len(audio_data)

    base_headers = {
        "Content-Disposition": f"attachment; filename={filename}",
        "Accept-Ranges": "bytes",
        "Cache-Control": "public, max-age=3600",
    }

    if range_header:
        # Parse the range request
        range_tuple = parse_range_header(range_header, file_size)

        if range_tuple is None:
            return Response(
                status_code=416,
                headers={
                    "Content-Range": f"bytes */{file_size}",
                    **base_headers,
                },
            )

        start, end = range_tuple
        content_length = end - start + 1

        # Return partial content
        return StreamingResponse(
            io.BytesIO(audio_data[start : end + 1]),
            status_code=206,
            media_type=content_type,
            headers={
                "Content-Length": str(content_length),
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                **base_headers,
            },
        )

    return StreamingResponse(
        io.BytesIO(audio_data),
        status_code=200,
        media_type=content_type,
        headers={
            "Content-Length": str(file_size),
            **base_headers,
        },
    )


def download_audio_file_response(
    uid: str,
    conversation_id: str,
    audio_file_id: str,
    audio_file: dict[str, Any],
    request: Request,
    format: str,
) -> Response:
    try:
        if not audio_file.get('chunk_timestamps'):
            raise HTTPException(status_code=500, detail="Audio file has no chunk timestamps")

        if format == "wav" and is_audio_merge_dispatch_enabled():
            payload = _get_artifact_download_payload(uid, conversation_id, audio_file_id, audio_file)
            if payload is None:
                return JSONResponse(
                    status_code=202,
                    content={"status": "pending", "poll_after_ms": AUDIO_URLS_POLL_AFTER_MS},
                )
            audio_data, content_type, extension = payload
        else:
            audio_data, content_type, extension = _get_inline_download_payload(
                uid, conversation_id, audio_file_id, audio_file, format
            )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Audio chunks not found in storage")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading audio file: {e}")
        raise HTTPException(status_code=500, detail="Failed to download audio file")

    return _stream_audio_response(
        audio_data, content_type, extension, conversation_id, audio_file_id, request.headers.get("Range")
    )


def build_playback_artifact(uid: str, conversation_id: str, timestamps: list[float]) -> bytes:
    """Merge chunks (download -> decrypt -> decode -> gap-fill) and encode MP3 ~48kbps mono."""
    pcm_data = download_audio_chunks_and_merge(
        uid, conversation_id, timestamps, fill_gaps=True, sample_rate=AUDIO_SAMPLE_RATE
    )
    if not pcm_data:
        return b''
    segment = AudioSegment(data=pcm_data, sample_width=2, frame_rate=AUDIO_SAMPLE_RATE, channels=1)
    del pcm_data
    buf = io.BytesIO()
    segment.export(buf, format='mp3', bitrate='48k')  # type: ignore[reportUnknownMemberType]  # pydub untyped
    return buf.getvalue()


# PCM16 mono at AUDIO_SAMPLE_RATE: 2 bytes per sample.
_PCM_BYTES_PER_SECOND = AUDIO_SAMPLE_RATE * 2


def build_conversation_playback_artifact(
    uid: str, conversation_id: str, audio_files: list[dict], started_at_ts: float
) -> tuple[bytes, list[dict]]:
    """One dense CBR MP3 for the whole conversation + spans manifest.

    Captured audio only: intra-part gaps (<90s) stay silence-filled exactly as
    the per-part artifacts do (fill_gaps=True per part); the >90s inter-part
    gaps are collapsed by concatenation. Each part becomes one span with
    wall_offset relative to started_at_ts (TranscriptSegment.start basis).

    Parts whose chunks are all gone are skipped; raises FileNotFoundError only
    if nothing is buildable. Parts are processed sequentially to bound memory.
    """
    parts = sorted(
        [af for af in audio_files if af.get('id') and af.get('chunk_timestamps')],
        key=lambda af: min(af['chunk_timestamps']),
    )
    pcm_buf = bytearray()
    spans: list[dict] = []
    for af in parts:
        timestamps = sorted(af['chunk_timestamps'])
        try:
            pcm = download_audio_chunks_and_merge(
                uid, conversation_id, timestamps, fill_gaps=True, sample_rate=AUDIO_SAMPLE_RATE
            )
        except FileNotFoundError:
            logger.warning(f'conversation_artifact: part {af["id"]} has no chunks, skipping conv={conversation_id}')
            continue
        if not pcm:
            continue
        spans.append(
            {
                'file_id': af['id'],
                'wall_offset': round(timestamps[0] - started_at_ts, 3),
                'artifact_offset': round(len(pcm_buf) / _PCM_BYTES_PER_SECOND, 3),
                'len': round(len(pcm) / _PCM_BYTES_PER_SECOND, 3),
            }
        )
        pcm_buf.extend(pcm)
        del pcm
    if not pcm_buf:
        raise FileNotFoundError(f'No chunks found for conversation {conversation_id}')
    segment = AudioSegment(data=bytes(pcm_buf), sample_width=2, frame_rate=AUDIO_SAMPLE_RATE, channels=1)
    del pcm_buf
    buf = io.BytesIO()
    segment.export(buf, format='mp3', bitrate='48k')  # type: ignore[reportUnknownMemberType]  # pydub untyped
    del segment
    return buf.getvalue(), spans
