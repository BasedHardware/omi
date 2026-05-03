import os
from typing import Any, Dict, Optional

import requests

from models import FallbackSegmentsRequest

OMI_API_BASE_URL = os.getenv("OMI_API_BASE_URL", "").rstrip("/")
OMI_API_KEY = os.getenv("OMI_API_KEY") or os.getenv("OMI_APP_SECRET")


def _headers() -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if OMI_API_KEY:
        headers["Authorization"] = f"Bearer {OMI_API_KEY}"
    return headers


def queue_fallback_import(request: FallbackSegmentsRequest) -> bool:
    if not OMI_API_BASE_URL:
        return False
    url = f"{OMI_API_BASE_URL}/v1/ambient-capture/fallback-segments"
    body = {
        "device_id": request.device_id,
        "segments": [
            {
                "text": segment.text,
                "source": segment.source,
                "start": segment.start.isoformat(),
                "end": segment.end.isoformat(),
                "confidence": segment.confidence,
                "health_state": segment.health_state,
                "foreground_app_package": segment.foreground_app,
                "raw_audio_available": segment.raw_audio_available,
            }
            for segment in request.segments
        ],
    }
    try:
        response = requests.post(url, json=body, headers=_headers(), timeout=10)
        return response.status_code < 300
    except requests.RequestException:
        return False


def create_omi_task(task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not OMI_API_BASE_URL:
        return None
    try:
        response = requests.post(f"{OMI_API_BASE_URL}/v1/tasks", json=task, headers=_headers(), timeout=10)
        if response.status_code < 300:
            return response.json()
    except requests.RequestException:
        return None
    return None


def sync_audio_spool(
    omi_user_id: str,
    filename: str,
    audio_bytes: bytes,
    conversation_id: Optional[str] = None,
) -> Dict[str, Any]:
    if not OMI_API_BASE_URL:
        return {"imported": False, "reason": "omi_api_base_url_missing"}
    params = {}
    if conversation_id:
        params["conversation_id"] = conversation_id
    headers = {}
    if OMI_API_KEY:
        headers["Authorization"] = f"Bearer {OMI_API_KEY}"
    files = {"files": (filename, audio_bytes, "application/octet-stream")}
    try:
        response = requests.post(
            f"{OMI_API_BASE_URL}/v1/sync-local-files",
            params=params,
            files=files,
            headers=headers,
            timeout=120,
        )
        if response.status_code < 300:
            data = response.json()
            conversation_ids = list(data.get("new_memories") or data.get("updated_memories") or [])
            return {
                "imported": True,
                "conversation_id": conversation_ids[0] if conversation_ids else None,
                "status_code": response.status_code,
                "response": data,
            }
        return {
            "imported": False,
            "reason": f"omi_http_{response.status_code}",
            "status_code": response.status_code,
            "body": response.text[:500],
        }
    except requests.RequestException as exc:
        return {"imported": False, "reason": "omi_request_failed", "error": str(exc)}
