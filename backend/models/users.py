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
    basic = 'basic'
    unlimited = 'unlimited'  # LEGACY — display "Unlimited (legacy)"; hidden from new users
    pro = 'pro'  # LEGACY alias for Architect — kept so old Stripe price IDs still map
    oracle = 'oracle'
    architect = 'architect'


class SubscriptionStatus(str, Enum):
    active = 'active'
    inactive = 'inactive'


class PlanLimits(BaseModel):
    transcription_seconds: Optional[int] = None
    words_transcribed: Optional[int] = None
    insights_gained: Optional[int] = None
    memories_created: Optional[int] = None
    # Chat caps. Exactly one of these is set per plan: `free` and `unlimited`
    # (displayed as "Plus") cap by question count; `pro` caps by cost_usd.
    chat_questions_per_month: Optional[int] = None
    chat_cost_usd_per_month: Optional[float] = None


class ChatQuotaUnit(str, Enum):
    questions = 'questions'
    cost_usd = 'cost_usd'


class ChatUsageQuota(BaseModel):
    plan: str  # display name: "Free", "Plus", "Pro"
    plan_type: str  # internal id: "basic" | "unlimited" | "pro"
    unit: ChatQuotaUnit
    used: float
    limit: Optional[float] = None  # None = unlimited (fallback)
    percent: float = 0.0
    allowed: bool = True
    reset_at: Optional[int] = None  # unix seconds — start of next month UTC


class Subscription(BaseModel):
    plan: PlanType = PlanType.basic
    status: SubscriptionStatus = SubscriptionStatus.active
    current_period_end: Optional[int] = None
    stripe_subscription_id: Optional[str] = None
    current_price_id: Optional[str] = None
    features: List[str] = []
    cancel_at_period_end: bool = False
    limits: PlanLimits = PlanLimits()


class PricingOption(BaseModel):
    id: str  # price_id
    title: str
    description: Optional[str] = None
    price_string: str


class SubscriptionPlan(BaseModel):
    id: str  # e.g., 'oracle'
    title: str
    features: List[str] = []
    prices: List[PricingOption] = []
    legacy: bool = False  # hide from new users; keep visible if they're already subscribed


class UserSubscriptionResponse(BaseModel):
    subscription: Subscription
    transcription_seconds_used: int
    transcription_seconds_limit: int
    words_transcribed_used: int
    words_transcribed_limit: int
    insights_gained_used: int
    insights_gained_limit: int
    memories_created_used: int
    memories_created_limit: int
    available_plans: List[SubscriptionPlan] = []
    show_subscription_ui: bool = True
