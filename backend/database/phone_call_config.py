"""
Catalog-backed defaults with a live Firestore overlay for phone-call policy.

The catalog's ``allocation_profiles.phone_calls`` owns the default monthly
allowance and duration for each phone-call profile. Firestore remains a live
operational override at the catalog-declared ``legacy_runtime_override`` path:
known fields are applied, the effective overlay is returned with catalog
revision/SHA metadata, and shared fallback telemetry records its use.

Stored in Firestore so limits can be tuned without a redeploy:

  Collection: phone_call_config
  Document ID: default
  Fields:
    free_plan: {
      monthly_call_limit: int,        # 0 = feature disabled for free users
      max_duration_seconds: int,      # per-call ceiling (None/0 = no cap)
      allowed_countries: list[str],   # ISO-2 codes; empty/missing = no restriction
    }
    paid_plan: {                      # optional; defaults to unlimited if missing
      monthly_call_limit: int | None,
      max_duration_seconds: int | None,
      allowed_countries: list[str],
    }

Setting `free_plan.monthly_call_limit` to 0 makes the feature behave as
paid-only (same as before this config existed).
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, Optional, cast

from config.plan_catalog import (
    CATALOG_REVISION,
    CATALOG_SHA256,
    PHONE_CALL_PROFILE_DEFAULTS,
    PlanType,
    get_plan_definition,
)
from database._client import db
from database.cache import get_memory_cache
from utils.observability.fallback import record_fallback

_CACHE_KEY = "phone_call_config:default"
_CACHE_TTL_SECONDS = 60  # short so flag flips propagate within a minute
_LOGGER = logging.getLogger(__name__)

# A Firestore override is deliberately observable but should not emit one
# warning per phone-call request. The config cache is also 60 seconds, so this
# small bounded map gives operators one event per effective overlay per cache
# lifetime while retaining the live override behavior.
_OVERLAY_TELEMETRY_TTL_SECONDS = _CACHE_TTL_SECONDS
_OVERLAY_TELEMETRY_MAX_ENTRIES = 32
_reported_overlays: dict[tuple[str, tuple[str, ...], bool, str], float] = {}


def _profile_default(name: str) -> Dict[str, Any]:
    profile = PHONE_CALL_PROFILE_DEFAULTS[name]

    def limit_value(field: str) -> Optional[int]:
        limit = cast(Dict[str, Any], profile[field])
        return None if limit['kind'] == 'unlimited' else int(limit['value'])

    return {
        "monthly_call_limit": limit_value('monthly_calls'),
        "max_duration_seconds": limit_value('max_duration_seconds'),
        "allowed_countries": [],
    }


_DEFAULT_FREE_PLAN = _profile_default('free')
_DEFAULT_PAID_PLAN = _profile_default('paid')


def _fetch_config() -> Dict[str, Any]:
    doc = db.collection("phone_call_config").document("default").get()
    if not getattr(doc, "exists", False):
        return {}
    raw: object = doc.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


def _get_config() -> Dict[str, Any]:
    fetched = get_memory_cache().get_or_fetch(_CACHE_KEY, _fetch_config, ttl=_CACHE_TTL_SECONDS)
    return cast(Dict[str, Any], fetched) if isinstance(fetched, dict) else {}


def _phone_call_profile_for_plan(plan: PlanType | str | None) -> str:
    """Resolve phone-call membership from the catalog, with Basic as fallback."""
    try:
        candidate = PlanType.basic if plan is None else PlanType(plan)
        profile = get_plan_definition(candidate).get('phone_calls_profile')
    except (TypeError, ValueError, KeyError):
        profile = 'free'
    return profile if profile in PHONE_CALL_PROFILE_DEFAULTS else 'free'


def is_paid_phone_call_plan(plan: PlanType | str | None) -> bool:
    """Return the catalog-declared phone-call membership for ``plan``."""
    return _phone_call_profile_for_plan(plan) == 'paid'


def _merge_defaults(override: Optional[Dict[str, Any]], defaults: Dict[str, Any]) -> Dict[str, Any]:
    """Overlay a Firestore override onto the catalog-derived defaults.

    An explicit ``None`` in the override is preserved (so ops can set
    ``max_duration_seconds: null`` in Firestore to clear the default cap).
    Only keys known to ``defaults`` are honored. Unknown override keys are
    ignored and surfaced in the effective-overlay metadata so a typo in
    Firestore cannot silently become policy.
    """
    merged: Dict[str, Any] = dict(defaults)
    if isinstance(override, dict):
        for k in defaults.keys():
            if k in override:
                merged[k] = override[k]
    return merged


def _declared_override(override: object, defaults: Dict[str, Any]) -> Dict[str, Any]:
    """Return only known Firestore fields that are declared for this overlay."""
    if not isinstance(override, dict):
        return {}
    return {key: override[key] for key in defaults if key in override}


def _ignored_override_fields(override: object, defaults: Dict[str, Any]) -> tuple[str, ...]:
    """Return Firestore fields that are present but not declared by the profile."""
    if not isinstance(override, dict):
        return ()
    return tuple(sorted(str(key) for key in override if key not in defaults))


def _override_declaration(profile: str) -> tuple[str | None, str | None, str | None]:
    """Return the catalog-declared path, document, and field for an overlay."""
    declaration = PHONE_CALL_PROFILE_DEFAULTS[profile].get('legacy_runtime_override')
    if not isinstance(declaration, str) or not declaration:
        return None, None, None
    document, separator, field = declaration.rpartition('.')
    if not separator or not document or not field:
        return declaration, None, None
    return declaration, document, field


def _overlay_signature(override: Dict[str, Any]) -> str:
    """Hash effective override values without putting values in telemetry labels."""
    try:
        encoded = json.dumps(override, sort_keys=True, separators=(',', ':'), default=repr).encode('utf-8')
    except (TypeError, ValueError):
        encoded = repr(sorted((str(key), repr(value)) for key, value in override.items())).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _record_effective_overlay(
    profile: str,
    fields: tuple[str, ...],
    *,
    has_undeclared_fields: bool,
    signature: str,
) -> None:
    """Emit shared fallback telemetry for a declared Firestore overlay.

    The bounded TTL map prevents a hot call path from emitting one warning per
    request, while the value signature ensures a live change to the same field
    is visible as a new effective overlay.
    """
    key = (profile, fields, has_undeclared_fields, signature)
    now = time.monotonic()

    for stale_key, emitted_at in list(_reported_overlays.items()):
        if now - emitted_at >= _OVERLAY_TELEMETRY_TTL_SECONDS:
            _reported_overlays.pop(stale_key, None)

    previous = _reported_overlays.get(key)
    if previous is not None and now - previous < _OVERLAY_TELEMETRY_TTL_SECONDS:
        return
    if len(_reported_overlays) >= _OVERLAY_TELEMETRY_MAX_ENTRIES:
        oldest_key = min(_reported_overlays, key=_reported_overlays.__getitem__)
        _reported_overlays.pop(oldest_key, None)
    _reported_overlays[key] = now
    record_fallback(
        component='firestore_read',
        from_mode='catalog_phone_call_policy',
        to_mode='firestore_phone_call_overlay' if fields else 'catalog_phone_call_policy',
        reason='policy' if fields else 'malformed_doc',
        outcome='degraded',
        log=_LOGGER,
    )


def _effective_config(profile: str, raw_config: Dict[str, Any]) -> Dict[str, Any]:
    defaults = _DEFAULT_PAID_PLAN if profile == 'paid' else _DEFAULT_FREE_PLAN
    declaration_path, declaration_document, declaration_field = _override_declaration(profile)
    raw_override = raw_config.get(f'{profile}_plan')
    override = _declared_override(raw_override, defaults)
    ignored_fields = _ignored_override_fields(raw_override, defaults)
    has_override = isinstance(raw_override, dict) and bool(raw_override)
    effective = _merge_defaults(override, defaults)
    fields = tuple(sorted(override))
    if has_override:
        _record_effective_overlay(
            profile,
            fields,
            has_undeclared_fields=bool(ignored_fields),
            signature=_overlay_signature(override),
        )

    # Keep the effective policy inspectable: callers can distinguish the
    # versioned catalog default from an operational Firestore overlay without
    # treating Firestore as another plan or membership source.
    effective.update(
        {
            'phone_calls_profile': profile,
            'catalog_revision': CATALOG_REVISION,
            'catalog_sha256': CATALOG_SHA256,
            'effective_overlay': {
                'declared': bool(fields),
                'source': 'firestore' if has_override else 'catalog',
                'declaration_path': declaration_path,
                'document': declaration_document if has_override else None,
                'field_path': declaration_field if has_override else None,
                'profile': profile,
                'fields': list(fields),
                'values': dict(override),
                'ignored_fields': list(ignored_fields),
                'catalog_revision': CATALOG_REVISION,
                'catalog_sha256': CATALOG_SHA256,
            },
        }
    )
    return effective


def get_free_plan_config() -> Dict[str, Any]:
    return _effective_config('free', _get_config())


def get_paid_plan_config() -> Dict[str, Any]:
    return _effective_config('paid', _get_config())


def get_config_for_plan(plan: PlanType | str | None) -> Dict[str, Any]:
    """Resolve config using the catalog's phone-call profile for ``plan``."""
    return _effective_config(_phone_call_profile_for_plan(plan), _get_config())
