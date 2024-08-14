from typing import List

from pydantic import BaseModel


class SaveFcmTokenRequest(BaseModel):
    fcm_token: str
    time_zone: str


class UploadProfile(BaseModel):
    bytes: List[List[int]]
    duration: int
