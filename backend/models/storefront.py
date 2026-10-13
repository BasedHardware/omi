"""Versioned backend presentation contract; clients need no tier policy."""

from typing import Literal

from pydantic import BaseModel, Field


class PlanFeature(BaseModel):
    key: str
    label: str
    included: bool = True


class AnnualSavings(BaseModel):
    amount_minor: int
    percent: float
    formatted: str


class StorefrontPrice(BaseModel):
    price_id: str | None = None
    interval: Literal['month', 'year']
    currency: str
    amount_minor: int
    formatted_amount: str
    monthly_equivalent: str
    annual_savings: AnnualSavings | None = None


class StorefrontTier(BaseModel):
    tier_id: str
    plan_id: str
    entitlement_version: str
    display_name: str
    tagline: str
    features: list[PlanFeature]
    prices: list[StorefrontPrice]
    action: Literal['current', 'upgrade', 'downgrade_not_offered', 'contact']
    recommended: bool = False
    legacy: bool = False


class StorefrontCurrentPlan(BaseModel):
    plan_id: str
    price_id: str | None = None
    legacy: bool


class StorefrontUsage(BaseModel):
    kind: Literal['transcription', 'usage_budget', 'unavailable'] = 'unavailable'
    budget_percent: float | None = None
    reset_at: int | None = None


class StorefrontResponse(BaseModel):
    schema_version: Literal[1] = 1
    catalog_revision: int
    show_subscription_ui: bool = True
    tiers: list[StorefrontTier] = Field(default_factory=list)
    next_offer_tier_id: str | None = None
    current: StorefrontCurrentPlan | None = None
    usage: StorefrontUsage = Field(default_factory=StorefrontUsage)
