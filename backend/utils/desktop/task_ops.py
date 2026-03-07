import logging
from typing import List

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from database.action_items import get_action_items
from utils.llm.clients import llm_mini

logger = logging.getLogger(__name__)

# --- Task Reranking ---

RERANK_SYSTEM_PROMPT = """\
You are a task prioritization assistant. Given a list of tasks, rerank them by importance \
and urgency. Consider deadlines, dependencies, and impact.

RULES:
- Most important/urgent tasks first
- Tasks with approaching deadlines rank higher
- Blocking tasks rank higher than blocked tasks
- Return the same task IDs in new order"""


class RankedTask(BaseModel):
    id: str = Field(description="Task ID")
    new_position: int = Field(description="New position (1 = most important)")


class RerankResult(BaseModel):
    updated_tasks: List[RankedTask] = Field(description="Tasks in new priority order")


async def rerank_tasks(uid: str) -> dict:
    """Rerank user's active tasks by priority.

    Returns:
        Dict with updated_tasks list
    """
    try:
        tasks = get_action_items(uid, completed=False, limit=50)
    except Exception as e:
        logger.error(f"Failed to fetch tasks for reranking: {e}")
        return {"updated_tasks": []}

    if not tasks:
        return {"updated_tasks": []}

    task_lines = []
    for t in tasks:
        tid = t.get('id', '')
        desc = t.get('description', '')
        due = t.get('due_at', '')
        priority = t.get('priority', 'medium')
        due_str = f", Due: {due}" if due else ""
        task_lines.append(f"- ID: {tid} | {desc} | Priority: {priority}{due_str}")

    task_text = "\n".join(task_lines)

    with_parser = llm_mini.with_structured_output(RerankResult)
    result = await with_parser.ainvoke(
        [
            SystemMessage(content=RERANK_SYSTEM_PROMPT),
            HumanMessage(content=f"Rerank these tasks by importance:\n\n{task_text}"),
        ]
    )

    return {"updated_tasks": [{"id": t.id, "new_position": t.new_position} for t in result.updated_tasks]}


# --- Task Deduplication ---

DEDUP_SYSTEM_PROMPT = """\
You are a task deduplication assistant. Identify semantically duplicate tasks and decide \
which to keep and which to delete.

RULES:
- Two tasks are duplicates if they describe the same action, even with different wording
- "Call John" and "Phone John" are duplicates
- "Review PR #42" and "Look at pull request 42" are duplicates
- Keep the more specific/detailed version
- Keep the one with a deadline if only one has one
- Keep the more recently created one if equally specific
- Only flag true duplicates — similar but distinct tasks should both be kept"""


class DedupGroup(BaseModel):
    keep_id: str = Field(description="ID of the task to keep")
    delete_ids: List[str] = Field(description="IDs of duplicate tasks to remove")
    reason: str = Field(description="Why these are duplicates")


class DedupResult(BaseModel):
    groups: List[DedupGroup] = Field(default_factory=list, description="Duplicate groups (empty if no duplicates)")


async def dedup_tasks(uid: str) -> dict:
    """Find and resolve duplicate tasks.

    Returns:
        Dict with deleted_ids and reason
    """
    try:
        tasks = get_action_items(uid, completed=False, limit=100)
    except Exception as e:
        logger.error(f"Failed to fetch tasks for dedup: {e}")
        return {"deleted_ids": [], "reason": "Failed to fetch tasks"}

    if len(tasks) < 2:
        return {"deleted_ids": [], "reason": "Not enough tasks to deduplicate"}

    task_lines = []
    for t in tasks:
        tid = t.get('id', '')
        desc = t.get('description', '')
        due = t.get('due_at', '')
        created = t.get('created_at', '')
        due_str = f", Due: {due}" if due else ""
        created_str = f", Created: {created}" if created else ""
        task_lines.append(f"- ID: {tid} | {desc}{due_str}{created_str}")

    task_text = "\n".join(task_lines)

    with_parser = llm_mini.with_structured_output(DedupResult)
    result = await with_parser.ainvoke(
        [
            SystemMessage(content=DEDUP_SYSTEM_PROMPT),
            HumanMessage(content=f"Find duplicate tasks:\n\n{task_text}"),
        ]
    )

    all_deleted = []
    reasons = []
    for group in result.groups:
        all_deleted.extend(group.delete_ids)
        reasons.append(group.reason)

    return {
        "deleted_ids": all_deleted,
        "reason": "; ".join(reasons) if reasons else "No duplicates found",
    }
