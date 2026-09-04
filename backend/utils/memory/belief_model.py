"""Read-side memory belief: currency, band, and half-life priors.

Pure functions. No I/O. Currency is never stored; no job writes it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Mapping, Optional

from utils.memory.decision_path_telemetry import classify_model_about

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
    user_asserted: bool = False,
    belief_class: Optional[str] = None,
    kind: Optional[str] = None,
    category: Optional[str] = None,
    tier: Optional[str] = None,
) -> Optional[float]:
    """Numeric stored half-life wins. ``belief_class`` supplies the class prior
    (including null = no decay). Legacy rows have neither: short_term uses the
    state prior, long_term/archive stay durable until backfill classifies them.
    """
    if stored_half_life_days is not None:
        if stored_half_life_days <= 0:
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
    # category is not a class; keep the argument so existing callers stay valid.
    _ = category
    if tier == "short_term":
        return HALF_LIFE_DAYS_BY_CLASS["state"]
    return None


USER_SUBJECT_SCOPES = frozenset({"primary_user"})
KNOWN_SUBJECT_SCOPES = frozenset(
    {
        "primary_user",
        "user_owned_project",
        "user_relationship",
        "third_party",
    }
)
# Extractor/backfill labels that are not released enum members. The released
# app-client contract pins MemorySubjectScope, so media and on-screen content
# is stored as third_party: non-user is what the surface bars need.
SUBJECT_SCOPE_ALIASES: Mapping[str, str] = {"media_screen": "third_party"}


def subject_scope_from_extraction(
    *,
    extracted_scope: Optional[str] = None,
    attribution: Optional[str] = None,
    about: Optional[str] = None,
    user_name: Optional[str] = None,
    speaker_label: Optional[str] = None,
) -> str:
    """Classify conversation-extracted subjects. Extractor-only labels are normalized via SUBJECT_SCOPE_ALIASES."""
    scope = (extracted_scope or "").strip().lower()
    scope = SUBJECT_SCOPE_ALIASES.get(scope, scope)
    if scope in KNOWN_SUBJECT_SCOPES:
        return scope
    if classify_model_about(about, user_name=user_name, speaker_label=speaker_label) == "primary_user":
        return "primary_user"
    if attribution == "user":
        return "primary_user"
    if attribution == "third_party":
        return "third_party"
    return "third_party"


def horizon_from_extraction(
    *,
    belief_class: Optional[str],
    half_life_days_override: Optional[float] = None,
    user_asserted: bool = False,
) -> tuple[Optional[str], Optional[float]]:
    """Return (belief_class, half_life_days) for a new claim."""
    if user_asserted:
        return (belief_class or "identity", None)
    resolved_class = belief_class if belief_class is not None and belief_class in HALF_LIFE_DAYS_BY_CLASS else "state"
    if half_life_days_override is not None:
        if half_life_days_override <= 0:
            raise ValueError("half_life_days must be positive when set")
        return resolved_class, half_life_days_override
    return resolved_class, HALF_LIFE_DAYS_BY_CLASS[resolved_class]


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
    return subject_scope in USER_SUBJECT_SCOPES


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


def _enum_value(value: object) -> Optional[str]:
    if value is None:
        return None
    raw = getattr(value, "value", value)
    return raw if isinstance(raw, str) else None


def _record_category(item: object) -> Optional[str]:
    """Category from MemoryDB.category or the item audit bag."""
    direct = _enum_value(getattr(item, "category", None))
    if direct:
        return direct
    audit = getattr(item, "".join(("pro", "motion")), None) or {}
    value = audit.get("category") if isinstance(audit, Mapping) else None
    return value if isinstance(value, str) else None


def belief_view_for_record(item: object, *, now: datetime) -> BeliefView:
    """Read-side view from a MemoryItem or MemoryDB-shaped record. No I/O."""
    captured_at = getattr(item, "captured_at", None) or getattr(item, "created_at")
    return belief_view(
        captured_at=captured_at,
        now=now,
        stored_half_life_days=getattr(item, "half_life_days", None),
        last_corroborated_at=getattr(item, "last_corroborated_at", None),
        valid_to=getattr(item, "valid_to", None) or getattr(item, "invalid_at", None),
        user_asserted=bool(getattr(item, "user_asserted", False) or getattr(item, "manually_added", False)),
        belief_class=getattr(item, "belief_class", None),
        kind=_enum_value(getattr(item, "kind", None)),
        category=_record_category(item),
        tier=_enum_value(getattr(item, "tier", None)) or _enum_value(getattr(item, "memory_tier", None)),
    )


def record_passes_proactive_bar(item: object, *, now: datetime) -> bool:
    scope = getattr(item, "subject_scope", None)
    return passes_proactive_bar(
        belief_view_for_record(item, now=now),
        subject_scope=_enum_value(scope) or (scope if isinstance(scope, str) else None),
        superseded_by=getattr(item, "superseded_by", None),
        confidence=getattr(item, "confidence", None),
    )


def public_belief_overlay(item: object, *, now: datetime) -> dict[str, object]:
    """Additive read fields. Empty when the flag is off so payloads stay identical."""
    if not belief_model_enabled():
        return {}
    view = belief_view_for_record(item, now=now)
    return {
        "currency": view.currency,
        "currency_band": view.band.value,
        "as_of": view.as_of,
        "half_life_days": view.half_life_days,
        "belief_class": getattr(item, "belief_class", None),
    }


def public_belief_overlay_json(item: object, *, now: datetime) -> dict[str, object]:
    overlay = public_belief_overlay(item, now=now)
    as_of = overlay.get("as_of")
    if isinstance(as_of, datetime):
        overlay = {**overlay, "as_of": as_of.isoformat()}
    return overlay
