"""
Server-driven config for per-plan caps. Stored in Firestore so caps can be
tuned without a redeploy:

  Collection: app_config
  Document ID: plan_caps
  Fields:
    plans:
      basic:     {chat_questions_per_month: 30, transcription_seconds: 72000, ...}
      lite:      {chat_questions_per_month: 100, transcription_seconds: 90000}
      plus:      {chat_questions_per_month: 300, transcription_seconds: 240000}
      max:       {chat_questions_per_month: null, transcription_seconds: null}
      unlimited: {chat_questions_per_month: 200, transcription_seconds: null}  # legacy Neo
      operator:  {chat_questions_per_month: 500, transcription_seconds: null}
      architect: {chat_cost_usd_per_month: 400.0, transcription_seconds: null}
    superwall_product_map:                  # product_id (App Store / Play) → PlanType value
      "com.omi.app.lite_monthly": "lite"
      "com.omi.app.lite_yearly":  "lite"
      "com.omi.app.plus_monthly": "plus"
      ...
    platform_overrides:                     # forward-compat for desktop-only extras
      desktop:
        # plan_id → {field: override_value}  — empty for now

A ``null`` value means "unlimited / no cap". Missing keys fall back to the
env-driven defaults already wired into ``utils.subscription`` so existing
behavior is preserved when the doc is absent or stale.
"""

import os
from typing import Optional

from database._client import db
from models.users import PlanType, PlanLimits

_CACHE_KEY = "plan_caps_config:default"
_CACHE_TTL_SECONDS = 60  # short so cap tweaks propagate within a minute


def _default_caps_for(plan: PlanType) -> dict:
    """Hardcoded fallback caps per plan, mirroring the pre-refactor
    ``get_plan_limits``. Reads env vars at call time so live tweaks (and
    test monkeypatches) flow through without a module reload.
    """
    if plan == PlanType.unlimited:
        return {
            'chat_questions_per_month': int(os.getenv('NEO_CHAT_QUESTIONS_PER_MONTH', '200')),
            'chat_cost_usd_per_month': None,
            'transcription_seconds': None,
            'words_transcribed': None,
            'insights_gained': None,
            'memories_created': None,
        }
    if plan == PlanType.operator:
        return {
            'chat_questions_per_month': int(os.getenv('OPERATOR_CHAT_QUESTIONS_PER_MONTH', '500')),
            'chat_cost_usd_per_month': None,
            'transcription_seconds': None,
            'words_transcribed': None,
            'insights_gained': None,
            'memories_created': None,
        }
    if plan == PlanType.architect:
        return {
            'chat_questions_per_month': None,
            'chat_cost_usd_per_month': float(os.getenv('ARCHITECT_CHAT_COST_USD_PER_MONTH', '400.0')),
            'transcription_seconds': None,
            'words_transcribed': None,
            'insights_gained': None,
            'memories_created': None,
        }
    # PlanType.basic and any other (defensive) plan fall through to free-tier caps.
    basic_minutes = int(os.getenv('BASIC_TIER_MINUTES_LIMIT_PER_MONTH', '0'))
    return {
        'chat_questions_per_month': int(os.getenv('FREE_CHAT_QUESTIONS_PER_MONTH', '30')),
        'chat_cost_usd_per_month': None,
        'transcription_seconds': basic_minutes * 60,
        'words_transcribed': int(os.getenv('BASIC_TIER_WORDS_TRANSCRIBED_LIMIT_PER_MONTH', '0')),
        'insights_gained': int(os.getenv('BASIC_TIER_INSIGHTS_GAINED_LIMIT_PER_MONTH', '0')),
        'memories_created': int(os.getenv('BASIC_TIER_MEMORIES_CREATED_LIMIT_PER_MONTH', '0')),
    }


def _fetch_config() -> dict:
    doc = db.collection('app_config').document('plan_caps').get()
    return doc.to_dict() if doc.exists else {}


def _get_config() -> dict:
    # Lazy import keeps this module test-stub friendly — callers that mock out
    # Firestore don't also need to mock out Redis (database.cache pulls in
    # redis_db at import time).
    from database.cache import get_memory_cache

    return get_memory_cache().get_or_fetch(_CACHE_KEY, _fetch_config, ttl=_CACHE_TTL_SECONDS) or {}


def _merge_with_defaults(override: Optional[dict], defaults: dict) -> dict:
    """Overlay a Firestore override onto hardcoded defaults.

    An explicit ``None`` in ``override`` is preserved (so ops can clear a cap by
    setting e.g. ``transcription_seconds: null`` in Firestore). Only keys known
    to ``defaults`` are honored — typos in Firestore can't silently change behavior.
    """
    merged = dict(defaults)
    if isinstance(override, dict):
        for k in defaults.keys():
            if k in override:
                merged[k] = override[k]
    return merged


def get_plan_caps(plan: PlanType, platform: Optional[str] = None) -> dict:
    """Return effective caps for ``plan`` (with optional per-platform override).

    Resolution order (highest precedence first):
      1. ``app_config/plan_caps.platform_overrides[platform][plan.value]``
      2. ``app_config/plan_caps.plans[plan.value]``
      3. Hardcoded fallback (``_default_caps_for``)

    The result always carries the same key set so callers can read fields
    without ``.get()`` defaults.
    """
    defaults = _default_caps_for(plan)
    cfg = _get_config()

    plans_override = (cfg.get('plans') or {}).get(plan.value)
    merged = _merge_with_defaults(plans_override, defaults)

    if platform:
        platform_override = ((cfg.get('platform_overrides') or {}).get(platform) or {}).get(plan.value)
        merged = _merge_with_defaults(platform_override, merged)

    return merged


def get_plan_limits_from_config(plan: PlanType, platform: Optional[str] = None) -> PlanLimits:
    """Return a ``PlanLimits`` model populated from ``get_plan_caps``."""
    caps = get_plan_caps(plan, platform)
    return PlanLimits(
        transcription_seconds=caps.get('transcription_seconds'),
        words_transcribed=caps.get('words_transcribed'),
        insights_gained=caps.get('insights_gained'),
        memories_created=caps.get('memories_created'),
        chat_questions_per_month=caps.get('chat_questions_per_month'),
        chat_cost_usd_per_month=caps.get('chat_cost_usd_per_month'),
    )


def get_superwall_product_map() -> dict:
    """Return the App Store / Play product_id → PlanType-value map.

    Used by the Superwall webhook handler to resolve product purchases. Tunable
    via Firestore so new SKUs don't need a redeploy.
    """
    return _get_config().get('superwall_product_map') or {}
