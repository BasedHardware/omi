"""Contracts shared by the listen WebSocket session components.

The route module owns HTTP/WebSocket admission.  This package owns the
long-lived session after the socket is accepted, so components can be tested
without importing the FastAPI router.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from utils.client_device import ClientDeviceContext


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
    client_device_context: Optional[ClientDeviceContext] = None


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
    last_activity_time: Optional[float] = None


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
    speaker_id_target_audio: float = 4.0
    credits_refresh_seconds: int = 900
    ws_receive_timeout: float = 300.0
    bg_drain_timeout: float = 30.0
