from typing import Any, Dict

from fastapi import HTTPException

import storage
from models import TelemetryIn

FORBIDDEN_TELEMETRY_FIELDS = {"audio", "raw_audio", "pcm", "payload"}
TEXT_FIELDS = {"text", "transcript", "caption", "segments"}


def ingest_telemetry(event: TelemetryIn) -> Dict[str, Any]:
    settings = storage.get_settings(event.omi_user_id)
    metadata_keys = set(event.metadata.keys())
    forbidden = metadata_keys.intersection(FORBIDDEN_TELEMETRY_FIELDS)
    if forbidden:
        raise HTTPException(status_code=422, detail=f"telemetry cannot include {', '.join(sorted(forbidden))}")
    if not settings.allow_telemetry_text:
        text_fields = metadata_keys.intersection(TEXT_FIELDS)
        if text_fields:
            raise HTTPException(status_code=422, detail=f"telemetry text disabled: {', '.join(sorted(text_fields))}")
    storage.store_telemetry(event.model_dump(mode="json"))
    return {"status": "ok"}
