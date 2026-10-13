"""Versioned backend presentation contract; clients render fields verbatim."""

from typing import Literal

from pydantic import BaseModel, Field, model_serializer


class StorefrontPrice(BaseModel):
    price_id: str | None = None
    interval: Literal['month', 'year']
    amount_minor: int
    currency: str
    headline: str
    subline: str | None = None
    renewal_line: str | None = None
    months_free: int | None = None
    # Present only when this price overrides the tier CTA (switch to yearly).
    cta_label: str | None = None

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
    cta_label: str | None = None
    blocked_line: str | None = None
    # True when this is the current plan and it has no button, so the client drops bullets.
    compact: bool = False
    prices: list[StorefrontPrice]


class StorefrontCurrent(BaseModel):
    plan_id: str
    name: str
    price_id: str | None = None
    interval: Literal['month', 'year'] | None = None
    legacy: bool
    cancel_at_period_end: bool = False
    line: str
    legacy_note: str | None = None


class StorefrontUsage(BaseModel):
    kind: Literal['usage_budget', 'transcription', 'unavailable'] = 'unavailable'
    percent: int | None = None
    period_id: str | None = None
    reset_label: str | None = None
    meter_line: str | None = None
    nudge_line: str | None = None
    pro_gates: list[str] = Field(default_factory=list)


class StorefrontResponse(BaseModel):
    schema_version: Literal[2] = 2
    catalog_revision: int
    show_subscription_ui: bool = True
    header: str | None = None
    current: StorefrontCurrent | None = None
    usage: StorefrontUsage = Field(default_factory=StorefrontUsage)
    tiers: list[StorefrontTier] = Field(default_factory=list)
    yearly_toggle_label: str | None = None
