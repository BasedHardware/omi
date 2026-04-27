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

from typing import Optional

from database._client import db
from database.cache import get_memory_cache

_CACHE_KEY = "phone_call_config:default"
_CACHE_TTL_SECONDS = 60  # short so flag flips propagate within a minute

_DEFAULT_FREE_PLAN = {
    "monthly_call_limit": 0,
    "max_duration_seconds": 300,
    "allowed_countries": [],
}
_DEFAULT_PAID_PLAN = {
    "monthly_call_limit": None,
    "max_duration_seconds": None,
    "allowed_countries": [],
}


def _fetch_config() -> dict:
    doc = db.collection("phone_call_config").document("default").get()
    return doc.to_dict() if doc.exists else {}


def _get_config() -> dict:
    return get_memory_cache().get_or_fetch(_CACHE_KEY, _fetch_config, ttl=_CACHE_TTL_SECONDS) or {}


def _merge_defaults(override: Optional[dict], defaults: dict) -> dict:
    """Overlay a Firestore override onto the hardcoded defaults.

    An explicit ``None`` in the override is preserved (so ops can set
    ``max_duration_seconds: null`` in Firestore to clear the default cap).
    Only keys known to ``defaults`` are honored — unknown override keys are
    ignored so a typo in Firestore can't silently change behavior.
    """
    merged = dict(defaults)
    if isinstance(override, dict):
        for k in defaults.keys():
            if k in override:
                merged[k] = override[k]
    return merged


def get_free_plan_config() -> dict:
    return _merge_defaults(_get_config().get("free_plan"), _DEFAULT_FREE_PLAN)


def get_paid_plan_config() -> dict:
    return _merge_defaults(_get_config().get("paid_plan"), _DEFAULT_PAID_PLAN)


def get_config_for_plan(is_paid: bool) -> dict:
    return get_paid_plan_config() if is_paid else get_free_plan_config()
