import base64
import hashlib
import re
import struct
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import HTTPException

import omi_client
import policy
import storage
from models import AudioSpoolUploadRequest, PLUGIN_ID

AUDIO_DIR = Path(__file__).with_name("audio_spool_uploads")
MAX_AUDIO_BYTES = 200 * 1024 * 1024
FILENAME_RE = re.compile(r"^ambient_android_pcm16_16000_1_[0-9]{10,17}_[0-9]+\.bin$")


def ingest_audio_spool(
    request: AudioSpoolUploadRequest,
    authorization: Optional[str],
    app_id: str,
) -> Dict[str, Any]:
    policy.authenticate_device(request.omi_user_id, request.device_id, app_id or PLUGIN_ID, authorization)
    if request.sample_rate != 16000 or request.channels != 1 or request.codec != "pcm16":
        raise HTTPException(status_code=422, detail="unsupported_audio_format")
    if not FILENAME_RE.match(request.filename):
        raise HTTPException(status_code=422, detail="invalid_audio_filename")

    try:
        audio_bytes = base64.b64decode(request.audio_base64, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="invalid_audio_base64") from exc
    if not audio_bytes:
        raise HTTPException(status_code=422, detail="empty_audio")
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="audio_spool_too_large")

    frame_count, pcm_bytes = inspect_length_prefixed_pcm(audio_bytes)
    if frame_count == 0 or pcm_bytes == 0:
        raise HTTPException(status_code=422, detail="invalid_length_prefixed_pcm")

    path = write_audio_file(request, audio_bytes)
    dedupe_key = spool_dedupe_key(request, audio_bytes)
    import_result = omi_client.sync_audio_spool(
        request.omi_user_id,
        request.filename,
        audio_bytes,
        conversation_id=None,
    )
    imported = bool(import_result.get("imported"))
    status = "imported" if imported else "stored"
    inserted = storage.store_audio_spool(
        {
            "omi_user_id": request.omi_user_id,
            "device_id": request.device_id,
            "session_id": request.session_id,
            "filename": request.filename,
            "file_path": str(path),
            "bytes": len(audio_bytes),
            "duration_estimate": request.duration_estimate,
            "sample_rate": request.sample_rate,
            "channels": request.channels,
            "codec": request.codec,
            "status": status,
            "omi_conversation_id": import_result.get("conversation_id"),
            "metadata": {
                **request.metadata,
                "format": request.format,
                "frame_count": frame_count,
                "pcm_bytes": pcm_bytes,
                "source": "omi_ambient_companion",
                "degraded": False,
            },
            "dedupe_key": dedupe_key,
            "imported_at": storage.now_iso() if imported else None,
        }
    )
    storage.audit(
        request.omi_user_id,
        request.device_id,
        "audio_spool_ingested",
        {
            "session_id": request.session_id,
            "bytes": len(audio_bytes),
            "frame_count": frame_count,
            "inserted": inserted,
            "status": status,
            "omi_import": import_result,
        },
    )
    return {
        "status": "ok",
        "inserted": inserted,
        "imported": imported,
        "conversation_id": import_result.get("conversation_id"),
        "frames": frame_count,
        "bytes": len(audio_bytes),
    }


def inspect_length_prefixed_pcm(data: bytes) -> tuple[int, int]:
    offset = 0
    frame_count = 0
    pcm_bytes = 0
    while offset + 4 <= len(data):
        frame_len = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        if frame_len <= 0 or frame_len > 65536:
            return 0, 0
        if offset + frame_len > len(data):
            return 0, 0
        frame_count += 1
        pcm_bytes += frame_len
        offset += frame_len
    if offset != len(data):
        return 0, 0
    return frame_count, pcm_bytes


def write_audio_file(request: AudioSpoolUploadRequest, audio_bytes: bytes) -> Path:
    safe_user = hashlib.sha256(request.omi_user_id.encode("utf-8")).hexdigest()[:16]
    directory = AUDIO_DIR / safe_user / request.device_id.replace("/", "_")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / request.filename
    path.write_bytes(audio_bytes)
    return path


def spool_dedupe_key(request: AudioSpoolUploadRequest, audio_bytes: bytes) -> str:
    digest = hashlib.sha256(audio_bytes).hexdigest()
    raw = "|".join([request.omi_user_id, request.device_id, request.session_id, request.filename, digest])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
