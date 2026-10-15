"""Pydantic models for the TTS (text-to-speech) proxy endpoint.

Defines the request shape shared by mobile and desktop clients.
"""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_VOICE_ID = "BAMYoBHLZM7lJgJAmFz0"  # Sloane
DEFAULT_MODEL_ID = "eleven_turbo_v2_5"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"


class TtsVoiceSettings(BaseModel):
    stability: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    similarity_boost: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    style: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    use_speaker_boost: Optional[bool] = None


class TtsSynthesizeRequest(BaseModel):
    # `model_id` collides with pydantic's `model_` protected namespace; disable.
    model_config = ConfigDict(protected_namespaces=())

    # Upper bound mirrors _TTS_REQUEST_CHAR_LIMIT in routers/tts.py (and the Rust backend), so an
    # oversized request is rejected at the schema/contract boundary rather than only at runtime.
    text: str = Field(..., min_length=1, max_length=5000)
    voice_id: str = DEFAULT_VOICE_ID
    model_id: str = DEFAULT_MODEL_ID
    output_format: str = DEFAULT_OUTPUT_FORMAT
    voice_settings: Optional[TtsVoiceSettings] = None

    @field_validator("text", "voice_id", "model_id", "output_format", mode="before")
    @classmethod
    def _validate_non_blank_strings(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("TTS fields must be strings")
        value = value.strip()
        if not value:
            raise ValueError("TTS fields must not be blank")
        return value


class TtsVoice(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)

    @field_validator("id", "name", mode="before")
    @classmethod
    def _validate_non_blank(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("voice fields must be strings")
        value = value.strip()
        if not value:
            raise ValueError("voice fields must not be blank")
        return value


class TtsVoiceCatalog(BaseModel):
    voices: List[TtsVoice]
    default_voice_id: str = Field(min_length=1)

    @field_validator("default_voice_id", mode="before")
    @classmethod
    def _validate_non_blank(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("default_voice_id must be a string")
        value = value.strip()
        if not value:
            raise ValueError("default_voice_id must not be blank")
        return value


class AssistantVoicePreference(BaseModel):
    voice_id: str = Field(min_length=1)

    @field_validator("voice_id", mode="before")
    @classmethod
    def _validate_non_blank(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("voice_id must be a string")
        value = value.strip()
        if not value:
            raise ValueError("voice_id must not be blank")
        return value


class AssistantVoicePreferenceUpdate(BaseModel):
    voice_id: str = Field(min_length=1)

    @field_validator("voice_id", mode="before")
    @classmethod
    def _validate_non_blank(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("voice_id must be a string")
        value = value.strip()
        if not value:
            raise ValueError("voice_id must not be blank")
        return value
