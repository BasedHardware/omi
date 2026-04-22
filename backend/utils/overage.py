"""Usage-based overage billing for chat.

Every paid plan participates — we never ask a paying user to upgrade, we bill
the excess.

  - Operator (500 included chat questions / mo): overage on questions past cap.
  - Neo / Unlimited (200 included): overage on questions past cap.
  - Architect ($400 included AI compute / mo): overage on cost past cap.
  - Free users still hard-capped (no payment method on file).
  - BYOK users bypass everything (handled in ``utils.subscription.enforce_chat_quota``).

True costs are tracked on every chat call via
``database.llm_usage.record_llm_usage_bucket`` → ``desktop_chat.cost_usd``.
This module reads those numbers rather than maintaining a parallel counter.

**Billing attribution**
  - Question-based plans (Operator, Neo): cost is attributed proportionally —
    ``overage = (excess_q / total_q) × total_real_cost × markup``. Approximate
    (a user who does cheap Qs then expensive Qs underbills), but fair enough.
  - Cost-based plans (Architect): exact. ``overage = (real_cost - cap) × markup``.
"""

import os
from typing import Optional

from database import user_usage as user_usage_db
from models.users import PlanType
from utils.subscription import (
    ARCHITECT_CHAT_COST_USD_PER_MONTH,
    NEO_CHAT_QUESTIONS_PER_MONTH,
    OPERATOR_CHAT_QUESTIONS_PER_MONTH,
)

# Markup applied to raw provider cost before charging the user.
# 1.15 = 15 % on top of true cost (covers variance + infra).
OVERAGE_MARKUP_MULTIPLIER = float(os.getenv('OVERAGE_MARKUP_MULTIPLIER', '1.15'))

# Per-1M-token reference rates shown in the explainer UI. These are NOT used
# for live computation — live cost is taken from the already-tracked
# `desktop_chat.cost_usd` which the LLM clients compute per-call from
# actual provider token counts. Rates here are purely informational.
PROVIDER_REFERENCE_RATES = {
    'claude_sonnet_input_per_mtok': 3.00,
    'claude_sonnet_output_per_mtok': 15.00,
    'gemini_flash_input_per_mtok': 0.30,
    'gemini_flash_output_per_mtok': 2.50,
    'gpt_4_1_mini_input_per_mtok': 0.40,
    'gpt_4_1_mini_output_per_mtok': 1.60,
    'deepgram_nova_per_min': 0.0043,
}

OVERAGE_EXPLAINER_TITLE = "What happens past your monthly limit?"

OVERAGE_EXPLAINER_BODY = (
    "Your paid plan includes a monthly AI-usage allowance. If you go over, Omi "
    "doesn't cut you off — you stay fully functional and we charge only for "
    "the extra usage, billed to the card on file at the end of your cycle.\n\n"
    "How the charge is computed:\n"
    "  • We sum the real provider cost (Claude, Gemini, Deepgram, etc.) of the "
    "usage past your included allowance.\n"
    "  • We add a {markup_pct:.0f}% buffer on top to cover infra and pricing variance.\n"
    "  • That's it — no surge pricing, no hidden fees.\n\n"
    "A typical chat question costs roughly $0.01–$0.05 of real compute. Heavy "
    "RAG or agentic questions cost a bit more.\n\n"
    "Prefer predictable billing? Bring your own API keys in Settings → Developer "
    "API Keys and pay providers directly — Omi is free when BYOK is active."
)


def build_explainer_text() -> str:
    return OVERAGE_EXPLAINER_BODY.format(
        markup_pct=(OVERAGE_MARKUP_MULTIPLIER - 1.0) * 100.0,
    )


def _plan_included_questions(plan: PlanType) -> Optional[int]:
    """Included chat questions for question-based overage plans."""
    if plan == PlanType.operator:
        return OPERATOR_CHAT_QUESTIONS_PER_MONTH
    if plan == PlanType.unlimited:
        return NEO_CHAT_QUESTIONS_PER_MONTH
    return None


def _plan_included_cost_usd(plan: PlanType) -> Optional[float]:
    """Included monthly AI-compute dollars for cost-based overage plans."""
    if plan == PlanType.architect:
        return ARCHITECT_CHAT_COST_USD_PER_MONTH
    return None


def is_overage_plan(plan: PlanType) -> bool:
    """True if this plan bills overage past its included allowance."""
    return _plan_included_questions(plan) is not None or _plan_included_cost_usd(plan) is not None


def get_user_overage(uid: str, plan: PlanType) -> dict:
    """Current-month overage snapshot for *uid* on *plan*.

    Returns a dict with:
      - included_questions: plan's question allowance (or None)
      - included_cost_usd:  plan's compute-dollar allowance (or None)
      - used_questions:     questions used this month
      - excess_questions:   max(0, used_q - included_q) for question plans
      - real_cost_usd:      provider cost for entire month (from tracked data)
      - overage_usd:        accrued overage charge with markup (0 if under cap)
      - markup_multiplier:  the multiplier applied
      - reset_at:           unix ts when the monthly bucket rolls over
    """
    included_q = _plan_included_questions(plan)
    included_cost = _plan_included_cost_usd(plan)
    usage = user_usage_db.get_monthly_chat_usage(uid)
    used_q = int(usage.get('questions', 0))
    real_cost = float(usage.get('cost_usd', 0.0))
    reset_at = usage.get('reset_at')

    overage_usd = 0.0
    excess_q = 0
    if included_q is not None and used_q > included_q and used_q > 0:
        # Question-based: attribute cost proportionally.
        excess_q = used_q - included_q
        overage_usd = round((excess_q / used_q) * real_cost * OVERAGE_MARKUP_MULTIPLIER, 4)
    elif included_cost is not None and real_cost > included_cost:
        # Cost-based: exact excess × markup.
        overage_usd = round((real_cost - included_cost) * OVERAGE_MARKUP_MULTIPLIER, 4)

    return {
        'included_questions': included_q,
        'included_cost_usd': included_cost,
        'used_questions': used_q,
        'excess_questions': excess_q,
        'real_cost_usd': round(real_cost, 4),
        'overage_usd': overage_usd,
        'markup_multiplier': OVERAGE_MARKUP_MULTIPLIER,
        'reset_at': reset_at,
    }
