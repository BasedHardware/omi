import logging
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from database.goals import get_user_goals
from database.action_items import get_action_items
from database.memories import get_memories
from utils.llm.clients import llm_gemini_flash

logger = logging.getLogger(__name__)

# Match the desktop FocusAssistant's ScreenAnalysis schema
FOCUS_SYSTEM_PROMPT = """You are a focus coach. Analyze the PRIMARY/MAIN window in screenshots to determine \
if the user is focused or distracted.

IMPORTANT: Look at the MAIN APPLICATION WINDOW, not log text or terminal output. \
If you see a code editor with logs that mention "YouTube" - that's just log text, \
the user is CODING, not on YouTube. Text in logs/terminals mentioning a site does \
NOT mean the user is on that site.

CONTEXT-AWARE ANALYSIS:
Each request may include the user's active goals, current tasks, recent memories, \
and analysis history. Use this context when available, but DO NOT let it prevent you \
from flagging obvious distractions.

- GOALS & TASKS: If the user's screen activity clearly relates to their active \
goals or current tasks, they are FOCUSED.
- HISTORY: Use recent analysis history to notice patterns, acknowledge transitions, \
and vary your responses.

Set status to "distracted" if the PRIMARY window is:
- YouTube, Twitch, Netflix, TikTok (actual video site visible, not just text mentioning it)
- Social media feeds: Twitter/X, Instagram, Facebook, Reddit (casual browsing, not researching)
- News sites, entertainment sites, games
- Any content consumption with no clear work purpose

Set status to "focused" if the PRIMARY window is:
- Code editors, IDEs, terminals, command line
- Documents, spreadsheets, slides, design tools
- Email, work chat (Slack, Teams), research
- Browsing that is clearly work-related (Stack Overflow, docs, PRs, Jira, etc.)

When in doubt, lean toward "distracted" — it's better to nudge the user once too \
often than to silently let them drift.

Always provide a short coaching message (100 characters max for notification banner):
- If distracted: Create a unique nudge to refocus. Vary your approach — be playful, \
direct, or motivational.
- If focused: Acknowledge their work with variety — don't just say "Nice focus!" \
every time."""


class FocusResult(BaseModel):
    status: str = Field(description='Focus status: "focused" or "distracted"')
    app_or_site: str = Field(description="Primary app or site in focus")
    description: str = Field(description="Brief description of what the user is doing")
    message: Optional[str] = Field(default=None, description="Short coaching message (max 100 chars)")


def _build_context(uid: str) -> str:
    """Build context from user's goals, tasks, and memories (server-side)."""
    parts = []

    # Goals (up to 10)
    try:
        goals = get_user_goals(uid, limit=10)
        if goals:
            goal_lines = [f"- {g.get('title', g.get('description', ''))}" for g in goals]
            parts.append("Active Goals:\n" + "\n".join(goal_lines))
    except Exception as e:
        logger.warning(f"Failed to fetch goals for context: {e}")

    # Tasks (up to 50, not completed)
    try:
        tasks = get_action_items(uid, completed=False, limit=50)
        if tasks:
            task_lines = [f"- {t.get('description', '')}" for t in tasks[:50]]
            parts.append("Current Tasks:\n" + "\n".join(task_lines))
    except Exception as e:
        logger.warning(f"Failed to fetch tasks for context: {e}")

    # Recent memories (up to 20, core category)
    try:
        memories = get_memories(uid, limit=20, categories=['core'])
        if memories:
            mem_lines = [f"- {m.get('structured', {}).get('title', m.get('content', ''))}" for m in memories[:20]]
            parts.append("Recent Memories:\n" + "\n".join(mem_lines))
    except Exception as e:
        logger.warning(f"Failed to fetch memories for context: {e}")

    return "\n\n".join(parts) if parts else ""


async def analyze_focus(
    uid: str,
    image_b64: str,
    app_name: str = "",
    window_title: str = "",
    history: str = "",
) -> dict:
    """Analyze a screenshot for focus status using vision LLM.

    Args:
        uid: User ID for fetching context
        image_b64: Base64-encoded JPEG screenshot
        app_name: Name of the foreground app
        window_title: Window title
        history: Formatted recent analysis history

    Returns:
        Dict with type, frame_id, status, app_or_site, description, message
    """
    # Build context from user data
    context = _build_context(uid)

    # Assemble prompt
    prompt_parts = []
    if context:
        prompt_parts.append(context)
    if history:
        prompt_parts.append(f"Recent activity (oldest to newest):\n{history}")
    if app_name or window_title:
        prompt_parts.append(f"Current app: {app_name}, Window: {window_title}")
    prompt_parts.append("Now analyze this screenshot:")

    prompt_text = "\n\n".join(prompt_parts)

    # Call vision LLM with structured output
    with_parser = llm_gemini_flash.with_structured_output(FocusResult)
    result = await with_parser.ainvoke(
        [
            SystemMessage(content=FOCUS_SYSTEM_PROMPT),
            HumanMessage(
                content=[
                    {"type": "text", "text": prompt_text},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                ]
            ),
        ]
    )

    return {
        "status": result.status,
        "app_or_site": result.app_or_site,
        "description": result.description,
        "message": result.message,
    }
