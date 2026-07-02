from datetime import datetime
from typing import Any, Callable, Iterable, List, Mapping, Optional

from pydantic import BaseModel, Field


class SaveFcmTokenRequest(BaseModel):
    fcm_token: str
    time_zone: str


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


class Person(BaseModel):
    id: str
    name: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    speech_samples: List[str] = []
    speech_sample_transcripts: Optional[List[str]] = None
    speech_samples_version: int = 3

<<<<<<< HEAD
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
=======

class PersonLeaderboardEntry(BaseModel):
    person_id: str
    name: str
    conversation_count: int
    speaking_seconds: float
    last_talked_at: Optional[datetime] = None


class PeopleLeaderboardResponse(BaseModel):
    # Size of the window scanned and how many conversations it actually considered,
    # so a client can tell an empty board (no people) from a short history.
    days: int
    conversations_considered: int
    people: List[PersonLeaderboardEntry] = []
>>>>>>> 8ecf43f8c9 (feat(backend): people-you-talk-to-the-most leaderboard (#3808))
