"""Read-side memory belief: currency, band, and half-life priors.

Pure functions. No I/O. Currency is never stored; no job writes it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Mapping, Optional

MEMORY_BELIEF_MODEL_ENABLED_ENV = "MEMORY_BELIEF_MODEL_ENABLED"

# Named classes the extractor uses. Priors are days; None means no decay.
HALF_LIFE_DAYS_BY_CLASS: Mapping[str, Optional[float]] = {
    "identity": None,
    "relationship": None,
    "preference": 180.0,
    "state": 30.0,
    "plan": 30.0,
    "episodic": 7.0,
    "meta_residue": 1.0,
    "meta_standing": None,
}

CURRENT_BAND_MIN = 0.5
FADING_BAND_MIN = 0.25


class CurrencyBand(str, Enum):
    current = "current"
    fading = "fading"
    history = "history"


@dataclass(frozen=True)
class BeliefView:
    currency: float
    band: CurrencyBand
    as_of: datetime
    half_life_days: Optional[float]
    last_evidenced_at: datetime


def belief_model_enabled() -> bool:
    """Deployment-wide flag. Unset and any value other than true fail closed to off."""
    return os.getenv(MEMORY_BELIEF_MODEL_ENABLED_ENV, "false").lower() == "true"


def _coerce_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("belief timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def resolve_last_evidenced_at(
    *,
    captured_at: datetime,
    last_corroborated_at: Optional[datetime] = None,
    stored_last_evidenced_at: Optional[datetime] = None,
) -> datetime:
    """Stored evidence clock. Defaults to captured_at when never re-evidenced."""
    if stored_last_evidenced_at is not None:
        return _coerce_aware_utc(stored_last_evidenced_at)
    if last_corroborated_at is not None:
        return _coerce_aware_utc(last_corroborated_at)
    return _coerce_aware_utc(captured_at)


def derive_half_life_days(
    *,
    stored_half_life_days: Optional[float] = None,
    half_life_field_present: bool = False,
    user_asserted: bool = False,
    belief_class: Optional[str] = None,
    kind: Optional[str] = None,
    category: Optional[str] = None,
    tier: Optional[str] = None,
) -> Optional[float]:
    """Stored half-life wins. Explicit null (field present) means no decay.

    Legacy rows omit the field; derive a prior from class/category/tier.
    """
    if half_life_field_present:
        if stored_half_life_days is not None and stored_half_life_days <= 0:
            raise ValueError("half_life_days must be positive when set")
        return stored_half_life_days
    if user_asserted:
        return None
    if belief_class:
        if belief_class not in HALF_LIFE_DAYS_BY_CLASS:
            raise ValueError(f"unknown belief_class: {belief_class}")
        return HALF_LIFE_DAYS_BY_CLASS[belief_class]
    if kind in {"document", "trigger"}:
        return None
    if category == "manual" or (category == "system" and tier == "long_term"):
        return HALF_LIFE_DAYS_BY_CLASS["preference"]
    if tier == "short_term" and category == "interesting":
        return HALF_LIFE_DAYS_BY_CLASS["episodic"]
    if tier == "short_term":
        return HALF_LIFE_DAYS_BY_CLASS["state"]
    return HALF_LIFE_DAYS_BY_CLASS["state"]


def compute_currency(
    *,
    half_life_days: Optional[float],
    last_evidenced_at: datetime,
    now: datetime,
    valid_to: Optional[datetime] = None,
) -> float:
    """Read-side currency. Named-date claims use valid_to instead of a half-life."""
    current_time = _coerce_aware_utc(now)
    evidenced = _coerce_aware_utc(last_evidenced_at)
    if valid_to is not None:
        return 1.0 if current_time <= _coerce_aware_utc(valid_to) else 0.0
    if half_life_days is None:
        return 1.0
    if half_life_days <= 0:
        raise ValueError("half_life_days must be positive when set")
    days_since = max(0.0, (current_time - evidenced).total_seconds() / 86400.0)
    return 0.5 ** (days_since / half_life_days)


def currency_band(currency: float) -> CurrencyBand:
    if currency > CURRENT_BAND_MIN:
        return CurrencyBand.current
    if currency >= FADING_BAND_MIN:
        return CurrencyBand.fading
    return CurrencyBand.history


def belief_view(
    *,
    captured_at: datetime,
    now: datetime,
    stored_half_life_days: Optional[float] = None,
    half_life_field_present: bool = False,
    last_corroborated_at: Optional[datetime] = None,
    stored_last_evidenced_at: Optional[datetime] = None,
    valid_to: Optional[datetime] = None,
    user_asserted: bool = False,
    belief_class: Optional[str] = None,
    kind: Optional[str] = None,
    category: Optional[str] = None,
    tier: Optional[str] = None,
) -> BeliefView:
    evidenced = resolve_last_evidenced_at(
        captured_at=captured_at,
        last_corroborated_at=last_corroborated_at,
        stored_last_evidenced_at=stored_last_evidenced_at,
    )
    half_life = derive_half_life_days(
        stored_half_life_days=stored_half_life_days,
        half_life_field_present=half_life_field_present,
        user_asserted=user_asserted,
        belief_class=belief_class,
        kind=kind,
        category=category,
        tier=tier,
    )
    value = compute_currency(
        half_life_days=half_life,
        last_evidenced_at=evidenced,
        now=now,
        valid_to=valid_to,
    )
    return BeliefView(
        currency=value,
        band=currency_band(value),
        as_of=evidenced,
        half_life_days=half_life,
        last_evidenced_at=evidenced,
    )


def is_user_subject(subject_scope: Optional[str]) -> bool:
    return subject_scope == "primary_user"


def is_contradicted(*, superseded_by: Optional[str] = None, confidence: Optional[float] = None) -> bool:
    if superseded_by:
        return True
    return confidence is not None and confidence <= 0.0


def passes_proactive_bar(
    view: BeliefView,
    *,
    subject_scope: Optional[str],
    superseded_by: Optional[str] = None,
    confidence: Optional[float] = None,
) -> bool:
    """JIT / proactive nudges: current band, user subject, truth not contradicted."""
    return (
        view.band == CurrencyBand.current
        and is_user_subject(subject_scope)
        and not is_contradicted(superseded_by=superseded_by, confidence=confidence)
    )
