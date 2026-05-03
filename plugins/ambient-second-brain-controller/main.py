import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import Body, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse

import accountability
import audio_spool
import fallback_segments
import integrations
import policy
import security
import storage
import task_extraction
import telemetry
from models import (
    AccountabilityRuleIn,
    AccountabilityRuleUpdate,
    CaptureSettings,
    ChatToolCall,
    DeviceRegisterRequest,
    DeviceRegisterResponse,
    AudioSpoolUploadRequest,
    DeviceRevokeRequest,
    FallbackSegmentsRequest,
    OmiWebhookPayload,
    PLUGIN_ID,
    TelemetryIn,
)

load_dotenv()

app = FastAPI(
    title="Ambient Second Brain Controller",
    description="Signed policy controller for Omi Advanced Ambient Capture.",
    version="0.1.0",
)


@app.on_event("startup")
def startup():
    storage.init_db()


def base_url() -> str:
    return os.getenv("WEBHOOK_BASE_URL", "http://localhost:8000").rstrip("/")


@app.get("/healthz")
def healthz():
    return {"status": "ok", "plugin_id": os.getenv("AMBIENT_PLUGIN_ID", PLUGIN_ID)}


@app.get("/readyz")
def readyz():
    try:
        storage.init_db()
        public_key = security.get_public_key_b64()
        return {
            "status": "ready",
            "base_url": base_url(),
            "key_id": security.get_key_id(),
            "key_fingerprint": security.key_fingerprint(public_key),
            "omi_import_configured": bool(os.getenv("OMI_API_KEY") or os.getenv("OMI_APP_SECRET")),
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"not_ready:{exc.__class__.__name__}") from exc


@app.get("/", response_class=HTMLResponse)
def app_home(omi_user_id: Optional[str] = Query(default=None), device_id: Optional[str] = Query(default=None)):
    user = omi_user_id or "demo"
    settings = storage.get_settings(user)
    audit = storage.get_audit_log(user, limit=20)
    status = policy.policy_status(user, device_id)
    return f"""
    <html>
      <head><title>Ambient Second Brain Controller</title></head>
      <body style="font-family: system-ui; max-width: 920px; margin: 32px auto; line-height: 1.45">
        <h1>Ambient Second Brain Controller</h1>
        <p>This plugin never records audio. It only issues signed, short-lived capture policies.</p>
        <h2>Device Status</h2>
        <pre>{status}</pre>
        <h2>Current Settings</h2>
        <pre>{settings.model_dump_json(indent=2)}</pre>
        <h2>Controls</h2>
        <p>Use <code>POST /settings</code> or Omi chat tools to change capture mode, sensitivity,
        communication mode, fallback settings, retention, and accountability rules.</p>
        <h2>Audit Log</h2>
        <pre>{audit}</pre>
      </body>
    </html>
    """


@app.get("/.well-known/ambient-controller.json")
def ambient_controller_manifest():
    public_key = security.get_public_key_b64()
    return {
        "plugin_id": os.getenv("AMBIENT_PLUGIN_ID", PLUGIN_ID),
        "name": "Ambient Second Brain Controller",
        "base_url": base_url(),
        "policy_url": f"{base_url()}/capture/policy/current",
        "telemetry_url": f"{base_url()}/capture/telemetry",
        "fallback_segments_url": f"{base_url()}/capture/fallback-segments",
        "audio_spool_url": f"{base_url()}/capture/audio-spool",
        "public_key": public_key,
        "key_id": security.get_key_id(),
        "key_fingerprint": security.key_fingerprint(public_key),
    }


@app.get("/.well-known/omi-app-registration.json")
def omi_app_registration_manifest():
    public_key = security.get_public_key_b64()
    return {
        "id": os.getenv("AMBIENT_PLUGIN_ID", PLUGIN_ID),
        "name": "Ambient Second Brain Controller",
        "description": "Issues signed ambient capture policies and extracts tasks, reminders, commitments, and accountability prompts from Omi conversations.",
        "capabilities": ["ambient_capture_controller", "chat_tools", "external_integration"],
        "app_home_url": f"{base_url()}/",
        "webhook_url": f"{base_url()}/webhooks/omi/transcript-processed",
        "chat_tools_url": f"{base_url()}/.well-known/omi-tools.json",
        "external_integration": {
            "capture_policy_url": f"{base_url()}/capture/policy/current",
            "capture_telemetry_url": f"{base_url()}/capture/telemetry",
            "fallback_segments_url": f"{base_url()}/capture/fallback-segments",
            "capture_controller_public_key": public_key,
            "capture_controller_key_id": security.get_key_id(),
            "capture_controller_scopes": ["ambient_capture_controller"],
        },
    }


@app.get("/.well-known/omi-tools.json")
def omi_tools_manifest():
    tool_names = [
        "get_capture_status",
        "set_capture_mode",
        "set_capture_sensitivity",
        "set_communication_mode",
        "set_fallback_settings",
        "set_retention_policy",
        "toggle_private_mode",
        "pause_capture",
        "resume_capture",
        "stop_capture",
        "get_audit_log",
        "create_accountability_rule",
        "list_accountability_rules",
        "update_accountability_rule",
        "delete_accountability_rule",
    ]
    return {
        "schema_version": "2026-04-28",
        "plugin_id": os.getenv("AMBIENT_PLUGIN_ID", PLUGIN_ID),
        "name": "Ambient Second Brain Controller",
        "app_home_url": base_url(),
        "tools": [
            {
                "name": name,
                "description": f"Ambient capture controller tool: {name.replace('_', ' ')}.",
                "input_schema": {"type": "object", "additionalProperties": True},
                "endpoint": f"{base_url()}/tools/{name}",
            }
            for name in tool_names
        ],
    }


@app.post("/device/register", response_model=DeviceRegisterResponse)
def register_device(request: DeviceRegisterRequest):
    token = storage.register_device(request.model_dump(mode="json"))
    settings = storage.ensure_default_settings_for_registration(request.omi_user_id)
    public_key = security.get_public_key_b64()
    storage.audit(
        request.omi_user_id,
        request.device_id,
        "controller_registered",
        {"plugin_id": os.getenv("AMBIENT_PLUGIN_ID", PLUGIN_ID)},
    )
    storage.audit(request.omi_user_id, request.device_id, "controller_key_pinned", {"key_id": security.get_key_id()})
    storage.audit(
        request.omi_user_id,
        request.device_id,
        "registration_settings_ready",
        {"capture_mode": settings.default_capture_mode, "advanced_capture_enabled": settings.advanced_capture_enabled},
    )
    return DeviceRegisterResponse(
        device_registered=True,
        policy_url=f"{base_url()}/capture/policy/current",
        telemetry_url=f"{base_url()}/capture/telemetry",
        fallback_segments_url=f"{base_url()}/capture/fallback-segments",
        audio_spool_url=f"{base_url()}/capture/audio-spool",
        plugin_public_key=public_key,
        key_id=security.get_key_id(),
        key_fingerprint=security.key_fingerprint(public_key),
        device_token=token,
    )


@app.post("/device/revoke")
def revoke_device(request: DeviceRevokeRequest):
    revoked = storage.revoke_device(request.omi_user_id, request.device_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="device_not_found")
    return {"revoked": True}


@app.get("/capture/policy/current")
def current_policy(
    authorization: Optional[str] = Header(default=None),
    x_omi_user_id: str = Header(alias="X-Omi-User-Id"),
    x_omi_device_id: str = Header(alias="X-Omi-Device-Id"),
    x_omi_app_id: str = Header(alias="X-Omi-App-Id"),
    x_last_policy_sequence: Optional[int] = Header(default=None, alias="X-Last-Policy-Sequence"),
):
    signed = policy.issue_current_policy(
        x_omi_user_id,
        x_omi_device_id,
        authorization,
        x_omi_app_id,
        last_sequence=x_last_policy_sequence,
    )
    return {
        "payload": signed.payload_json,
        "structured_payload": signed.payload.model_dump(mode="json"),
        "signature": signed.signature,
        "alg": signed.alg,
        "key_id": signed.key_id,
        "public_key": signed.public_key,
    }


@app.post("/capture/telemetry")
def capture_telemetry(
    event: TelemetryIn,
    authorization: Optional[str] = Header(default=None),
    x_omi_app_id: str = Header(default=PLUGIN_ID, alias="X-Omi-App-Id"),
):
    policy.authenticate_device(event.omi_user_id, event.device_id, x_omi_app_id, authorization)
    return telemetry.ingest_telemetry(event)


@app.post("/capture/fallback-segments")
def capture_fallback_segments(
    request: FallbackSegmentsRequest,
    authorization: Optional[str] = Header(default=None),
    x_omi_app_id: str = Header(default=PLUGIN_ID, alias="X-Omi-App-Id"),
):
    policy.authenticate_device(request.omi_user_id, request.device_id, x_omi_app_id, authorization)
    return fallback_segments.ingest_fallback_segments(request)


@app.post("/capture/audio-spool")
def capture_audio_spool(
    request: AudioSpoolUploadRequest,
    authorization: Optional[str] = Header(default=None),
    x_omi_app_id: str = Header(default=PLUGIN_ID, alias="X-Omi-App-Id"),
):
    return audio_spool.ingest_audio_spool(request, authorization, x_omi_app_id)


@app.get("/settings")
def get_settings(omi_user_id: str = Query(...)):
    return storage.get_settings(omi_user_id).model_dump(mode="json")


@app.post("/settings")
def update_settings(payload: Dict[str, Any] = Body(...)):
    omi_user_id = payload.pop("omi_user_id", None)
    if not omi_user_id:
        raise HTTPException(status_code=422, detail="omi_user_id required")
    current = storage.get_settings(omi_user_id).model_dump(mode="json")
    current.update(payload)
    settings = storage.save_settings(omi_user_id, current)
    return settings.model_dump(mode="json")


@app.post("/webhooks/omi/memory-created")
def memory_created(payload: OmiWebhookPayload):
    return _process_omi_webhook(payload)


@app.post("/webhooks/omi/transcript-processed")
def transcript_processed(payload: OmiWebhookPayload):
    return _process_omi_webhook(payload)


@app.post("/webhooks/omi/audio-bytes")
def audio_bytes_webhook(payload: Dict[str, Any]):
    storage.audit(payload.get("omi_user_id") or payload.get("user_id"), None, "audio_bytes_webhook_ignored", {})
    return {"status": "ignored", "reason": "use /capture/audio-spool with device token auth"}


@app.post("/tools/{tool_name}")
def run_tool(tool_name: str, call: ChatToolCall):
    return _run_tool(tool_name, call)


def _process_omi_webhook(payload: OmiWebhookPayload):
    omi_user_id = payload.omi_user_id or payload.user_id
    if not omi_user_id:
        raise HTTPException(status_code=422, detail="omi_user_id required")
    tasks = task_extraction.extract_tasks_from_webhook(payload.model_dump(mode="json"))
    stored = [integrations.dispatch_task(omi_user_id, task.model_dump(mode="json")) for task in tasks]
    storage.audit(
        omi_user_id,
        None,
        "omi_webhook_processed",
        {"task_count": len(tasks), "conversation_id": payload.conversation_id},
    )
    return {"status": "ok", "tasks": [task.model_dump(mode="json") for task in tasks], "stored": stored}


def _run_tool(tool_name: str, call: ChatToolCall):
    settings = storage.get_settings(call.omi_user_id)
    data = settings.model_dump(mode="json")
    args = call.arguments
    if tool_name == "get_capture_status":
        return policy.policy_status(call.omi_user_id, call.device_id)
    if tool_name == "set_capture_mode":
        data["advanced_capture_enabled"] = args.get("mode", "off") != "off"
        data["default_capture_mode"] = args.get("mode", data["default_capture_mode"])
    elif tool_name == "set_capture_sensitivity":
        data["sensitivity"] = args.get("sensitivity", data["sensitivity"])
    elif tool_name == "set_communication_mode":
        data["communication_mode"] = args.get("communication_mode", data["communication_mode"])
    elif tool_name == "set_fallback_settings":
        data["allow_local_stt_fallback"] = bool(args.get("local_stt", data["allow_local_stt_fallback"]))
        data["allow_caption_fallback"] = bool(args.get("caption", data["allow_caption_fallback"]))
    elif tool_name == "set_retention_policy":
        data["raw_audio_retention"] = args.get("raw_audio_retention", data["raw_audio_retention"])
        data["allow_audio_upload"] = bool(args.get("allow_audio_upload", data["allow_audio_upload"]))
    elif tool_name == "toggle_private_mode":
        data["default_capture_mode"] = "private" if args.get("enabled", True) else "normal"
    elif tool_name in {"pause_capture", "stop_capture"}:
        data["default_capture_mode"] = "off"
        data["advanced_capture_enabled"] = False
    elif tool_name == "resume_capture":
        data["default_capture_mode"] = args.get("mode", "normal")
        data["advanced_capture_enabled"] = True
    elif tool_name == "get_audit_log":
        return {"audit_log": storage.get_audit_log(call.omi_user_id, int(args.get("limit", 100)))}
    elif tool_name == "create_accountability_rule":
        rule = AccountabilityRuleIn(omi_user_id=call.omi_user_id, **args)
        return accountability.create_accountability_rule(rule)
    elif tool_name == "list_accountability_rules":
        return {"rules": accountability.list_accountability_rules(call.omi_user_id)}
    elif tool_name == "update_accountability_rule":
        rule_id = int(args.pop("rule_id"))
        return accountability.update_accountability_rule(rule_id, AccountabilityRuleUpdate(**args))
    elif tool_name == "delete_accountability_rule":
        return accountability.delete_accountability_rule(int(args["rule_id"]))
    else:
        raise HTTPException(status_code=404, detail="unknown_tool")
    updated = storage.save_settings(call.omi_user_id, CaptureSettings.model_validate(data).model_dump(mode="json"))
    storage.audit(call.omi_user_id, call.device_id, "chat_tool_control", {"tool": tool_name, "arguments": args})
    return {"status": "ok", "settings": updated.model_dump(mode="json")}
