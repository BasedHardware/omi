import logging
from typing import List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from database.memories import get_memories
from utils.llm.clients import llm_gemini_flash

logger = logging.getLogger(__name__)

MEMORY_SYSTEM_PROMPT = """\
You are a memory extraction assistant. Analyze screenshots to identify facts, insights, \
or noteworthy information worth remembering about the user or their context.

EXTRACTION RULES:
- Extract facts ABOUT the user: preferences, projects, people they work with, decisions, realizations
- Extract useful external information: advice, tips, insights from what they're reading
- Maximum 3 memories per screenshot
- Each memory should be a concise, standalone fact
- Skip trivial or transient information (UI state, loading screens, timestamps)
- ~80% of screenshots contain NO memorable information — return empty list when nothing stands out

DEDUPLICATION:
- Compare against existing memories provided in context
- If a fact is already known, skip it
- Only extract genuinely NEW information

CATEGORIES:
- system: Facts about the user (preferences, opinions, network, projects, habits)
- interesting: External wisdom or advice from others (articles, conversations, tips)"""


class ExtractedMemory(BaseModel):
    content: str = Field(description="Concise statement of the fact or insight")
    category: str = Field(description="system or interesting")
    confidence: float = Field(ge=0.0, le=1.0, description="Extraction confidence")


class MemoryExtractionResult(BaseModel):
    memories: List[ExtractedMemory] = Field(default_factory=list, description="Extracted memories (empty if none)")


def _build_memory_context(uid: str) -> str:
    """Build existing memories context for deduplication."""
    try:
        existing = get_memories(uid, limit=30, categories=['system', 'interesting'])
        if existing:
            lines = []
            for m in existing:
                content = m.get('structured', {}).get('content', m.get('content', ''))
                if content:
                    lines.append(f"- {content}")
            if lines:
                return "Existing memories (DO NOT extract duplicates):\n" + "\n".join(lines)
    except Exception as e:
        logger.warning(f"Failed to fetch existing memories: {e}")
    return ""


async def extract_memories(
    uid: str,
    image_b64: str,
    app_name: str = "",
    window_title: str = "",
) -> dict:
    """Extract memories from a screenshot using vision LLM.

    Returns:
        Dict with memories list (each has content, category, confidence)
    """
    memory_context = _build_memory_context(uid)

    prompt_parts = []
    if memory_context:
        prompt_parts.append(memory_context)
    if app_name or window_title:
        prompt_parts.append(f"Current app: {app_name}, Window: {window_title}")
    prompt_parts.append("Analyze this screenshot for noteworthy facts or insights:")

    prompt_text = "\n\n".join(prompt_parts)

    with_parser = llm_gemini_flash.with_structured_output(MemoryExtractionResult)
    result = await with_parser.ainvoke(
        [
            SystemMessage(content=MEMORY_SYSTEM_PROMPT),
            HumanMessage(
                content=[
                    {"type": "text", "text": prompt_text},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                ]
            ),
        ]
    )

    return {
        "memories": [
            {"content": m.content, "category": m.category, "confidence": m.confidence} for m in result.memories
        ]
    }
