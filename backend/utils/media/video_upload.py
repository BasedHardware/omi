"""Chat video attachments: a clip, or frames a client sampled, become one FileChat row.

Shared by the in-app upload routes and the messaging channels. The stored chat file is the
overview contact sheet (an ordinary image to every reader); ``FileChat.video`` carries the
frame times, the filmstrip for closer looks, and the encrypted transcript.
"""

from __future__ import annotations

import logging
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Sequence
from uuid import uuid4

from utils.media.video_frames import MAX_CANDIDATES, VideoDigest, VideoFramesError, digest_frames, digest_video

logger = logging.getLogger(__name__)

# In-app uploads are sync routes; their STT runs here so concurrent uploads on one instance
# share a small bound instead of each starting its own thread.
_STT_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix='chat-video-stt')

VIDEO_UNREADABLE = "Couldn't read that video. Try a different clip, or send a screenshot."


def store_video(uid: str, name: str, digest: VideoDigest, transcript: str) -> Dict[str, Any]:
    """Upload the sheet and filmstrip, save the FileChat row, and return it (with ``size``)."""
    from database import chat
    from models.chat import FileChat
    from utils.other import storage
    from utils.other.chat_file import FileChatTool

    with tempfile.TemporaryDirectory(prefix='omi-chat-video-') as directory:
        result = FileChatTool.upload_video(directory, name, digest, transcript, uid)
        thumb = result.get('thumbnail')
        urls = storage.upload_multi_chat_files([thumb], uid) if thumb else {}
        row = FileChat(
            id=str(uuid4()),
            name=result['file_name'],
            mime_type=result['mime_type'],
            openai_file_id=result['file_id'],
            created_at=datetime.now(timezone.utc),
            thumbnail=urls.get(str(thumb), ''),
            video=result['video'],
        ).model_dump()
    row['size'] = len(digest.sheet)
    chat.add_multi_files(uid, [row])
    return row


def _transcribe_file(path: Path, uid: str) -> str:
    """Speech in the clip, or '' when there is none (a muted video note) or STT fails."""
    from utils.messaging.adapters.media import ChatMediaStore, MediaPreparationError, decode_audio_file

    try:
        return ChatMediaStore().transcribe_pcm(decode_audio_file(path), uid)
    except MediaPreparationError:
        return ''


def video_from_file(uid: str, path: Path, name: str) -> Dict[str, Any]:
    """An uploaded clip: frames and speech in parallel, then the stored row.

    Raises VideoFramesError when the clip has no decodable picture.
    """
    speech = _STT_POOL.submit(_transcribe_file, path, uid)
    try:
        digest = digest_video(path.read_bytes())
    except BaseException:
        speech.cancel()
        raise
    return store_video(uid, name, digest, speech.result())


def video_from_frames(
    uid: str,
    name: str,
    frames: Sequence[bytes],
    times: Sequence[float],
    duration: float,
    audio_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Frames (and optionally the audio track) a client sampled on device."""
    speech = _STT_POOL.submit(_transcribe_file, audio_path, uid) if audio_path else None
    try:
        digest = digest_frames(frames, times, duration)
    except BaseException:
        if speech:
            speech.cancel()
        raise
    return store_video(uid, name, digest, speech.result() if speech else '')


__all__ = [
    'MAX_CANDIDATES',
    'VIDEO_UNREADABLE',
    'VideoFramesError',
    'store_video',
    'video_from_file',
    'video_from_frames',
]
