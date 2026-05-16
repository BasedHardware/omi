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
    basic = 'basic'  # display "Free"
    unlimited = 'unlimited'  # LEGACY — display "Neo"; hidden from new mobile users
    architect = 'architect'  # display "Architect"
    operator = 'operator'  # display "Operator"
    # Mobile-only paid tiers (Superwall-purchased via App Store / Play). The
    # caps live in `app_config/plan_caps` Firestore doc; defaults match
    # BasedHardware/omi-enterprise#23 (Lite: 100 msgs / 1500 mins, Plus: 300
    # msgs / 4000 mins, Unlimited: no caps).
    # Note: ``unlimited_v2`` is internally distinct from the legacy ``unlimited``
    # (Neo) plan — the legacy keeps its enum value for backward-compat with
    # live Stripe subscribers; the new mobile tier uses ``unlimited_v2`` to
    # avoid colliding while still being displayed to users as "Unlimited".
    lite = 'lite'
    plus = 'plus'
    unlimited_v2 = 'unlimited_v2'

    @classmethod
    def _missing_(cls, value):
        # Backward compat: 'pro' was renamed to 'architect' before the
        # Lite/Plus/Max tiers were introduced. Five live user docs still
        # store `plan='pro'` literally — keep them resolving to architect.
        if value == 'pro':
            return cls.architect
        return None


class SubscriptionStatus(str, Enum):
    active = 'active'
    inactive = 'inactive'


class SubscriptionSource(str, Enum):
    """Which billing rail created the subscription. ``stripe`` covers the
    legacy book (web/desktop checkout); ``superwall_*`` covers new mobile
    purchases routed through Superwall + App Store / Play Billing."""

    stripe = 'stripe'
    superwall_ios = 'superwall_ios'
    superwall_android = 'superwall_android'


class PlanLimits(BaseModel):
    transcription_seconds: Optional[int] = None
    words_transcribed: Optional[int] = None
    insights_gained: Optional[int] = None
    memories_created: Optional[int] = None
    # Chat caps. Exactly one of these is set per plan: `free` and `unlimited`
    # (displayed as "Plus") cap by question count; `architect` caps by cost_usd.
    chat_questions_per_month: Optional[int] = None
    chat_cost_usd_per_month: Optional[float] = None


class ChatQuotaUnit(str, Enum):
    questions = 'questions'
    cost_usd = 'cost_usd'


class ChatUsageQuota(BaseModel):
    plan: str  # display name: "Free", "Plus", "Architect"
    plan_type: str  # internal id: "basic" | "unlimited" | "architect"
    unit: ChatQuotaUnit
    used: float
    limit: Optional[float] = None  # None = unlimited (fallback)
    percent: float = 0.0
    allowed: bool = True
    reset_at: Optional[int] = None  # unix seconds — start of next month UTC


class Subscription(BaseModel):
    plan: PlanType = PlanType.basic
    status: SubscriptionStatus = SubscriptionStatus.active
    # Which billing rail owns this sub. Defaults to `stripe` so existing user
    # docs (which don't carry the field) behave exactly as before. Set to
    # `superwall_ios` / `superwall_android` by the Superwall webhook handler.
    source: SubscriptionSource = SubscriptionSource.stripe
    current_period_end: Optional[int] = None
    stripe_subscription_id: Optional[str] = None
    # Identifier from Superwall (their internal sub id) — populated only for
    # mobile purchases. Lets the webhook handler dedupe events.
    superwall_subscription_id: Optional[str] = None
    current_price_id: Optional[str] = None
    features: List[str] = []
    cancel_at_period_end: bool = False
    limits: PlanLimits = PlanLimits()
    deprecated: bool = False
    deprecation_message: Optional[str] = None


class PricingOption(BaseModel):
    id: str  # price_id
    title: str
    description: Optional[str] = None
    price_string: str


class SubscriptionPlan(BaseModel):
    id: str  # e.g., 'operator'
    title: str
    subtitle: Optional[str] = None  # e.g. "500 questions per month" — rendered under the title
    description: Optional[str] = None  # longer copy rendered below price
    eyebrow: Optional[str] = None  # e.g. "Most popular" — rendered above the title
    features: List[str] = []
    prices: List[PricingOption] = []
    legacy: bool = False


class TrialMetadata(BaseModel):
    """Structured trial state for desktop clients to render countdown UI."""

    trial_started_at: Optional[int] = None  # unix seconds
    trial_ends_at: Optional[int] = None  # unix seconds
    trial_remaining_seconds: int = 0
    trial_expired: bool = False
    trial_duration_seconds: int = 0  # configured trial length
    trial_features: List[str] = []
    plan_after_trial: str = 'Free'  # display name of fallback plan


class PhoneCallQuota(BaseModel):
    """Phone call feature access + remaining-quota snapshot for the client."""

    has_access: bool
    is_paid: bool
    monthly_limit: Optional[int] = None  # None = unlimited (paid), 0 = disabled
    monthly_used: int = 0
    remaining: Optional[int] = None  # None = unlimited
    max_duration_seconds: Optional[int] = None
    allowed_countries: List[str] = []
    reset_at: Optional[int] = None  # unix seconds — start of next month UTC


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
    # Whether the Superwall mobile paywall is active for this user. Computed
    # server-side from `app_config/plan_caps.superwall_enabled` (global) and
    # `superwall_test_uids` (per-uid override). When false, the client routes
    # all upgrade triggers to the legacy PlansSheet and skips Superwall SDK
    # configuration entirely.
    superwall_enabled: bool = False
    # Chat quota usage — derived from llm_usage collection
    chat_quota_used: float = 0.0
    chat_quota_unit: Optional[ChatQuotaUnit] = None
    chat_quota_percent: float = 0.0
    chat_quota_allowed: bool = True
    chat_quota_reset_at: Optional[int] = None
    # Phone call feature access snapshot — null means the client hasn't been
    # given a quota read (older servers or disabled endpoints).
    phone_call_quota: Optional[PhoneCallQuota] = None
