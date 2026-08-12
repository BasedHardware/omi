"""Backend-owned AgentPill title + spoken acknowledgement for a kicked-off agent.

Desktop used to build this prompt itself and call Anthropic Haiku through
``/v2/chat/completions``. The prompt, the model and the output contract now live
here, behind ``get_llm('session_titles')``.
"""

import logging
import time
from typing import Any, Optional, cast

from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from utils.llm.usage_tracker import Features, track_usage
from .clients import get_llm

logger = logging.getLogger(__name__)

MAX_QUERY_CHARS = 2_000
MAX_TITLE_CHARS = 40
MAX_ACK_CHARS = 120
MAX_OUTPUT_TOKENS = 120
AGENT_PILL_TITLE_TIMEOUT_SECONDS = 8.0


class AgentPillTitleAck(BaseModel):
    title: str = Field(description="3-5 word imperative Title Case title", default="")
    ack: str = Field(description="Short spoken acknowledgement, max 7 words", default="")


_AGENT_PILL_TITLE_PROMPT = """The user just kicked off a background agent with this request:

"{query}"

Output only structured data matching the format instructions.

RULES:
- title: 3-5 word imperative title in Title Case, no trailing punctuation, no quotes.
- ack: one short spoken acknowledgement, max 7 words, friendly tone
  (e.g. "Got it, building Mario now.").
- Do not invent goals that are not in the request.

{format_instructions}
"""


def generate_agent_pill_title_ack(
    uid: str,
    query: str,
    deadline: float | None = None,
) -> Optional[AgentPillTitleAck]:
    """Return-only title + ack through get_llm('session_titles').

    Returns an empty result for an empty query and ``None`` when the model call or
    parse fails, so callers can fall back to a heuristic title / random ack.

    When ``deadline`` is supplied, the request timeout is capped to the remaining
    time so a queued title job does not outlive the calling Mac client's budget.
    """
    text = (query or "").strip()
    if not text:
        return AgentPillTitleAck(title="", ack="")
    text = text[:MAX_QUERY_CHARS]

    request_timeout = AGENT_PILL_TITLE_TIMEOUT_SECONDS
    if deadline is not None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        request_timeout = min(request_timeout, remaining)

    try:
        parser = PydanticOutputParser(pydantic_object=AgentPillTitleAck)
        prompt = _AGENT_PILL_TITLE_PROMPT.format(
            query=text,
            format_instructions=parser.get_format_instructions(),
        )
        with track_usage(uid, Features.CHAT):
            response = get_llm(
                'session_titles',
                request_timeout=request_timeout,
                max_tokens=MAX_OUTPUT_TOKENS,
                max_retries=0,
                allow_byok=False,
            ).invoke(prompt)
        try:
            parsed = parser.parse(cast(str, cast(Any, response).content))
        except Exception as e:
            logger.error("Error parsing agent pill title/ack: %s", type(e).__name__)
            return None
    except Exception:
        logger.exception("Error generating agent pill title/ack for uid=%s", uid)
        return None

    title = parsed.title.strip()[:MAX_TITLE_CHARS]
    ack = ' '.join(parsed.ack.strip().split()[:7])[:MAX_ACK_CHARS]
    return AgentPillTitleAck(title=title, ack=ack)
