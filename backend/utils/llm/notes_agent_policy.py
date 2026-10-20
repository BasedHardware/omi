"""Who gets agentic meeting notes, and how much they may spend. No I/O beyond env reads.

One function, :func:`plan_notes_agent`, decides both questions so the gate and
the budget can never disagree. Everything that does not qualify keeps the
existing one-shot notes call unchanged.

Controls (read per call, never at import):

- ``CONVERSATION_NOTES_AGENT_ENABLED``: kill switch, default on. ``false``/``off``/``0``
  returns every conversation to the one-shot path.
- ``CONVERSATION_NOTES_AGENT_PERCENT``: stable conversation-hash cohort, default 100.
- ``CONVERSATION_NOTES_AGENT_UID_ALLOWLIST``: comma-separated UIDs always in the cohort.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Optional

from llm_gateway.gateway.accounting import rate_card_for

FLAG = 'CONVERSATION_NOTES_AGENT_ENABLED'
PERCENT = 'CONVERSATION_NOTES_AGENT_PERCENT'
UID_ALLOWLIST = 'CONVERSATION_NOTES_AGENT_UID_ALLOWLIST'

# A conversation this long is worth an agent on words alone.
AGENT_MIN_WORDS = 1500
# Meeting evidence (calendar, call screen, several capture sources) earns the agent
# from here: below it there is too little speech for context to change the notes.
MEETING_MIN_WORDS = 300

MAX_COST_USD = 0.02
DEADLINE_SECONDS = 120.0
# After this much wall time the next turn must submit, so a slow provider still
# leaves room for the final call inside the deadline.
FORCE_SUBMIT_AFTER_SECONDS = 75.0

# Price the budget with the conv-structure model's card (gpt-6-luna, per million tokens).
PRICE_PROVIDER = 'openai'
PRICE_MODEL = 'gpt-6-luna'
_FALLBACK_INPUT, _FALLBACK_CACHED, _FALLBACK_OUTPUT = 0.10, 0.01, 0.60


@dataclass(frozen=True)
class NotesAgentBudget:
    max_turns: int
    max_tool_calls: int
    max_cost_usd: float = MAX_COST_USD
    deadline_seconds: float = DEADLINE_SECONDS
    force_submit_after_seconds: float = FORCE_SUBMIT_AFTER_SECONDS


@dataclass(frozen=True)
class NotesAgentDecision:
    run: bool
    reason: str
    budget: Optional[NotesAgentBudget] = None


def enabled() -> bool:
    return os.getenv(FLAG, 'true').strip().lower() not in {'false', 'off', '0', 'no'}


def _percent() -> int:
    raw = os.getenv(PERCENT, '').strip()
    if not raw:
        return 100
    try:
        return max(0, min(100, int(raw)))
    except ValueError:
        # An unreadable ramp value must not silently widen the cohort.
        return 0


def in_cohort(uid: Optional[str], conversation_id: Optional[str]) -> bool:
    allowlist = {item.strip() for item in os.getenv(UID_ALLOWLIST, '').split(',') if item.strip()}
    if uid and uid in allowlist:
        return True
    percent = _percent()
    if percent >= 100:
        return True
    if percent <= 0 or not conversation_id:
        return False
    bucket = int(hashlib.sha256(f'notes-agent:{conversation_id}'.encode()).hexdigest()[:8], 16) % 100
    return bucket < percent


def budget_for_words(words: int) -> NotesAgentBudget:
    """Value-proportional: longer meetings may look up more, never past ~15 tools or ~2 cents."""
    if words >= 5000:
        return NotesAgentBudget(max_turns=9, max_tool_calls=15)
    if words >= AGENT_MIN_WORDS:
        return NotesAgentBudget(max_turns=7, max_tool_calls=10)
    return NotesAgentBudget(max_turns=5, max_tool_calls=6)


def plan_notes_agent(
    *,
    uid: Optional[str],
    conversation_id: Optional[str],
    words: int,
    has_calendar: bool = False,
    has_call_screen: bool = False,
    capture_sources: int = 1,
    transport_ready: bool = True,
) -> NotesAgentDecision:
    """The one gate and budget for agentic notes.

    ``transport_ready`` is false when the notes model cannot carry tools (BYOK,
    direct-provider routing): those conversations keep the one-shot call.
    """
    if not enabled():
        return NotesAgentDecision(False, 'disabled')
    if not transport_ready:
        return NotesAgentDecision(False, 'transport')
    if words >= AGENT_MIN_WORDS:
        reason = 'long_transcript'
    elif words >= MEETING_MIN_WORDS and capture_sources >= 2:
        reason = 'multi_source'
    elif words >= MEETING_MIN_WORDS and (has_calendar or has_call_screen):
        reason = 'meeting_evidence'
    else:
        return NotesAgentDecision(False, 'below_threshold')
    if not in_cohort(uid, conversation_id):
        return NotesAgentDecision(False, 'cohort')
    return NotesAgentDecision(True, reason, budget_for_words(words))


def estimate_cost_usd(prompt_tokens: int, cached_tokens: int, completion_tokens: int) -> float:
    """Marginal token cost from the gateway rate card; an estimate, not an invoice."""
    prompt = max(0, prompt_tokens)
    cached = max(0, min(cached_tokens, prompt))
    output = max(0, completion_tokens)
    try:
        card = rate_card_for(PRICE_PROVIDER, PRICE_MODEL)
    except Exception:  # noqa: BLE001 - the estimate falls back to the documented card
        card = None
    if card is not None:
        rates = card.effective_rates(prompt)
        micro = (
            (prompt - cached) * rates.input_micro_usd_per_million
            + cached * rates.cached_input_micro_usd_per_million
            + output * rates.output_micro_usd_per_million
        ) / 1_000_000
        return micro / 1_000_000
    return ((prompt - cached) * _FALLBACK_INPUT + cached * _FALLBACK_CACHED + output * _FALLBACK_OUTPUT) / 1_000_000
