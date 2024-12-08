from enum import Enum

from pydantic import BaseModel
from typing import Optional


class WebhookType(str, Enum):
    audio_bytes = 'audio_bytes'
    audio_bytes_websocket = 'audio_bytes_websocket'
    realtime_transcript = 'realtime_transcript'
    memory_created = 'memory_created',
    day_summary = 'day_summary'


class PayPalDetails(BaseModel):
    paypal_email: str
    paypal_me_link: Optional[str] = None


class CreatorProfileRequest(BaseModel):
    creator_name: str
    creator_email: str
    paypal_details: PayPalDetails
