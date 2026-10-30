"""Parsing seam for the conv_discard decision.

The model is asked for JSON but regularly answers with Python booleans
(`{"discard": True}`) or the bare `discard = True` line the prompt also asks
for. Both are invalid JSON, so the strict parser raised and the caller's
fail-open kept every conversation the model wanted discarded.
"""

import re
from typing import Any, List, Optional

from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field


class DiscardConversation(BaseModel):
    discard: bool = Field(description="If the conversation should be discarded or not")


# Matches the decision in `{"discard": True}` and in the bare `discard = True`
# line the prompt asks for — neither is valid JSON. Anchored to the whole
# (fence-stripped) reply so prose that merely mentions "discard" — e.g.
# `do_not_discard = True` or a quoted `discard = True` inside a reason string —
# is rejected instead of silently read as a decision.
_CODE_FENCE_PATTERN = re.compile(r'^```\w*\n(.*)\n```$', re.DOTALL)
_DISCARD_DECISION_PATTERN = re.compile(r'^\{?\s*"?discard"?\s*[:=]\s*(true|false)\s*\}?$', re.IGNORECASE)


def parse_discard_decision(text: str) -> Optional[bool]:
    """Read the discard decision out of a non-JSON reply, or None if there is none."""
    stripped = text.strip()
    fence_match = _CODE_FENCE_PATTERN.match(stripped)
    if fence_match:
        stripped = fence_match.group(1).strip()
    match = _DISCARD_DECISION_PATTERN.match(stripped)
    if not match:
        return None
    return match.group(1).lower() == 'true'


class LenientDiscardParser(PydanticOutputParser):
    """PydanticOutputParser that also accepts the shapes conv_discard actually returns.

    A reply carrying no decision at all still raises, so the caller's fail-open
    branch keeps covering genuine garbage.
    """

    def parse_result(self, result: List[Any], *, partial: bool = False) -> Any:
        try:
            return super().parse_result(result, partial=partial)
        except Exception:
            decision = parse_discard_decision(result[0].text if result else '')
            if decision is None:
                raise
            return DiscardConversation(discard=decision)
