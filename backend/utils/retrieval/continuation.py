"""Chat continuation protocol for resuming truncated or cut-off responses.

Ensures that when a user sends an unambiguous continuation command (e.g. "Continue",
"keep going", "please continue") following a prior assistant message, the model:
1. Resumes directly from the exact handoff point without restarting from the beginning.
2. Does not repeat, recap, or summarize already delivered content.
3. Omits conversational filler ("Sure, continuing...", "As I said earlier...").
4. Deduplicates any overlapping prefix if the model repeats words from the prior tail.
"""

import re
from typing import Optional, Sequence

from models.chat import Message

# Matches unambiguous continuation commands with optional polite prefixes/suffixes
CONTINUATION_PATTERN = re.compile(
    r"^(?:please\s+|pls\s+|can\s+you\s+|could\s+you\s+)?"
    r"(?:continue|keep\s+going|go\s+on|resume|carry\s+on)"
    r"(?:\s+(?:from\s+where\s+you\s+left\s+off|where\s+you\s+left\s+off|the\s+response|the\s+answer|your\s+response|your\s+answer|speaking|writing|talking))?"
    r"(?:\s+please|\s+pls)?[.!?]*$",
    re.IGNORECASE,
)

CONTINUATION_SYSTEM_CONTRACT = """<continuation_contract>
The user is requesting to continue the immediately preceding response that stopped or was truncated.
CRITICAL CONTINUATION CONTRACT:
1. RESUME DIRECTLY: Pick up immediately from the exact point where your previous answer stopped.
2. NO REPETITION: Do NOT repeat, summarize, rephrase, or recap any content, sections, or words already delivered in the previous answer.
3. NO META-COMMENTARY: Do NOT begin with conversational filler, greetings, or acknowledgments (e.g., "Sure, I'll continue", "Here is the rest", "Continuing from where I left off", "As I was saying"). Begin immediately with the continuation text.
4. SEAMLESS ATTACHMENT: Your response must seamlessly attach to the previous response as if written continuously.
5. NO REDUNDANT RETRIEVAL: Do NOT re-execute retrieval or search tools that were already executed for the prior answer unless new specific information is needed.
</continuation_contract>"""


def is_continuation_request(text: Optional[str]) -> bool:
    """Return True if user input is an unambiguous request to continue previous output."""
    if not text:
        return False
    cleaned = text.strip()
    return bool(CONTINUATION_PATTERN.match(cleaned))


def get_continuation_target(messages: Sequence[Message]) -> Optional[Message]:
    """If the latest turn is an unambiguous continuation of an immediately preceding assistant message, return that assistant message."""
    if len(messages) < 2:
        return None
    latest = messages[-1]
    if latest.sender in ('ai', 'assistant'):
        return None
    if not is_continuation_request(latest.text):
        return None
    # Inspect immediately preceding message
    prior = messages[-2]
    if prior.sender in ('ai', 'assistant') and prior.text and prior.text.strip():
        return prior
    return None


def format_continuation_user_prompt(original_text: str, prior_tail: str) -> str:
    """Format the continuation request with explicit resumption guidance referencing the prior tail."""
    clean_tail = prior_tail.strip()[-300:] if prior_tail else ""
    anchor_hint = f' [Resuming immediately after: "...{clean_tail}"]' if clean_tail else ""
    directive = (
        f"[Instruction: Resume your immediately preceding answer{anchor_hint}. "
        f"Do NOT restart, summarize, or repeat already delivered content. "
        f"Begin immediately with the next words without any introductory remarks.]"
    )
    if original_text:
        return f"{original_text}\n\n{directive}"
    return directive


def inject_continuation_directive(anthropic_messages: list, prior_text: Optional[str]) -> list:
    """Enhance the latest user turn in provider messages with continuation resumption directives."""
    if not anthropic_messages:
        return anthropic_messages
    for msg in reversed(anthropic_messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        prior_tail = (prior_text or "").strip()[-300:]
        directive = format_continuation_user_prompt("", prior_tail).strip()
        if isinstance(content, str):
            msg["content"] = f"{content}\n\n{directive}"
        elif isinstance(content, list):
            msg["content"] = [*content, {"type": "text", "text": f"\n\n{directive}"}]
        break
    return anthropic_messages


def strip_continuation_overlap(continuation_text: str, prior_tail: Optional[str]) -> str:
    """If the continuation text inadvertently repeats the ending words of the prior response, strip the duplicate prefix."""
    if not continuation_text or not prior_tail:
        return continuation_text

    prior_words = prior_tail.strip().split()
    cont_words = continuation_text.strip().split()

    max_check = min(len(prior_words), len(cont_words), 25)
    for k in range(max_check, 1, -1):
        suffix = " ".join(prior_words[-k:]).lower()
        prefix = " ".join(cont_words[:k]).lower()
        if suffix == prefix:
            remaining = continuation_text.strip()
            match = re.match(r"^(\s*\S+){" + str(k) + r"}\s*", remaining)
            if match:
                return remaining[match.end() :]
    return continuation_text
