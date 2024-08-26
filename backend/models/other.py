from datetime import datetime
from typing import List

from pydantic import BaseModel


class SaveFcmTokenRequest(BaseModel):
    fcm_token: str
    time_zone: str


class UploadProfile(BaseModel):
    bytes: List[List[int]]
    duration: int


class CreatePerson(BaseModel):
    name: str


class Person(BaseModel):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    deleted: bool = False
