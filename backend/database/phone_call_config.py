"""
Server-driven config for phone-call free-tier quotas.

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

from typing import Any, Dict, Optional, cast

from config.plan_catalog import PHONE_CALL_PROFILE_DEFAULTS
from database._client import db
from database.cache import get_memory_cache

_CACHE_KEY = "phone_call_config:default"
_CACHE_TTL_SECONDS = 60  # short so flag flips propagate within a minute


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


def _merge_defaults(override: Optional[Dict[str, Any]], defaults: Dict[str, Any]) -> Dict[str, Any]:
    """Overlay a Firestore override onto the hardcoded defaults.

    An explicit ``None`` in the override is preserved (so ops can set
    ``max_duration_seconds: null`` in Firestore to clear the default cap).
    Only keys known to ``defaults`` are honored — unknown override keys are
    ignored so a typo in Firestore can't silently change behavior.
    """
    merged: Dict[str, Any] = dict(defaults)
    if isinstance(override, dict):
        for k in defaults.keys():
            if k in override:
                merged[k] = override[k]
    return merged


def get_free_plan_config() -> Dict[str, Any]:
    return _merge_defaults(_get_config().get("free_plan"), _DEFAULT_FREE_PLAN)


def get_paid_plan_config() -> Dict[str, Any]:
    return _merge_defaults(_get_config().get("paid_plan"), _DEFAULT_PAID_PLAN)


def get_config_for_plan(is_paid: bool) -> Dict[str, Any]:
    return get_paid_plan_config() if is_paid else get_free_plan_config()
