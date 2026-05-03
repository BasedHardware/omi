"""Decisions extraction (v0 lens).

Extracts a list of explicit decisions from a meeting transcript, each tied
back (by positional index) to action items already extracted from the same
conversation. Used by `process_conversation` for allowlisted uids and by
`scripts/decisions_preflight.py` for offline evaluation — both call
`extract_decisions` so the prompt is defined exactly once here.
"""

import logging
import uuid
from typing import List

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from models.conversation import Decision, Structured
from utils.log_sanitizer import sanitize

from .clients import llm_medium_experiment

logger = logging.getLogger(__name__)


# Canonical Decisions extraction prompt. Also used by the preflight script
# (do not duplicate; both paths import this constant).
DECISIONS_PROMPT = '''You are extracting decisions from a meeting transcript.

A decision is an explicit agreement reached during the meeting — "we will use Postgres,"
"Sarah owns the audit," "we're shipping Friday." It is NOT:
  - a task assignment without an underlying agreement (those are action items)
  - a hypothetical ("we could maybe...")
  - small talk or filler
  - a recap of a prior decision

For each decision, output:
  - id: a uuid4 hex string (8-32 chars, alphanumeric)
  - statement: one sentence, max 200 chars, in the participants' own words where possible
  - owner_name: the person primarily accountable, or null if unstated
  - due_at: ISO 8601 datetime if stated, else null
  - status: "open" by default; "blocked" only if the transcript explicitly says so
  - open_questions: up to 5 unresolved sub-questions raised during this decision
  - related_action_item_ids: array of integer indexes into the action_items list provided below
    that exist BECAUSE OF this decision. Indexes only — do not invent new actions.

If the meeting produced NO real decisions (e.g., a casual catch-up, a Q&A), output an empty array.
Do NOT invent decisions to fill space. An empty array is the correct answer for casual meetings.

Provided:
  transcript: {transcript}
  action_items: {action_items_list}

{format_instructions}

Output: JSON only, no preamble.'''


class DecisionsExtraction(BaseModel):
    """Pydantic wrapper for the LLM output parser."""

    decisions: List[Decision] = Field(default=[], description="Extracted decisions; empty list if none.")


def extract_decisions(structured: Structured, transcript: str, conversation_id: str = "unknown") -> List[Decision]:
    """Extract a list of Decisions from the transcript, validated against `structured.action_items`.

    Args:
        structured: The already-extracted Structured for the conversation. We
            reference the action_items list by positional index — caller must
            not reorder it after this call.
        transcript: Plain-text transcript of the conversation.
        conversation_id: Used only for logging context.

    Returns:
        List of Decision objects. Returns [] on parse error, model error, or
        when more than 20% of `related_action_item_ids` across the response
        are out-of-range (high-hallucination signal).
    """
    action_items_list = [
        {"index": i, "description": item.description} for i, item in enumerate(structured.action_items)
    ]

    parser = PydanticOutputParser(pydantic_object=DecisionsExtraction)
    prompt = ChatPromptTemplate.from_messages([('system', DECISIONS_PROMPT)])
    chain = prompt | llm_medium_experiment.bind(prompt_cache_key="omi-extract-decisions") | parser

    try:
        response = chain.invoke(
            {
                'transcript': transcript,
                'action_items_list': action_items_list,
                'format_instructions': parser.get_format_instructions(),
            }
        )
    except ValueError as e:
        # PydanticOutputParser raises ValueError / OutputParserException for malformed JSON.
        payload = str(e)
        logger.error(
            f"[Decisions] parse failed conv={conversation_id} payload_len={len(payload)} "
            f"sample={sanitize(payload[:200])}"
        )
        return []
    except Exception as e:
        logger.error(f"[Decisions] extraction failed conv={conversation_id} error={type(e).__name__}: {str(e)}")
        raise

    decisions = response.decisions or []
    n_action_items = len(structured.action_items)

    # Validate related_action_item_ids: drop out-of-range indexes; track totals.
    total_indexes = 0
    invalid_indexes = 0
    for decision in decisions:
        ids = decision.related_action_item_ids or []
        total_indexes += len(ids)
        valid_ids = [i for i in ids if isinstance(i, int) and 0 <= i < n_action_items]
        invalid_indexes += len(ids) - len(valid_ids)
        decision.related_action_item_ids = valid_ids
        # Defensively replace LLM-provided id with a backend-generated uuid hex.
        decision.id = uuid.uuid4().hex

    if total_indexes > 0 and (invalid_indexes / total_indexes) > 0.20:
        logger.error(
            f"[Decisions] high-hallucination conv={conversation_id} " f"invalid={invalid_indexes}/{total_indexes}"
        )
        return []

    return decisions
