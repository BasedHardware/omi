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
    confirm_lines: list[str] | None = None
    # Present only when this price overrides the tier cta_label (switch to yearly).
    cta_label: str | None = None

    @model_serializer(mode='wrap')
    def _omit_empty_optionals(self, handler):
        data = handler(self)
        if data.get('months_free') is None:
            data.pop('months_free', None)
        if data.get('confirm_lines') is None:
            data.pop('confirm_lines', None)
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
    # True when the card has no bullets and no purchase button: the current
    # plan without a CTA, and Free shown to a cancel-scheduled paid subscriber.
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
    # Remaining recording hours. Present only from 80% up to, but not including, 100%,
    # and only when that estimate is positive. Clients that localize the meter use this
    # with percent and reset_label; English keeps meter_line.
    hours_left: int | None = None
    nudge_line: str | None = None
    # Opens the plans sheet (trigger=usage_budget). Only with a usage_budget meter line.
    more_label: str | None = None
    pro_gates: list[str] = Field(default_factory=list)
    mcp_cap_reached: bool = False

    @model_serializer(mode='wrap')
    def _omit_inactive_cap(self, handler):
        data = handler(self)
        if not self.mcp_cap_reached:
            data.pop('mcp_cap_reached', None)
        if data.get('more_label') is None:
            data.pop('more_label', None)
        if data.get('hours_left') is None:
            data.pop('hours_left', None)
        return data


class StorefrontCapChoice(BaseModel):
    title: str
    body: str
    upgrade_label: str
    on_device_label: str
    dont_ask_again_label: str
    on_device_upgrade_line: str


class ChatAtCap(BaseModel):
    state: Literal['paused'] = 'paused'
    title: str
    body: str
    reset_at: int
    reset_line: str
    trigger: Literal['usage_budget'] = 'usage_budget'
    upgrade_plan: str | None = None
    upgrade_label: str | None = None


class StorefrontResponse(BaseModel):
    schema_version: Literal[2] = 2
    catalog_revision: int
    show_subscription_ui: bool = True
    header: str | None = None
    current: StorefrontCurrent | None = None
    usage: StorefrontUsage = Field(default_factory=StorefrontUsage)
    tiers: list[StorefrontTier] = Field(default_factory=list)
    yearly_toggle_label: str | None = None
    at_cap: StorefrontCapChoice | None = None
    chat_at_cap: ChatAtCap | None = None

    @model_serializer(mode='wrap')
    def _omit_inactive_cap(self, handler):
        data = handler(self)
        if self.chat_at_cap is None:
            data.pop('chat_at_cap', None)
        if self.at_cap is None:
            data.pop('at_cap', None)
        return data
