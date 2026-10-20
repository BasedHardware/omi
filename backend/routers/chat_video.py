"""Chat video attachments: device-sampled frames, and the clip branch of /v2/files.

A video is read as stills plus speech (utils/media/video_frames.py); the clip is never stored.
"""

import json
import math
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from models.chat import FileChat
from utils.media import video_upload
from utils.multipart import MultipartLimits, MultipartMaxPartSizeRoute, max_part_size, multipart_limits
from utils.other import endpoints as auth

router = APIRouter(route_class=MultipartMaxPartSizeRoute)

_VIDEO_SUFFIXES = {'.mp4', '.mov', '.m4v', '.webm', '.mkv', '.avi', '.3gp'}
MB = 1024 * 1024
MAX_VIDEO_FRAME_BYTES = MB // 2
MAX_VIDEO_AUDIO_BYTES = 20 * MB
# Parsed before auth: at most 48 frames + audio, three form fields, and Cloud Run's body cap.
VIDEO_FRAMES_LIMITS = MultipartLimits(max_files=video_upload.MAX_CANDIDATES + 1, max_fields=3, max_body_size=32 * MB)


def is_video_upload(name: str, content_type: Optional[str]) -> bool:
    return Path(name).suffix.lower() in _VIDEO_SUFFIXES or (content_type or '').lower().startswith('video/')


def store_uploaded_clip(uid: str, path: Path, name: str) -> FileChat:
    """A whole clip sent to /v2/files: sampled here, stored as its sheet + filmstrip."""
    try:
        return FileChat(**video_upload.video_from_file(uid, path, name))
    except video_upload.VideoFramesError:
        raise HTTPException(status_code=400, detail=video_upload.VIDEO_UNREADABLE)


def _frame_times(raw: str, count: int) -> List[float]:
    """One finite, non-negative number of seconds per frame, or a 400."""
    try:
        values = json.loads(raw)
        times = [float(t) for t in values if isinstance(t, (int, float)) and not isinstance(t, bool)]
    except (ValueError, TypeError, OverflowError, RecursionError):
        raise HTTPException(status_code=400, detail='frame_times must be a JSON array of seconds')
    if not isinstance(values, list) or len(times) != len(values) or len(times) != count:
        raise HTTPException(status_code=400, detail='frame_times must list one time per frame')
    if not all(math.isfinite(t) and 0 <= t <= 36000 for t in times):
        raise HTTPException(status_code=400, detail='frame_times must be seconds within the clip')
    return times


@router.post('/v2/files/video', response_model=List[FileChat], tags=['chat'])
@max_part_size(MAX_VIDEO_AUDIO_BYTES)
@multipart_limits(VIDEO_FRAMES_LIMITS)
def upload_video_frames_chat(
    frames: List[UploadFile] = File(
        ..., description='JPEG or PNG stills sampled from the clip, in time order (at most 48).'
    ),
    frame_times: str = Form(..., max_length=4096, description="JSON array of each frame's time in seconds."),
    duration_seconds: float = Form(..., ge=0, le=36000),
    name: str = Form('video.mov', max_length=255),
    audio: Optional[UploadFile] = File(None, description="The clip's audio track (m4a/aac/ogg), for its transcript."),
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "file:upload")),
):
    """A video the client sampled on device: stills (and audio) instead of the whole clip.

    Same result as uploading the clip to /v2/files: one chat file whose image is a numbered
    contact sheet of the clip's most distinct frames.
    """
    times = _frame_times(frame_times, len(frames))
    if len(frames) > video_upload.MAX_CANDIDATES:
        raise HTTPException(status_code=400, detail=f'Send at most {video_upload.MAX_CANDIDATES} frames')
    blobs = []
    for frame in frames:
        blob = frame.file.read(MAX_VIDEO_FRAME_BYTES + 1)
        if len(blob) > MAX_VIDEO_FRAME_BYTES:
            raise HTTPException(status_code=400, detail='Each frame must be 512 KB or smaller')
        blobs.append(blob)
    safe_name = Path(name).name or 'video.mov'
    audio_path = None
    try:
        if audio is not None:
            audio_path = Path(tempfile.gettempdir()) / f"{uuid.uuid4().hex}_audio"
            with audio_path.open("wb") as buffer:
                shutil.copyfileobj(audio.file, buffer)
        try:
            row = video_upload.video_from_frames(uid, safe_name, blobs, times, duration_seconds, audio_path)
        except video_upload.VideoFramesError:
            raise HTTPException(status_code=400, detail=video_upload.VIDEO_UNREADABLE)
    finally:
        if audio_path is not None:
            audio_path.unlink(missing_ok=True)
    return [FileChat(**row).client_dump()]
