from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

PLUGIN_ID = "ambient_second_brain_controller"
POLICY_SCOPE = "ambient_capture_controller"

CaptureMode = Literal["off", "normal", "aggressive", "work_hours", "meeting", "private"]
Sensitivity = Literal["low", "medium", "high", "custom"]
CommunicationMode = Literal[
    "off",
    "detect_only",
    "detect_and_attempt_mic",
    "detect_and_caption_fallback",
]
RawAudioRetention = Literal["none", "until_synced", "24h", "7d"]
NotificationAggressiveness = Literal["quiet", "normal", "persistent", "urgent"]
AuditLevel = Literal["basic", "verbose"]
FallbackSource = Literal["local_stt", "accessibility_caption", "live_caption", "gap_marker"]


class DeviceRegisterRequest(BaseModel):
    omi_user_id: str
    device_id: str
    device_label: str
    app_install_id: str
    client_public_key: Optional[str] = None


class DeviceRegisterResponse(BaseModel):
    device_registered: bool
    policy_url: str
    telemetry_url: str
    fallback_segments_url: str
    audio_spool_url: str
    plugin_public_key: str
    key_id: str
    key_fingerprint: str
    device_token: str


class DeviceRevokeRequest(BaseModel):
    omi_user_id: str
    device_id: str


class CaptureSettings(BaseModel):
    advanced_capture_enabled: bool = False
    default_capture_mode: CaptureMode = "off"
    sensitivity: Sensitivity = "medium"
    silence_detection_seconds: int = 12
    rms_silence_dbfs_threshold: float = -75
    zero_frame_threshold: float = 0.98
    allow_accessibility_mode: bool = False
    allow_local_stt_fallback: bool = True
    allow_caption_fallback: bool = False
    allow_audio_upload: bool = False
    allow_transcript_upload: bool = True
    raw_audio_retention: RawAudioRetention = "until_synced"
    communication_mode: CommunicationMode = "detect_only"
    high_risk_apps: List[str] = Field(
        default_factory=lambda: [
            "com.microsoft.teams",
            "us.zoom.videomeetings",
            "com.google.android.apps.meetings",
            "com.Slack",
        ]
    )
    notification_aggressiveness: NotificationAggressiveness = "quiet"
    audit_level: AuditLevel = "basic"
    work_hours: Dict[str, Any] = Field(default_factory=dict)
    integrations: Dict[str, Any] = Field(default_factory=dict)
    allow_telemetry_text: bool = False


class CapturePolicyPayload(BaseModel):
    version: int = 1
    plugin_id: str = PLUGIN_ID
    scope: str = POLICY_SCOPE
    user_id: str
    device_id: str
    sequence: int
    issued_at: datetime
    valid_until: datetime
    capture_mode: CaptureMode
    sensitivity: Sensitivity
    silence_detection_seconds: int
    rms_silence_dbfs_threshold: float
    zero_frame_threshold: float
    allow_foreground_mic: bool
    allow_accessibility_mode: bool
    allow_local_stt_fallback: bool
    allow_caption_fallback: bool
    allow_audio_upload: bool
    allow_transcript_upload: bool
    raw_audio_retention: RawAudioRetention
    communication_mode: CommunicationMode
    high_risk_apps: List[str]
    notification_aggressiveness: NotificationAggressiveness
    audit_level: AuditLevel


class SignedPolicy(BaseModel):
    payload: CapturePolicyPayload
    payload_json: str
    signature: str
    alg: str = "Ed25519"
    key_id: str
    public_key: str


class TelemetryIn(BaseModel):
    omi_user_id: str
    device_id: str
    event_type: str
    timestamp: datetime
    capture_state: Optional[str] = None
    health_state: Optional[str] = None
    foreground_app: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FallbackSegmentIn(BaseModel):
    text: str = ""
    source: FallbackSource
    start: datetime
    end: datetime
    confidence: Optional[float] = None
    health_state: str
    raw_audio_available: bool = False
    foreground_app: Optional[str] = None


class FallbackSegmentsRequest(BaseModel):
    omi_user_id: str
    device_id: str
    session_id: str
    segments: List[FallbackSegmentIn]


class AudioSpoolUploadRequest(BaseModel):
    omi_user_id: str
    device_id: str
    session_id: str
    filename: str
    started_at: datetime
    duration_estimate: float = 0.0
    sample_rate: int = 16000
    channels: int = 1
    codec: Literal["pcm16"] = "pcm16"
    format: Literal["length_prefixed_pcm"] = "length_prefixed_pcm"
    audio_base64: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class OmiWebhookPayload(BaseModel):
    omi_user_id: Optional[str] = None
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None
    memory_id: Optional[str] = None
    transcript: Optional[str] = None
    text: Optional[str] = None
    segments: List[Dict[str, Any]] = Field(default_factory=list)
    data: Dict[str, Any] = Field(default_factory=dict)


class ExtractedTask(BaseModel):
    title: str
    description: str = ""
    source_conversation_id: Optional[str] = None
    source_segment_ids: List[str] = Field(default_factory=list)
    due_at: Optional[datetime] = None
    owner: Literal["user", "other", "unknown"] = "unknown"
    confidence: float = 0.0
    destination: Literal["omi", "google_tasks", "google_calendar", "slack_dm", "none"] = "none"
    requires_confirmation: bool = True


class AccountabilityRuleIn(BaseModel):
    omi_user_id: str
    name: str
    prompt: str
    cadence: str = "daily"
    enabled: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AccountabilityRuleUpdate(BaseModel):
    name: Optional[str] = None
    prompt: Optional[str] = None
    cadence: Optional[str] = None
    enabled: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None


class ChatToolCall(BaseModel):
    omi_user_id: str
    device_id: Optional[str] = None
    arguments: Dict[str, Any] = Field(default_factory=dict)
