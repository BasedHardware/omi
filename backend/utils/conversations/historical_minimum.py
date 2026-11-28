"""Historical-tier (T1+) rows outside the owner's open: keep the transcript, never generate.

Every automatic trigger that reaches ``process_conversation`` for a historical
row (sync append, enrichment wake, recovery, finalization) stores the row as
completed with its deterministic title, or its existing open-time summary, and
no model, memory, task, app, folder, webhook or notification work. Only
:data:`SUMMARY_TRIGGERS` generate, and those stay summary-only.
"""

from __future__ import annotations

from typing import Any

from config import historical_tier
from models.conversation import Conversation
from utils.conversations.deterministic_minimum import build_deterministic_minimum_structured
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.projection_payload import omit_null_processing_state, strip_client_processing
from utils.conversations.summary_delivery import present

TERMINAL_NO_DERIVED_EFFECTS_FIELD = 'terminal_no_derived_effects'
BLOCKED_REASON = 'historical_on_open'
# Owner actions on this exact row. Their run is summary-only (process_conversation's
# historical seam); everything else is stored without a model call.
SUMMARY_TRIGGERS = frozenset(
    {
        ProcessingTrigger.HISTORICAL_OPEN,
        ProcessingTrigger.FIRST_WEEK_FORCED_CLOSE,
        ProcessingTrigger.USER_REPROCESS,
        ProcessingTrigger.MERGE,
        ProcessingTrigger.BACKLOG_CHOICE,
    }
)


def short_circuits(conversation: Any, trigger: ProcessingTrigger) -> bool:
    return historical_tier.is_historical(conversation) and trigger not in SUMMARY_TRIGGERS


def payload(uid: str, conversation: Conversation) -> dict[str, Any]:
    """The model-free persist for an automatic trigger; mutates ``conversation`` to match.

    The caller (``process_conversation``, the lifecycle owner) marks the row completed first.
    """
    if not present(conversation.structured) and not (conversation.structured.title or '').strip():
        conversation.structured = build_deterministic_minimum_structured(conversation, uid=uid, historical=True)
    conversation.deferred = False
    write = omit_null_processing_state(strip_client_processing(conversation.model_dump()))
    write[TERMINAL_NO_DERIVED_EFFECTS_FIELD] = True
    if not present(conversation.structured):
        write['summary_blocked_reason'] = BLOCKED_REASON
    return write
