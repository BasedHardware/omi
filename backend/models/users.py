from enum import Enum
from typing import Optional, List

from pydantic import BaseModel


class WebhookType(str, Enum):
    audio_bytes = 'audio_bytes'
    audio_bytes_websocket = 'audio_bytes_websocket'
    realtime_transcript = 'realtime_transcript'
    memory_created = ('memory_created',)
    day_summary = 'day_summary'


class PlanType(str, Enum):
    free = 'free'
    unlimited = 'unlimited'


class SubscriptionStatus(str, Enum):
    active = 'active'
    inactive = 'inactive'


class Subscription(BaseModel):
    plan: PlanType = PlanType.free
    status: SubscriptionStatus = SubscriptionStatus.active
    current_period_end: Optional[int] = None
    stripe_subscription_id: Optional[str] = None
    features: List[str] = []
    cancel_at_period_end: bool = False


class SubscriptionPlan(BaseModel):
    id: str  # price_id
    title: str
    description: Optional[str] = None
    price_string: str
    features: List[str] = []


class UserSubscriptionResponse(BaseModel):
    subscription: Subscription
    transcription_seconds_used: int
    transcription_seconds_limit: int
    available_plans: List[SubscriptionPlan] = []
