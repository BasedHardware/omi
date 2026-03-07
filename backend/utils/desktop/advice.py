import logging
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from database.goals import get_user_goals
from database.action_items import get_action_items
from utils.llm.clients import llm_gemini_flash

logger = logging.getLogger(__name__)

ADVICE_SYSTEM_PROMPT = """\
You are a proactive assistant that offers brief, actionable advice based on what the user \
is currently doing on their screen. Your advice should be contextual and helpful.

ADVICE RULES:
- Only offer advice when you can provide genuinely useful, specific guidance
- Advice must relate to what's visible on screen
- Keep it short (1-2 sentences max)
- Be actionable — tell the user something they can DO, not just observe
- Consider the user's goals and tasks when forming advice
- ~70% of screenshots need NO advice — return null when nothing useful to say

TONE:
- Direct and casual, not formal
- Helpful, not preachy
- Specific to what you see, not generic productivity tips

CATEGORIES:
- productivity: efficiency tips, workflow improvements
- mistake_prevention: catching potential errors or oversights
- learning: suggesting resources or approaches
- health: break reminders, posture, eye strain (only if clearly needed)
- goal_alignment: connecting current activity to stated goals"""


class AdviceResult(BaseModel):
    has_advice: bool = Field(description="Whether advice is warranted")
    content: Optional[str] = Field(default=None, description="The advice (1-2 sentences, null if none)")
    category: Optional[str] = Field(
        default=None, description="productivity|mistake_prevention|learning|health|goal_alignment"
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence this advice is useful")


def _build_advice_context(uid: str) -> str:
    """Build user context for advice generation."""
    parts = []

    try:
        goals = get_user_goals(uid, limit=5)
        if goals:
            goal_lines = [f"- {g.get('title', g.get('description', ''))}" for g in goals]
            parts.append("User's goals:\n" + "\n".join(goal_lines))
    except Exception as e:
        logger.warning(f"Failed to fetch goals for advice: {e}")

    try:
        tasks = get_action_items(uid, completed=False, limit=10)
        if tasks:
            task_lines = [f"- {t.get('description', '')}" for t in tasks[:10]]
            parts.append("Current tasks:\n" + "\n".join(task_lines))
    except Exception as e:
        logger.warning(f"Failed to fetch tasks for advice: {e}")

    return "\n\n".join(parts) if parts else ""


async def generate_advice(
    uid: str,
    image_b64: str,
    app_name: str = "",
    window_title: str = "",
) -> dict:
    """Generate contextual advice from a screenshot using vision LLM.

    Returns:
        Dict with has_advice, content, category, confidence (or nulls if no advice)
    """
    advice_context = _build_advice_context(uid)

    prompt_parts = []
    if advice_context:
        prompt_parts.append(advice_context)
    if app_name or window_title:
        prompt_parts.append(f"Current app: {app_name}, Window: {window_title}")
    prompt_parts.append("Based on this screenshot, do you have any specific, actionable advice?")

    prompt_text = "\n\n".join(prompt_parts)

    with_parser = llm_gemini_flash.with_structured_output(AdviceResult)
    result = await with_parser.ainvoke(
        [
            SystemMessage(content=ADVICE_SYSTEM_PROMPT),
            HumanMessage(
                content=[
                    {"type": "text", "text": prompt_text},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                ]
            ),
        ]
    )

    if not result.has_advice:
        return {"has_advice": False, "advice": None}

    return {
        "has_advice": True,
        "advice": {
            "content": result.content,
            "category": result.category,
            "confidence": result.confidence,
        },
    }
