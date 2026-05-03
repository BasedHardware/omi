import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException

import security
import storage
from models import CapturePolicyPayload, CaptureSettings, PLUGIN_ID, POLICY_SCOPE, SignedPolicy

POLICY_VALIDITY_MINUTES = 10


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def authenticate_device(
    omi_user_id: str,
    device_id: str,
    app_id: str,
    authorization: Optional[str],
) -> Dict[str, Any]:
    if app_id != os.getenv("AMBIENT_PLUGIN_ID", PLUGIN_ID):
        raise HTTPException(status_code=403, detail="wrong_app_id")
    device = storage.get_device(omi_user_id, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="device_not_registered")
    if device["revoked"]:
        raise HTTPException(status_code=403, detail="device_revoked")
    expected = f"Bearer {device['device_token']}"
    if authorization and authorization != expected:
        raise HTTPException(status_code=401, detail="invalid_device_token")
    if not authorization:
        raise HTTPException(status_code=401, detail="missing_device_token")
    return device


def build_policy_payload(omi_user_id: str, device_id: str, settings: CaptureSettings, sequence: int) -> Dict[str, Any]:
    issued_at = utc_now()
    capture_enabled = settings.advanced_capture_enabled and settings.default_capture_mode != "off"
    capture_mode = settings.default_capture_mode if capture_enabled else "off"
    payload = CapturePolicyPayload(
        version=1,
        plugin_id=os.getenv("AMBIENT_PLUGIN_ID", PLUGIN_ID),
        scope=POLICY_SCOPE,
        user_id=omi_user_id,
        device_id=device_id,
        sequence=sequence,
        issued_at=issued_at,
        valid_until=issued_at + timedelta(minutes=POLICY_VALIDITY_MINUTES),
        capture_mode=capture_mode,
        sensitivity=settings.sensitivity,
        silence_detection_seconds=settings.silence_detection_seconds,
        rms_silence_dbfs_threshold=settings.rms_silence_dbfs_threshold,
        zero_frame_threshold=settings.zero_frame_threshold,
        allow_foreground_mic=capture_enabled,
        allow_accessibility_mode=settings.allow_accessibility_mode,
        allow_local_stt_fallback=settings.allow_local_stt_fallback,
        allow_caption_fallback=settings.allow_accessibility_mode and settings.allow_caption_fallback,
        allow_audio_upload=settings.allow_audio_upload,
        allow_transcript_upload=settings.allow_transcript_upload,
        raw_audio_retention=settings.raw_audio_retention,
        communication_mode=settings.communication_mode,
        high_risk_apps=settings.high_risk_apps,
        notification_aggressiveness=settings.notification_aggressiveness,
        audit_level=settings.audit_level,
    )
    data = payload.model_dump(mode="json")
    data["issued_at"] = iso_z(payload.issued_at)
    data["valid_until"] = iso_z(payload.valid_until)
    return data


def issue_current_policy(
    omi_user_id: str,
    device_id: str,
    authorization: Optional[str],
    app_id: str,
    last_sequence: Optional[int] = None,
) -> SignedPolicy:
    device = authenticate_device(omi_user_id, device_id, app_id, authorization)
    current_sequence = int(device["policy_sequence"])
    if last_sequence is not None and last_sequence < current_sequence:
        storage.audit(omi_user_id, device_id, "policy_sequence_hint_stale", {"last_sequence": last_sequence})
    sequence = storage.next_policy_sequence(omi_user_id, device_id)
    settings = storage.get_settings(omi_user_id)
    payload = build_policy_payload(omi_user_id, device_id, settings, sequence)
    payload_json, signature = security.sign_payload(payload)
    storage.store_policy(omi_user_id, device_id, sequence, payload, signature)
    return SignedPolicy(
        payload=CapturePolicyPayload.model_validate(json.loads(payload_json)),
        payload_json=payload_json,
        signature=signature,
        key_id=security.get_key_id(),
        public_key=security.get_public_key_b64(),
    )


def policy_status(omi_user_id: str, device_id: Optional[str] = None) -> Dict[str, Any]:
    settings = storage.get_settings(omi_user_id)
    device = storage.get_device(omi_user_id, device_id) if device_id else None
    return {
        "capture_mode": settings.default_capture_mode if settings.advanced_capture_enabled else "off",
        "sensitivity": settings.sensitivity,
        "communication_mode": settings.communication_mode,
        "device": device,
    }
