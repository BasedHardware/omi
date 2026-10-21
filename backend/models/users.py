from models.storefront import ChatAtCap
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Literal

from pydantic import BaseModel, Field, model_serializer

from config.plan_catalog import PlanType


class WebhookType(str, Enum):
    audio_bytes = 'audio_bytes'
    audio_bytes_websocket = 'audio_bytes_websocket'
    realtime_transcript = 'realtime_transcript'
    memory_created = ('memory_created',)
    day_summary = 'day_summary'
    button_event = 'button_event'


def webhook_url_from_setting(wtype: WebhookType | str, value: Optional[str]) -> str:
    """The endpoint a stored webhook setting points at, or '' when none is configured.

    audio_bytes stores '<url>,<seconds>', so clearing only the URL leaves a ',5' setting
    that is not an empty string yet has nowhere to deliver to. Every caller deciding
    whether a webhook is configured must read the setting through here.
    """
    if not value:
        return ''
    # WebhookType is a str enum, so this holds for the raw wire value too.
    if wtype == WebhookType.audio_bytes:
        value = value.split(',')[0]
    return value.strip()


LOCATION_CONTEXT_PURPOSE = 'chat_city_context'
LOCATION_CONTEXT_DISCLOSED_PROVIDERS = ('Google Maps', 'the configured AI chat provider')


class LocationContextConsentStatus(str, Enum):
    granted = 'granted'
    revoked = 'revoked'


class LocationContextConsent(BaseModel):
    """Server-owned authorization for city-only context in interactive chat."""

    status: LocationContextConsentStatus
    purpose: str
    disclosed_providers: tuple[str, str]
    granted_at: datetime
    expires_at: datetime
    revoked_at: Optional[datetime] = None

    def is_active(self, now: Optional[datetime] = None) -> bool:
        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None or self.granted_at.tzinfo is None or self.expires_at.tzinfo is None:
            return False
        return (
            self.status is LocationContextConsentStatus.granted
            and self.revoked_at is None
            and self.purpose == LOCATION_CONTEXT_PURPOSE
            and self.disclosed_providers == LOCATION_CONTEXT_DISCLOSED_PROVIDERS
            and self.granted_at <= current_time
            and self.expires_at > current_time
        )


class LocationContextConsentUpdate(BaseModel):
    enabled: bool
    disclosure_accepted: bool = Field(
        default=False,
        description=(
            'Required to enable city context: Google Maps reverse-geocodes the device location and the configured '
            'AI chat provider receives city, region, and country only.'
        ),
    )


class LocationContextConsentResponse(BaseModel):
    enabled: bool
    purpose: str = LOCATION_CONTEXT_PURPOSE
    disclosed_providers: tuple[str, str] = LOCATION_CONTEXT_DISCLOSED_PROVIDERS
    expires_at: Optional[datetime] = None


class SubscriptionStatus(str, Enum):
    active = 'active'
    inactive = 'inactive'


class PlanLimits(BaseModel):
    transcription_seconds: Optional[int] = None
    words_transcribed: Optional[int] = None
    insights_gained: Optional[int] = None
    # Chat caps. Exactly one of these is set per plan: `free` and `unlimited`
    # (displayed as "Plus") cap by question count; `architect` caps by cost_usd.
    chat_questions_per_month: Optional[int] = None
    chat_cost_usd_per_month: Optional[float] = None


class ChatQuotaUnit(str, Enum):
    questions = 'questions'
    cost_usd = 'cost_usd'


class ChatUsageQuota(BaseModel):
    chat_at_cap: ChatAtCap | None = None
    uses_shared_budget: bool = False
    plan: str  # display name: "Free", "Plus", "Architect"
    plan_type: str  # internal id: "basic" | "unlimited" | "architect"
    unit: ChatQuotaUnit
    used: float
    limit: Optional[float] = None  # None = unlimited (fallback)
    percent: float = 0.0
    allowed: bool = True
    reset_at: Optional[int] = None  # unix seconds — start of next month UTC
    # Catalog exhaustion policy for this plan's chat allocation. True means going
    # past `limit` accrues a charge instead of blocking, so a client must not
    # gate sends on `allowed` alone (`utils.subscription.enforce_chat_quota`
    # returns without raising for these plans).
    is_overage_plan: bool = False

    @model_serializer(mode='wrap')
    def _omit_inactive_shared_budget(self, handler):
        data = handler(self)
        if self.chat_at_cap is None:
            data.pop('chat_at_cap', None)
        if not self.uses_shared_budget:
            data.pop('uses_shared_budget', None)
        return data


class Subscription(BaseModel):
    # Catalog identity; the route remaps labels before serializing for legacy clients.
    plan: PlanType = PlanType.basic
    status: SubscriptionStatus = SubscriptionStatus.active
    current_period_end: Optional[int] = None
    # Period start is used by the Neo desktop-grandfather check. Populated by the
    # Stripe webhook on every subscription event going forward; existing subs
    # have None until their first post-deploy webhook fires (renewal/cancel/etc.)
    # and are treated as pre-cutoff (grandfathered) until then.
    current_period_start: Optional[int] = None
    stripe_subscription_id: Optional[str] = None
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


class TranscriptionAllowanceSnapshot(BaseModel):
    """The one server answer to which STT mode the client should open (local-models free tier, S16).

    ``mode``: ``managed`` (Omi-billed socket), ``on_device`` (the plan's managed
    minutes are spent; the local engine is free on every plan), ``blocked``
    (desktop trial paywall). ``remaining_seconds`` is null when unlimited.
    """

    mode: str
    remaining_seconds: Optional[int] = None
    reason: str = ''


class HeldAudioRecording(BaseModel):
    """One recording the server is keeping until reset or upgrade. No audio bytes."""

    id: str
    started_at: int
    seconds: int


class HeldAudioSummary(BaseModel):
    """Additive held-audio totals. Absent until funded-STT dispatch enforcement is holding audio.

    ``count`` is the exact number of holds, including ones past the newest page.
    ``recordings`` is that page, newest first.
    """

    seconds: int
    reset_at: int
    retain_live: bool
    state: Literal['paused', 'recovering'] = 'paused'
    count: int = 0
    recordings: List[HeldAudioRecording] = []


class ProcessingBacklog(BaseModel):
    state: Literal['capped', 'waiting_choice', 'processing', 'none']
    budget_exhausted: bool = False
    held_audio_count: int = 0
    held_audio_seconds: int = 0
    deferred_conversations: int = 0
    deferred_seconds: int = 0
    estimated_units: float = 0
    estimated_hours: float = 0
    estimated_percent: float = 0
    remaining_units: Optional[float] = None
    exceeds_remaining: bool = False


class UserSubscriptionResponse(BaseModel):
    subscription: Subscription
    transcription_seconds_used: int
    transcription_seconds_limit: int
    words_transcribed_used: int
    words_transcribed_limit: int
    insights_gained_used: int
    insights_gained_limit: int
    available_plans: List[SubscriptionPlan] = []
    show_subscription_ui: bool = True
    # True only for a reader who can still get an introductory free trial on checkout: on the free
    # plan with no Stripe customer yet. A former subscriber is False; clients must not promise a
    # trial they will not get (the checkout refuses a trial request for such a reader).
    trial_eligible: bool = False
    # Chat quota usage — derived from llm_usage collection
    chat_quota_used: float = 0.0
    chat_quota_unit: Optional[ChatQuotaUnit] = None
    chat_quota_percent: float = 0.0
    chat_quota_allowed: bool = True
    chat_quota_reset_at: Optional[int] = None
    # Phone call feature access snapshot — null means the client hasn't been
    # given a quota read (older servers or disabled endpoints).
    phone_call_quota: Optional[PhoneCallQuota] = None
    # Unix seconds. Set for Neo subscribers who retain desktop access under the
    # grandfather rule (subscription period started before NEO_DESKTOP_GRANDFATHER_CUTOFF)
    # — value is `subscription.current_period_end`. Null otherwise. The desktop client
    # uses this to render a "Neo desktop access ends on <date>" notice.
    desktop_grandfather_until: Optional[int] = None
    # Resolved once per request by `resolve_transcription_allowance`; the same
    # answer the listen socket enforces. Null only on servers that predate it.
    transcription_allowance: Optional[TranscriptionAllowanceSnapshot] = None
    # Present only while STT cap dispatch enforcement is on and audio is held
    # or live capture must be retained. Omitted entirely when unset, not null.
    # Older clients ignore the field.
    held_audio: Optional[HeldAudioSummary] = None
    processing_backlog: Optional[ProcessingBacklog] = None
    # Server catalog capability, independent of BYOK and usage-budget availability.
    cloud_screen_vectors: Optional[bool] = None

    @model_serializer(mode='wrap')
    def serialize_optional_held_audio(self, handler):
        data = handler(self)
        if data.get('cloud_screen_vectors') is None:
            data.pop('cloud_screen_vectors', None)
        if data.get('held_audio') is None:
            data.pop('held_audio', None)
        if data.get('processing_backlog') is None:
            data.pop('processing_backlog', None)
        return data


class AvailableLanguage(BaseModel):
    code: str
    name: str


class AvailableLanguagesResponse(BaseModel):
    languages: List[AvailableLanguage]
