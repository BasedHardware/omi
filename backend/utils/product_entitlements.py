"""Product-scoped free-tier limits (orthogonal to PlanType + X-App-Platform).

Context for Claude free users get a separate STT pool and zero chat questions.
Missing / unknown product keeps existing plan limits (Desktop / mobile unchanged).
"""

from __future__ import annotations

import os
from typing import Optional

from database.user_product import normalize_product
from models.users import PlanLimits, PlanType

CONTEXT_FOR_CLAUDE_PRODUCT = 'context-for-claude'

# Separate free STT pool for Context (env-overridable). Desktop free keeps BASIC_TIER_*.
CONTEXT_FOR_CLAUDE_BASIC_TIER_MINUTES_LIMIT_PER_MONTH = int(
    os.getenv('CONTEXT_FOR_CLAUDE_BASIC_TIER_MINUTES_LIMIT_PER_MONTH', '3000')
)
CONTEXT_FOR_CLAUDE_BASIC_TIER_MONTHLY_SECONDS_LIMIT = CONTEXT_FOR_CLAUDE_BASIC_TIER_MINUTES_LIMIT_PER_MONTH * 60
CONTEXT_FOR_CLAUDE_FREE_CHAT_QUESTIONS_PER_MONTH = int(
    os.getenv('CONTEXT_FOR_CLAUDE_FREE_CHAT_QUESTIONS_PER_MONTH', '0')
)

# Hourly / monthly usage field for the Context STT pool (not shared with Desktop).
CONTEXT_TRANSCRIPTION_SECONDS_FIELD = 'transcription_seconds_context_for_claude'

# Warm this many most-recent Context stubs when Claude touches MCP (demand-side).
CONTEXT_RECENT_ENRICH_N = int(os.getenv('CONTEXT_FOR_CLAUDE_RECENT_ENRICH_N', '3'))


def is_context_for_claude(app_product: Optional[str]) -> bool:
    return normalize_product(app_product) == CONTEXT_FOR_CLAUDE_PRODUCT


def apply_product_free_limits(plan: PlanType, limits: PlanLimits, app_product: Optional[str]) -> PlanLimits:
    """Overlay Context free caps onto basic-plan limits. Paid plans unchanged."""
    if not is_context_for_claude(app_product) or plan != PlanType.basic:
        return limits
    return PlanLimits(
        transcription_seconds=CONTEXT_FOR_CLAUDE_BASIC_TIER_MONTHLY_SECONDS_LIMIT,
        words_transcribed=limits.words_transcribed,
        insights_gained=limits.insights_gained,
        chat_questions_per_month=CONTEXT_FOR_CLAUDE_FREE_CHAT_QUESTIONS_PER_MONTH,
        chat_cost_usd_per_month=limits.chat_cost_usd_per_month,
    )


def transcription_usage_field(app_product: Optional[str]) -> str:
    """Which monthly counter to read/write for STT entitlement."""
    if is_context_for_claude(app_product):
        return CONTEXT_TRANSCRIPTION_SECONDS_FIELD
    return 'transcription_seconds'
