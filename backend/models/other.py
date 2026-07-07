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
    # External identity handles (e.g. normalized iMessage phone/email). Lets us map a
    # chat-app contact back to a canonical Person across multiple handles.
    handles: List[str] = []
    # Where this person record originated: None (voice/manual) or 'imessage', etc.
    source: Optional[str] = None
    # Per-person profile (populated in Phase 2 by generate_person_profile).
    relationship: Optional[str] = None
    profile_summary: Optional[str] = None
    tone_notes: Optional[str] = None
    profile_updated_at: Optional[datetime] = None
    message_count: Optional[int] = None
    # Phase 2: PIL-style structured profile slots projected from person-keyed memories.
    location: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    goals: List[str] = []
    interests: List[str] = []
    preferred_channel: Optional[str] = None
    last_contacted_at: Optional[datetime] = None
