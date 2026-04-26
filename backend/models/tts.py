"""Pydantic models for the TTS (text-to-speech) proxy endpoint.

Mirrors the request shape of `desktop/Backend-Rust/src/routes/tts.rs` so the
mobile and desktop clients can share contract expectations.
"""

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_VOICE_ID = "BAMYoBHLZM7lJgJAmFz0"  # Sloane
DEFAULT_MODEL_ID = "eleven_turbo_v2_5"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"


class TtsVoiceSettings(BaseModel):
    stability: Optional[float] = None
    similarity_boost: Optional[float] = None
    style: Optional[float] = None
    use_speaker_boost: Optional[bool] = None


class TtsSynthesizeRequest(BaseModel):
    # `model_id` collides with pydantic's `model_` protected namespace; disable.
    model_config = ConfigDict(protected_namespaces=())

    text: str = Field(..., min_length=1)
    voice_id: str = DEFAULT_VOICE_ID
    model_id: str = DEFAULT_MODEL_ID
    output_format: str = DEFAULT_OUTPUT_FORMAT
    voice_settings: Optional[TtsVoiceSettings] = None
