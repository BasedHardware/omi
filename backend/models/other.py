from datetime import datetime
from typing import Any, Callable, Iterable, List, Mapping, Optional

from pydantic import BaseModel, Field, model_validator


class SaveFcmTokenRequest(BaseModel):
    fcm_token: str
    time_zone: str


class FcmTokenResponse(BaseModel):
    status: str


class SaveUnifiedPushEndpointRequest(BaseModel):
    endpoint: str
    time_zone: str
    # WebPush keys (optional): present when the app registers an encrypted endpoint. They flow through
    # to storage so the send channel can encrypt the payload (aes128gcm); absent = plaintext POST.
    p256dh: Optional[str] = None
    auth: Optional[str] = None

    @model_validator(mode='after')
    def _both_or_neither_webpush_key(self) -> 'SaveUnifiedPushEndpointRequest':
        # The send channel encrypts only when BOTH keys are set (utils/push/unifiedpush._encode_for).
        # A half-registered endpoint (one key) would silently fall back to plaintext, which an app that
        # sent keys cannot decode. Reject the malformed set at registration (cubic PR 10887 B4).
        if bool(self.p256dh) != bool(self.auth):
            raise ValueError('p256dh and auth WebPush keys must be provided together (both or neither)')
        return self


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


class Person(BaseModel):
    id: str
    name: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    speech_samples: List[str] = []
    speech_sample_transcripts: Optional[List[str]] = None
    speech_samples_version: int = 3

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
