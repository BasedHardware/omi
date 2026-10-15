"""Versioned backend presentation contract; clients render fields verbatim."""

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_serializer


class StorefrontPrice(BaseModel):
    price_id: Optional[str] = None
    interval: Literal['month', 'year']
    amount_minor: int = Field(ge=0)
    currency: str = Field(min_length=1, max_length=10)
    headline: str
    subline: Optional[str] = None
    renewal_line: Optional[str] = None
    months_free: Optional[int] = Field(default=None, ge=0)
    # Present only when this price overrides the tier cta_label (switch to yearly).
    cta_label: Optional[str] = None

    @model_serializer(mode='wrap')
    def _omit_empty_optionals(self, handler):
        data = handler(self)
        if data.get('months_free') is None:
            data.pop('months_free', None)
        if data.get('cta_label') is None:
            data.pop('cta_label', None)
        return data


class StorefrontTier(BaseModel):
    tier_id: str
    plan_id: str
    name: str
    recommended: bool = False
    is_current: bool = False
    hours_line: str
    bullets: list[str]
    action: Literal['checkout', 'current', 'none']
    cta_label: Optional[str] = None
    blocked_line: Optional[str] = None
    # True when the card has no bullets and no purchase button: the current
    # plan without a CTA, and Free shown to a cancel-scheduled paid subscriber.
    compact: bool = False
    prices: list[StorefrontPrice]


class StorefrontCurrent(BaseModel):
    plan_id: str
    name: str
    price_id: Optional[str] = None
    interval: Optional[Literal['month', 'year']] = None
    legacy: bool
    cancel_at_period_end: bool = False
    line: str
    legacy_note: Optional[str] = None


class StorefrontUsage(BaseModel):
    kind: Literal['usage_budget', 'transcription', 'unavailable'] = 'unavailable'
    percent: Optional[int] = Field(default=None, ge=0)
    period_id: Optional[str] = None
    reset_label: Optional[str] = None
    meter_line: Optional[str] = None
    nudge_line: Optional[str] = None
    pro_gates: list[str] = Field(default_factory=list)


class StorefrontResponse(BaseModel):
    schema_version: Literal[2] = 2
    catalog_revision: int = Field(ge=0)
    show_subscription_ui: bool = True
    header: Optional[str] = None
    current: Optional[StorefrontCurrent] = None
    usage: StorefrontUsage = Field(default_factory=StorefrontUsage)
    tiers: list[StorefrontTier] = Field(default_factory=list)
    yearly_toggle_label: Optional[str] = None
