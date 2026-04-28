import hashlib
from typing import Any, Dict, List

import omi_client
import storage
from models import FallbackSegmentIn, FallbackSegmentsRequest


def dedupe_key(omi_user_id: str, device_id: str, session_id: str, segment: FallbackSegmentIn) -> str:
    normalized_text = " ".join(segment.text.lower().strip().split())
    raw = "|".join(
        [
            omi_user_id,
            device_id,
            session_id,
            segment.source,
            normalized_text,
            segment.start.isoformat(),
            segment.end.isoformat(),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def ingest_fallback_segments(request: FallbackSegmentsRequest) -> Dict[str, Any]:
    inserted: List[int] = []
    skipped = 0
    for segment in request.segments:
        if not segment.text.strip() and segment.source != "gap_marker":
            skipped += 1
            continue
        data = {
            "omi_user_id": request.omi_user_id,
            "device_id": request.device_id,
            "session_id": request.session_id,
            "text": segment.text.strip(),
            "source": segment.source,
            "start": segment.start.isoformat(),
            "end": segment.end.isoformat(),
            "confidence": segment.confidence,
            "health_state": segment.health_state,
            "raw_audio_available": segment.raw_audio_available,
            "foreground_app": segment.foreground_app,
            "metadata": {
                "fallback_source": segment.source,
                "degraded": True,
                "health_state": segment.health_state,
                "raw_audio_available": segment.raw_audio_available,
                "foreground_app": segment.foreground_app,
            },
            "dedupe_key": dedupe_key(request.omi_user_id, request.device_id, request.session_id, segment),
        }
        if storage.store_fallback_segment(data):
            inserted.append(len(inserted))
        else:
            skipped += 1

    queued = omi_client.queue_fallback_import(request)
    storage.audit(
        request.omi_user_id,
        request.device_id,
        "fallback_segments_ingested",
        {"inserted": len(inserted), "skipped": skipped, "queued_for_omi": queued},
    )
    return {"status": "ok", "inserted": len(inserted), "skipped": skipped, "queued_for_omi": queued}
