"""Who gets agentic meeting notes, and how much they may spend. No I/O beyond env reads.

One function, :func:`plan_notes_agent`, decides both questions so the gate and
the budget can never disagree. Everything that does not qualify keeps the
existing one-shot notes call unchanged.

Controls (read per call, never at import):

- ``CONVERSATION_NOTES_AGENT_ENABLED``: kill switch, default on. ``false``/``off``/``0``
  returns every conversation to the one-shot path.
- ``CONVERSATION_NOTES_AGENT_LOOKUP_EFFICIENCY_ENABLED``: default on. Off restores
  legacy lookup charging, tool schema, prompt, packet and investigation floor.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

FLAG = 'CONVERSATION_NOTES_AGENT_ENABLED'
LOOKUP_EFFICIENCY = 'CONVERSATION_NOTES_AGENT_LOOKUP_EFFICIENCY_ENABLED'

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

# Budget pricing: the gateway's gpt-6-luna card (openai.gpt-6-luna.2026-09-22), in USD per
# million tokens. Images without llm_gateway (pusher) import this module, so the card is
# mirrored here and pinned to cost_rate_cards.yaml by tests/unit/test_notes_agent.py.
PRICE_PROVIDER = 'openai'
PRICE_MODEL = 'gpt-6-luna'
INPUT_USD_PER_MILLION = 0.10
CACHED_INPUT_USD_PER_MILLION = 0.01
OUTPUT_USD_PER_MILLION = 0.60


@dataclass(frozen=True)
class NotesAgentBudget:
    max_turns: int
    max_tool_calls: int
    # Lookups required before a submission is accepted (one rejection, never past the caps).
    min_tool_calls: int = 0
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


def lookup_efficiency_enabled() -> bool:
    return os.getenv(LOOKUP_EFFICIENCY, 'true').strip().lower() not in {'false', 'off', '0', 'no'}


def in_cohort(uid: Optional[str], conversation_id: Optional[str]) -> bool:
    """Permanent full admission (David 2026-11-09 flag rulings)."""
    return True


def budget_for_words(words: int) -> NotesAgentBudget:
    """Value-proportional: longer meetings must investigate more, never past ~15 tools or ~2 cents."""
    if words >= 5000:
        return NotesAgentBudget(max_turns=9, max_tool_calls=15, min_tool_calls=5)
    if words >= AGENT_MIN_WORDS:
        return NotesAgentBudget(max_turns=7, max_tool_calls=10, min_tool_calls=4)
    return NotesAgentBudget(max_turns=5, max_tool_calls=6, min_tool_calls=2)


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
    """Marginal token cost at the conv-structure model's card; an estimate, not an invoice."""
    prompt = max(0, prompt_tokens)
    cached = max(0, min(cached_tokens, prompt))
    output = max(0, completion_tokens)
    return (
        (prompt - cached) * INPUT_USD_PER_MILLION
        + cached * CACHED_INPUT_USD_PER_MILLION
        + output * OUTPUT_USD_PER_MILLION
    ) / 1_000_000
