from datetime import datetime
from enum import Enum
import math
from typing import Any, Callable, Iterable, List, Mapping, Optional

from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator, model_validator


class SaveFcmTokenRequest(BaseModel):
    fcm_token: str
    time_zone: str


class SyncUserTimeZoneRequest(BaseModel):
    time_zone: str

    @field_validator("time_zone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("time_zone must be a non-empty IANA timezone")
        try:
            ZoneInfo(stripped)
        except Exception as exc:
            raise ValueError("time_zone must be a valid IANA timezone") from exc
        return stripped


class FcmTokenResponse(BaseModel):
    status: str


class SendNotificationRequest(BaseModel):
    uid: str
    title: str
    body: str
    data: dict = Field(default_factory=dict)


class SendAppNotificationRequest(BaseModel):
    aid: str
    message: str
    uid: str


class UploadProfile(BaseModel):
    bytes: List[List[int]]
    duration: int


class CreatePerson(BaseModel):
    name: str = Field(min_length=2, max_length=40)


# Person photo deferred pending product input on storage: no photo/avatar/image
# field today; GCS people_profiles/ is speech-sample audio only; the app uses
# local speaker icons; unlike app/persona logos there is no person-photo URL or
# upload pattern to mirror. Do not invent an optional photo string yet.
class VoiceReadiness(str, Enum):
    ready = 'ready'
    saved_sample_awaiting_embedding = 'saved_sample_awaiting_embedding'
    not_learned = 'not_learned'
    unknown = 'unknown'


def voice_readiness(data: Mapping[str, Any]) -> VoiceReadiness:
    """Report stored recognition evidence, never infer a queued enrollment job."""
    samples = data.get('speech_samples')
    version = data.get('speech_samples_version')
    if samples is None or not isinstance(samples, list):
        return VoiceReadiness.unknown
    if not samples:
        return VoiceReadiness.not_learned
    if not isinstance(version, int) or isinstance(version, bool) or version < 3:
        return VoiceReadiness.unknown
    vector = data.get('speaker_embedding')
    if vector is None or vector == []:
        return VoiceReadiness.saved_sample_awaiting_embedding
    if (
        not isinstance(vector, list)
        or not vector
        or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in vector)
        or not any(v != 0 for v in vector)
    ):
        return VoiceReadiness.unknown
    return VoiceReadiness.ready


class Person(BaseModel):
    id: str
    name: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    speech_samples: List[str] = []
    speech_sample_transcripts: Optional[List[str]] = None
    speech_samples_version: int = 3
    voice_readiness: VoiceReadiness = VoiceReadiness.unknown

    @model_validator(mode='before')
    @classmethod
    def derive_voice_readiness(cls, data):
        if isinstance(data, Mapping):
            claimed = data.get('voice_readiness')
            try:
                VoiceReadiness(claimed)
                claimed_valid = True
            except (ValueError, TypeError):
                claimed_valid = False
            if claimed_valid and 'speaker_embedding' not in data:
                return data
            data = {**data, 'voice_readiness': voice_readiness(data)}
        return data

    @classmethod
    def deserialize_many_safe(
        cls,
        records: Iterable[Mapping[str, Any]],
        on_error: Optional[Callable[[Mapping[str, Any], Exception], None]] = None,
    ) -> List['Person']:
        """Build Person objects from raw stored records, skipping any that fail validation so one
        malformed or legacy person document cannot break a whole people lookup. on_error(record,
        exception), when provided, is called for each skip. Mirrors Message.deserialize_many_safe."""
        parsed: List['Person'] = []
        for record in records:
            try:
                parsed.append(cls(**record))
            except Exception as exc:  # noqa: BLE001 - one bad record must not break the lookup
                if on_error is not None:
                    on_error(record, exc)
        return parsed
