import logging
from typing import List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from database.action_items import get_action_items
from utils.llm.clients import llm_gemini_flash

logger = logging.getLogger(__name__)

TASK_SYSTEM_PROMPT = """\
You are a task extraction assistant. Analyze screenshots to identify actionable tasks, \
requests, or to-dos visible on screen.

EXTRACTION RULES:
- Only extract tasks that are clearly visible and actionable
- Title must be 6+ words, verb-first, naming a specific person/project/artifact + concrete action
- Skip vague or generic items ("do something", "check this")
- ~90% of screenshots contain NO new task — use no_tasks when nothing actionable is found

DEDUPLICATION:
- Compare against the user's existing tasks provided in context
- If a task is semantically similar to an existing one (even with different wording), skip it
- "Call John" and "Phone John" are duplicates
- "Finish report by Friday" and "Complete report by end of week" are duplicates
- When in doubt, err on treating as duplicate (DON'T extract)

PRIORITY GUIDELINES:
- high: urgent deadlines, blocking requests, error fixes
- medium: normal work tasks, follow-ups
- low: nice-to-haves, ideas, non-urgent items

SOURCE CATEGORIES:
- direct_request: someone asked the user to do something (message, meeting, mention)
- self_generated: user's own idea, reminder, or goal subtask
- calendar_driven: event preparation, recurring task, deadline
- reactive: error response, notification, observation
- external_system: from project tools, alerts, documentation"""


class ExtractedTask(BaseModel):
    title: str = Field(description="Verb-first title, 6+ words, specific person/project + concrete action")
    description: str = Field(default="", description="Additional context if needed")
    priority: str = Field(description="high, medium, or low")
    tags: List[str] = Field(default_factory=list, description="1-3 relevant tags")
    source_app: str = Field(default="", description="App where task was found")
    inferred_deadline: Optional[str] = Field(default=None, description="yyyy-MM-dd format or null")
    confidence: float = Field(ge=0.0, le=1.0, description="Extraction confidence")
    source_category: str = Field(
        default="reactive", description="direct_request|self_generated|calendar_driven|reactive|external_system"
    )


class TaskExtractionResult(BaseModel):
    has_new_tasks: bool = Field(description="Whether any new tasks were found")
    tasks: List[ExtractedTask] = Field(default_factory=list, description="Extracted tasks (empty if none)")
    context_summary: str = Field(default="", description="Brief summary of what user is viewing")
    current_activity: str = Field(default="", description="What user is actively doing")


def _build_task_context(uid: str) -> str:
    """Build existing tasks context for deduplication."""
    parts = []

    try:
        # Active tasks (not completed) for dedup
        active_tasks = get_action_items(uid, completed=False, limit=50)
        if active_tasks:
            task_lines = []
            for t in active_tasks:
                desc = t.get('description', '')
                due = t.get('due_at', '')
                due_str = f" (Due: {due})" if due else ""
                task_lines.append(f"- {desc}{due_str} [Pending]")
            parts.append("Existing active tasks (DO NOT extract duplicates):\n" + "\n".join(task_lines))
    except Exception as e:
        logger.warning(f"Failed to fetch active tasks for dedup: {e}")

    try:
        # Recently completed tasks (last 10) for dedup
        completed_tasks = get_action_items(uid, completed=True, limit=10)
        if completed_tasks:
            task_lines = [f"- {t.get('description', '')} [Completed]" for t in completed_tasks[:10]]
            parts.append("Recently completed tasks:\n" + "\n".join(task_lines))
    except Exception as e:
        logger.warning(f"Failed to fetch completed tasks: {e}")

    return "\n\n".join(parts) if parts else ""


async def extract_tasks(
    uid: str,
    image_b64: str,
    app_name: str = "",
    window_title: str = "",
) -> dict:
    """Extract tasks from a screenshot using vision LLM.

    Args:
        uid: User ID for fetching existing tasks (dedup)
        image_b64: Base64-encoded JPEG screenshot
        app_name: Name of the foreground app
        window_title: Window title

    Returns:
        Dict with has_new_tasks, tasks list, context_summary, current_activity
    """
    # Pre-fetch existing tasks for dedup context
    task_context = _build_task_context(uid)

    # Assemble prompt
    prompt_parts = []
    if task_context:
        prompt_parts.append(task_context)
    if app_name or window_title:
        prompt_parts.append(f"Current app: {app_name}, Window: {window_title}")
    prompt_parts.append("Analyze this screenshot for actionable tasks:")

    prompt_text = "\n\n".join(prompt_parts)

    # Call vision LLM with structured output
    with_parser = llm_gemini_flash.with_structured_output(TaskExtractionResult)
    result = await with_parser.ainvoke(
        [
            SystemMessage(content=TASK_SYSTEM_PROMPT),
            HumanMessage(
                content=[
                    {"type": "text", "text": prompt_text},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                ]
            ),
        ]
    )

    tasks_list = []
    for task in result.tasks:
        tasks_list.append(
            {
                "title": task.title,
                "description": task.description,
                "priority": task.priority,
                "tags": task.tags,
                "source_app": task.source_app or app_name,
                "inferred_deadline": task.inferred_deadline,
                "confidence": task.confidence,
                "source_category": task.source_category,
            }
        )

    return {
        "has_new_tasks": result.has_new_tasks and len(tasks_list) > 0,
        "tasks": tasks_list,
        "context_summary": result.context_summary,
        "current_activity": result.current_activity,
    }
