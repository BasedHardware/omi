import logging

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from database.memories import get_memories
from database.action_items import get_action_items
from database.goals import get_user_goals
from utils.llm.clients import llm_mini

logger = logging.getLogger(__name__)

PROFILE_SYSTEM_PROMPT = """\
You are generating a concise user profile summary based on their data (goals, tasks, memories). \
This profile helps other AI assistants understand who the user is and what they care about.

FORMAT:
- Write in third person ("The user...")
- Include: professional focus, key projects, communication style, preferences
- Keep under 300 words
- Be factual — only include what's supported by the data
- If data is sparse, keep the profile short rather than speculating"""


class ProfileResult(BaseModel):
    profile_text: str = Field(description="The generated user profile summary")


async def generate_profile(uid: str) -> dict:
    """Generate a user profile from their goals, tasks, and memories.

    Returns:
        Dict with profile_text
    """
    parts = []

    try:
        goals = get_user_goals(uid, limit=10)
        if goals:
            goal_lines = [f"- {g.get('title', g.get('description', ''))}" for g in goals]
            parts.append("Goals:\n" + "\n".join(goal_lines))
    except Exception as e:
        logger.warning(f"Failed to fetch goals for profile: {e}")

    try:
        tasks = get_action_items(uid, completed=False, limit=30)
        if tasks:
            task_lines = [f"- {t.get('description', '')}" for t in tasks[:30]]
            parts.append("Active tasks:\n" + "\n".join(task_lines))
    except Exception as e:
        logger.warning(f"Failed to fetch tasks for profile: {e}")

    try:
        memories = get_memories(uid, limit=30, categories=['system'])
        if memories:
            mem_lines = []
            for m in memories:
                content = m.get('structured', {}).get('content', m.get('content', ''))
                if content:
                    mem_lines.append(f"- {content}")
            if mem_lines:
                parts.append("Known facts:\n" + "\n".join(mem_lines))
    except Exception as e:
        logger.warning(f"Failed to fetch memories for profile: {e}")

    if not parts:
        return {"profile_text": "No data available to generate profile."}

    data_text = "\n\n".join(parts)

    with_parser = llm_mini.with_structured_output(ProfileResult)
    result = await with_parser.ainvoke(
        [
            SystemMessage(content=PROFILE_SYSTEM_PROMPT),
            HumanMessage(content=f"Generate a user profile from this data:\n\n{data_text}"),
        ]
    )

    return {"profile_text": result.profile_text}
