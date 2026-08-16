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
# line the prompt asks for — neither is valid JSON.
_DISCARD_DECISION_PATTERN = re.compile(r'discard\W{0,4}(true|false)\b', re.IGNORECASE)


def parse_discard_decision(text: str) -> Optional[bool]:
    """Read the discard decision out of a non-JSON reply, or None if there is none."""
    matches = _DISCARD_DECISION_PATTERN.findall(text)
    if not matches:
        return None
    return matches[-1].lower() == 'true'


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
