from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class SaveFcmTokenRequest(BaseModel):
    fcm_token: str
    time_zone: str


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
