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
from utils.memory.belief_source_policy import has_verified_owner_authorship, original_evidence_time

MEMORY_BELIEF_MODEL_ENABLED_ENV = "MEMORY_BELIEF_MODEL_ENABLED"
MEMORY_BELIEF_AUTOMATION_PAUSED_ENV = "MEMORY_BELIEF_AUTOMATION_PAUSED"

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
TEMPORAL_READ_VIEWS = frozenset({"released", "useful_now", "history", "all"})


class CurrencyBand(str, Enum):
    current = "current"
    fading = "fading"
    history = "history"


@dataclass(frozen=True)
class BeliefView:
    currency: Optional[float]
    band: Optional[CurrencyBand]
    as_of: datetime
    half_life_days: Optional[float]
    last_evidenced_at: datetime


def belief_model_enabled() -> bool:
    """Deployment-wide flag. Unset and any value other than true fail closed to off."""
    return os.getenv(MEMORY_BELIEF_MODEL_ENABLED_ENV, "false").lower() == "true"


def belief_automation_enabled() -> bool:
    """Whether belief-producing jobs and admission paths may run.

    Read-side overlays remain available while the independent automation pause
    is active, so an operator can stop writes/backfills without removing the
    beta read contract from clients.
    """
    return belief_model_enabled() and os.getenv(MEMORY_BELIEF_AUTOMATION_PAUSED_ENV, "false").lower() != "true"


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
    if user_asserted and not belief_class:
        # Manual adoption without a class is authoritative evidence, but it
        # does not contain enough temporal information to claim currentness.
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
    """Return (belief_class, half_life_days) for a new claim.

    Manual adoption is an authority signal, not a promise that the claim is
    timeless.  A supplied class or explicit horizon therefore remains in
    force for user-asserted memories.  Missing classification stays unknown;
    it is never silently promoted to ``identity``.
    """
    resolved_class = belief_class if belief_class is not None and belief_class in HALF_LIFE_DAYS_BY_CLASS else None
    if half_life_days_override is not None:
        if half_life_days_override <= 0:
            raise ValueError("half_life_days must be positive when set")
        return resolved_class, half_life_days_override
    if resolved_class is None:
        return None, None
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


def currency_band(currency: Optional[float]) -> Optional[CurrencyBand]:
    if currency is None:
        return None
    if currency > CURRENT_BAND_MIN:
        return CurrencyBand.current
    if currency >= FADING_BAND_MIN:
        return CurrencyBand.fading
    return CurrencyBand.history


def normalize_temporal_read_view(value: Optional[str]) -> str:
    """Normalize the additive list view selector.

    ``released`` is deliberately the default so older clients and callers
    retain the shipped list contract when they omit the new query parameter.
    """
    normalized = (value or "released").strip().lower()
    if normalized not in TEMPORAL_READ_VIEWS:
        raise ValueError(f"unsupported memory read view: {value}")
    return normalized


def memory_use_suppressed(item: object) -> bool:
    """Read the canonical owner-use suppression without interpreting confidence."""
    arguments = getattr(item, "arguments", None)
    use = arguments.get("memory_use") if isinstance(arguments, Mapping) else None
    return isinstance(use, Mapping) and use.get("suppressed") is True


def belief_classification_known(item: object) -> bool:
    """Whether a record carries an explicit class or stored horizon."""
    stored_half_life = getattr(item, "half_life_days", None)
    belief_class = getattr(item, "belief_class", None)
    return stored_half_life is not None or (belief_class is not None and belief_class in HALF_LIFE_DAYS_BY_CLASS)


def temporal_view_allows_record(
    item: object,
    *,
    view: str,
    now: datetime,
    include_archive: bool = False,
) -> bool:
    """Apply the shared temporal presentation policy to one decoded record.

    This is a presentation filter only.  It never mutates lifecycle state and
    never treats a missing class as current.  ``released`` leaves historical
    lifecycle filtering to the existing owner; the other views use the
    read-side currency bands while retaining the existing access fences.
    """
    normalized = normalize_temporal_read_view(view)
    tier = _enum_value(getattr(item, "tier", None)) or _enum_value(getattr(item, "memory_tier", None))
    status = _enum_value(getattr(item, "status", None)) or _enum_value(getattr(item, "ledger_status", None))
    # Legacy/non-ledger projections carry lineage closure on the public row
    # without a separate status field. Treat that retained version as history
    # for the temporal presentation policy instead of guessing it is current.
    if status is None and getattr(item, "superseded_by", None):
        status = "superseded"
    # Suppression is a default-use fence.  An explicit owner history read may
    # inspect the retained record and its suppression state; only useful-now
    # and automated consumers must honor the fence.
    suppressed = memory_use_suppressed(item)
    if suppressed and normalized == "useful_now":
        return False
    if getattr(item, "user_review", None) is False:
        return False
    if getattr(item, "invalid_at", None) is not None and normalized == "useful_now":
        return False
    if getattr(item, "invalid_at", None) is not None and normalized == "history":
        return True
    if tier == "archive":
        # Archive is never part of the everyday useful-now view, even when a
        # caller also holds the explicit archive capability.  History/all may
        # opt in through the existing include_archive authorization.
        if normalized == "useful_now" or not include_archive:
            return False
    if normalized == "released":
        return True
    if status in {"tombstoned", "hidden"}:
        return False
    assessment = belief_view_for_record(item, now=now)
    if normalized == "useful_now":
        # Unclassified rows are inspectable on history/all, never the current
        # working set — matching record_passes_proactive_bar and the overlay
        # that refuses to mint a current band without a class.
        if not belief_classification_known(item):
            return False
        return assessment.band in {CurrencyBand.current, CurrencyBand.fading} or assessment.band is None
    if normalized == "history":
        # History is the explicit dated/retained view: current facts stay in
        # useful-now, while expired claims, unknown legacy rows, superseded
        # records, and owner-suppressed records remain inspectable.
        if suppressed or status == "superseded" or not belief_classification_known(item):
            return True
        return assessment.band in {CurrencyBand.fading, CurrencyBand.history}
    # ``all`` is the explicit owner-visible superset and may include archive
    # only when the caller has that grant.
    return True


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
    suppressed: bool = False,
) -> bool:
    """JIT / proactive nudges: current band, user subject, truth not contradicted."""
    return (
        view.band == CurrencyBand.current
        and is_user_subject(subject_scope)
        and not is_contradicted(superseded_by=superseded_by, confidence=confidence)
        and not suppressed
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
    captured_at = original_evidence_time(item)
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
    if not belief_classification_known(item):
        return False
    if getattr(item, "user_review", None) is False:
        return False
    promotion = getattr(item, "promotion", None)
    if isinstance(promotion, Mapping) and promotion.get("user_review") is False:
        return False
    if not has_verified_owner_authorship(item):
        return False
    scope = getattr(item, "subject_scope", None)
    return passes_proactive_bar(
        belief_view_for_record(item, now=now),
        subject_scope=_enum_value(scope) or (scope if isinstance(scope, str) else None),
        superseded_by=getattr(item, "superseded_by", None),
        confidence=getattr(item, "confidence", None),
        suppressed=memory_use_suppressed(item),
    )


def public_belief_overlay(item: object, *, now: datetime) -> dict[str, object]:
    """Additive read fields. Empty when the flag is off so payloads stay identical."""
    if not belief_model_enabled():
        return {}
    view = belief_view_for_record(item, now=now)
    classified = belief_classification_known(item)
    return {
        "currency": view.currency if classified else None,
        "currency_band": view.band.value if classified and view.band is not None else None,
        "as_of": view.as_of,
        "half_life_days": view.half_life_days,
        "belief_class": getattr(item, "belief_class", None),
        "belief_computed_at": now,
    }


def public_belief_overlay_json(item: object, *, now: datetime) -> dict[str, object]:
    overlay = public_belief_overlay(item, now=now)
    for field in ("as_of", "belief_computed_at"):
        value = overlay.get(field)
        if isinstance(value, datetime):
            overlay = {**overlay, field: value.isoformat()}
    return overlay
