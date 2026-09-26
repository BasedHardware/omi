"""Contracts shared by the listen WebSocket session components.

The route module owns HTTP/WebSocket admission.  This package owns the
long-lived session after the socket is accepted, so components can be tested
without importing the FastAPI router.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, NamedTuple, Optional

from routers.listen.realtime_demand import RealtimeDemandTracker
from utils.client_device import ClientDeviceContext
from models.geolocation import Geolocation


class ConversationCaptureOrigin(NamedTuple):
    """One conversation's first-audio origin on the capture wall axis.

    ``pinnable`` is True only for a conversation admitted as v2 from its
    first audio (created fresh by this v2 session). A resumed row's adopted
    ``started_at`` projects segment offsets but never pins the v2 marker —
    that row stays legacy for its lifetime.
    """

    wall: float
    pinnable: bool


def persisted_started_seconds(started_at: Any) -> Optional[float]:
    """Wall seconds for a persisted ``started_at`` (datetime, number, or ISO string).

    Firestore rows may carry any of the three; an unparseable value returns
    None so callers fail closed instead of crash-looping on ``.timestamp()``.
    """
    if started_at is None:
        return None
    if hasattr(started_at, 'timestamp'):
        try:
            return float(started_at.timestamp())
        except (TypeError, ValueError, OverflowError):
            return None
    if isinstance(started_at, str):
        try:
            return datetime.fromisoformat(started_at.strip().replace('Z', '+00:00')).timestamp()
        except ValueError:
            return None
    if isinstance(started_at, (int, float)) and not isinstance(started_at, bool):
        return float(started_at)
    return None


class CustomSttMode(str, Enum):
    disabled = 'disabled'
    enabled = 'enabled'


@dataclass(frozen=True)
class ListenRequest:
    websocket: Any
    uid: str
    language: str = 'en'
    sample_rate: int = 8000
    codec: str = 'pcm8'
    channels: int = 1
    include_speech_profile: bool = True
    stt_service: Optional[str] = None
    conversation_timeout: int = 120
    source: Optional[str] = None
    custom_stt_mode: CustomSttMode = CustomSttMode.disabled
    onboarding_mode: bool = False
    speaker_auto_assign_enabled: bool = False
    create_speakers: bool = True
    vad_gate_override: Optional[str] = None
    call_id: Optional[str] = None
    client_conversation_id: Optional[str] = None
    conversation_role: str = 'ambient'
    client_device_context: Optional[ClientDeviceContext] = None
    owner_persistence_blocked: asyncio.Event = field(default_factory=asyncio.Event)
    geolocation: Optional[Geolocation] = None
    # A re-record of an *existing* speech profile from Settings, not a claim to
    # onboarding provenance. Distinct from onboarding_mode (which still drives
    # the same server-pushed question flow) so this can bypass the
    # completed-account admission gate below without weakening it for real
    # onboarding — see runtime.py's _bootstrap. Appended last so a positional
    # caller can't silently mis-bind an existing argument.
    speech_profile_redo: bool = False


@dataclass
class ListenSessionState:
    active: bool = True
    close_code: int = 1001
    stt_terminal_failure: bool = False
    shutdown_event: asyncio.Event = field(default_factory=asyncio.Event)
    audio_ring_buffer: Any = None
    speaker_id_enabled: bool = False
    speaker_id_done: asyncio.Event = field(default_factory=asyncio.Event)
    speaker_map_dirty: bool = False
    first_audio_byte_timestamp: Optional[float] = None
    # Capture sample clock (single-channel server-STT sessions): the per-socket
    # sample cursor, per-conversation pinned first-audio origins (wall seconds),
    # fresh conversations still awaiting their first accepted frame, and the
    # recent capture ranges that resolve a mapped provider segment's owning
    # conversation. The clock itself is internal to the socket; capture_timeline
    # is None only for multi-channel and custom-STT sessions. capture_timeline_v2
    # admits the v2 *persistence* (projected times, started_at pin, marker,
    # pusher projection) for this recording only.
    capture_timeline: Any = None
    capture_timeline_v2: bool = False
    conversation_capture_origins: Dict[str, 'ConversationCaptureOrigin'] = field(default_factory=dict)
    conversations_awaiting_capture_origin: set = field(default_factory=set)
    # Rows resumed with an unparseable started_at: their origin is unknowable,
    # so they never pin the v2 marker and project against the legacy base.
    conversations_legacy_locked: set = field(default_factory=set)
    conversation_sample_ranges: Any = None
    live_transcription_attempt: Any = None
    client_live_transcription_attempt: Any = None
    live_transcription_failed: bool = False
    last_usage_record_timestamp: Optional[float] = None
    words_transcribed_since_last_record: int = 0
    last_transcript_time: Optional[float] = None
    current_conversation_id: Optional[str] = None
    freemium_threshold_sent: bool = False
    remaining_seconds_cache: Optional[int] = None
    remaining_seconds_cache_ts: float = 0.0
    remaining_seconds_cache_initialized: bool = False
    fair_use_last_check_ts: float = 0.0
    fair_use_dg_budget_exhausted: bool = False
    fair_use_track_dg_usage: bool = False
    fair_use_plan: Optional[Any] = None
    dg_usage_ms_pending: int = 0
    last_audio_received_time: Optional[float] = None
    last_audio_resume_time: Optional[float] = None
    last_activity_time: Optional[float] = None
    # Client-provided close provenance. This is set before a normal WebSocket
    # close so finalization can distinguish an internal rotation from a
    # terminal meeting end without trusting socket timing.
    finalization_reason: Optional[str] = None
    # Who could watch this session live; see routers/listen/realtime_demand.py.
    realtime_demand: RealtimeDemandTracker = field(default_factory=RealtimeDemandTracker)


@dataclass(frozen=True)
class ListenLimits:
    max_segment_buffer_size: int = 1000
    max_photo_buffer_size: int = 100
    max_audio_buffer_size: int = 10 * 1024 * 1024
    max_pending_requests: int = 100
    max_pending_speaker_sample_requests: int = 50
    max_image_chunks: int = 50
    image_chunk_ttl: float = 60.0
    image_chunk_cleanup_interval: float = 2.0
    image_chunk_cleanup_min_size: int = 5
    ring_buffer_duration: float = 60.0
    speaker_id_min_audio: float = 2.0
    credits_refresh_seconds: int = 900
    ws_receive_timeout: float = 300.0
    bg_drain_timeout: float = 30.0
