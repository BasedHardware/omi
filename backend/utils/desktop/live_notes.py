import logging

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from utils.llm.clients import llm_mini

logger = logging.getLogger(__name__)

LIVE_NOTES_SYSTEM_PROMPT = """\
You are a live note-taking assistant. Given a transcript segment, generate a concise, \
well-structured note that captures the key information.

RULES:
- Condense transcript into clear, readable notes
- Preserve important details: names, numbers, decisions, action items
- Remove filler words, repetition, and hesitation
- Use bullet points for multiple items
- Keep notes under 200 words
- If the transcript is too short or contains no meaningful content, return empty string"""


class LiveNoteResult(BaseModel):
    text: str = Field(description="The generated note (empty string if no meaningful content)")


async def generate_live_note(
    text: str,
    session_context: str = "",
) -> dict:
    """Generate a live note from transcript text.

    Args:
        text: Transcript text to summarize
        session_context: Optional session context

    Returns:
        Dict with text field (the note)
    """
    prompt_parts = []
    if session_context:
        prompt_parts.append(f"Session context: {session_context}")
    prompt_parts.append(f"Transcript:\n{text}")

    prompt_text = "\n\n".join(prompt_parts)

    with_parser = llm_mini.with_structured_output(LiveNoteResult)
    result = await with_parser.ainvoke(
        [
            SystemMessage(content=LIVE_NOTES_SYSTEM_PROMPT),
            HumanMessage(content=prompt_text),
        ]
    )

    return {"text": result.text}
