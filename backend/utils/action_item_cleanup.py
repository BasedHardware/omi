import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field as PydanticField

import database.action_items as action_items_db
import database.conversations as conversations_db
from database.vector_db import fetch_action_item_vectors
from utils.llm.clients import get_llm

logger = logging.getLogger(__name__)


def _parse_dt(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        return datetime.fromisoformat(value.rstrip('Z')).replace(tzinfo=timezone.utc)
    # Firestore DatetimeWithNanoseconds
    if hasattr(value, 'timestamp'):
        return datetime.fromtimestamp(value.timestamp(), tz=timezone.utc)
    return None


def _conversation_dates(uid: str, conversation_ids: set[str]) -> dict[str, datetime]:
    """Return a map of conversation_id → started_at (or created_at) for a set of IDs."""
    dates = {}
    for cid in conversation_ids:
        try:
            conv = conversations_db.get_conversation(uid, cid)
            if not conv:
                continue
            ref = _parse_dt(conv.get('started_at')) or _parse_dt(conv.get('created_at'))
            if ref:
                dates[cid] = ref
        except Exception as e:
            logger.warning(f'Failed to fetch conversation {cid}: {e}')
    return dates


def _fetch_conversation_contexts(uid: str, conversation_ids: set[str]) -> dict[str, dict]:
    """
    Return a map of conversation_id → {started_at, title, overview} for a set of IDs.
    Missing or errored conversations are silently omitted.
    """
    contexts = {}
    for cid in conversation_ids:
        try:
            conv = conversations_db.get_conversation(uid, cid)
            if not conv:
                continue
            started_at = _parse_dt(conv.get('started_at')) or _parse_dt(conv.get('created_at'))
            structured = conv.get('structured') or {}
            if isinstance(structured, dict):
                title = structured.get('title', '')
                overview = structured.get('overview', '')
            else:
                title, overview = '', ''
            contexts[cid] = {
                'started_at': started_at,
                'title': title,
                'overview': overview[:300] if overview else '',
            }
        except Exception as e:
            logger.warning(f'Failed to fetch conversation context {cid}: {e}')
    return contexts


# ---------------------------------------------------------------------------
# Strategy: age-based staleness
# ---------------------------------------------------------------------------

def candidates_stale_age(uid: str, age_days: int = 30) -> list[dict]:
    """
    Return open tasks with no due date whose source conversation is older than
    age_days. Falls back to the task's own created_at for standalone tasks.
    Each result dict has 'id', 'description', 'strategy'.
    """
    now = datetime.now(timezone.utc)
    all_items = action_items_db.get_action_items(uid, completed=False)

    # Batch-fetch conversation dates for all linked tasks in one pass
    conv_ids = {i['conversation_id'] for i in all_items if i.get('conversation_id')}
    conv_dates = _conversation_dates(uid, conv_ids)

    candidates = []
    for item in all_items:
        if item.get('due_at'):
            continue

        cid = item.get('conversation_id')
        if cid:
            # Use conversation start date; fall back to created_at if conversation not found
            ref = conv_dates.get(cid) or _parse_dt(item.get('created_at'))
        else:
            ref = _parse_dt(item.get('created_at'))

        if ref is None:
            continue

        if (now - ref).days >= age_days:
            candidates.append({
                'id': item['id'],
                'description': item.get('description', ''),
                'strategy': 'stale_age',
            })

    return candidates


# ---------------------------------------------------------------------------
# Strategy: overdue due dates
# ---------------------------------------------------------------------------

def candidates_overdue(uid: str, overdue_days: int = 7) -> list[dict]:
    """
    Return open tasks whose due_at is more than overdue_days in the past.
    These are either done-and-not-marked or permanently missed.
    Each result dict has 'id', 'description', 'strategy'.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=overdue_days)
    items = action_items_db.get_action_items(uid, completed=False, due_end_date=cutoff)
    return [
        {
            'id': item['id'],
            'description': item.get('description', ''),
            'strategy': 'overdue',
        }
        for item in items
        if item.get('due_at')  # guard: due_end_date filter should handle this but be explicit
    ]


# ---------------------------------------------------------------------------
# Strategy: semantic deduplication
# ---------------------------------------------------------------------------

def candidates_semantic_dedup(uid: str, similarity_threshold: float = 0.92) -> list[dict]:
    """
    Find open tasks that are near-duplicates of a newer task using local cosine
    similarity. Fetches all vectors in one Pinecone call, then computes an
    in-memory similarity matrix — O(1) Pinecone calls regardless of task count.

    For each group of similar tasks, the newest is kept and older duplicates
    are returned as candidates.
    """
    all_items = action_items_db.get_action_items(uid, completed=False)
    if not all_items:
        return []

    # Fetch all vectors in one batch
    ids = [item['id'] for item in all_items]
    vectors = fetch_action_item_vectors(uid, ids)
    if not vectors:
        logger.warning('semantic_dedup: no vectors found, skipping')
        return []

    # Keep only items that have a vector
    items_with_vec = [i for i in all_items if i['id'] in vectors]
    if len(items_with_vec) < 2:
        return []

    # Build matrix (n × d), normalise rows for cosine similarity via dot product
    item_ids = [i['id'] for i in items_with_vec]
    matrix = np.array([vectors[iid] for iid in item_ids], dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    matrix /= norms
    similarity = matrix @ matrix.T  # (n × n) cosine similarity

    # Parse creation dates for tie-breaking (newer wins)
    dates = [_parse_dt(i.get('created_at')) or datetime.min.replace(tzinfo=timezone.utc)
             for i in items_with_vec]
    id_to_item = {i['id']: i for i in items_with_vec}

    candidate_ids: set[str] = set()
    candidates: list[dict] = []

    for i, item_id in enumerate(item_ids):
        if item_id in candidate_ids:
            continue
        for j in range(i + 1, len(item_ids)):
            if item_ids[j] in candidate_ids:
                continue
            if float(similarity[i, j]) < similarity_threshold:
                continue
            # Duplicate pair found — drop the older one
            if dates[i] >= dates[j]:
                dup_id = item_ids[j]
            else:
                dup_id = item_id
                break  # current item is the older duplicate; outer loop will skip it
            if dup_id not in candidate_ids:
                candidate_ids.add(dup_id)
                candidates.append({
                    'id': dup_id,
                    'description': id_to_item[dup_id].get('description', ''),
                    'strategy': 'semantic_dedup',
                })

    logger.info(f'semantic_dedup uid={uid} checked={len(items_with_vec)} duplicates={len(candidates)}')
    return candidates


# ---------------------------------------------------------------------------
# Strategy: LLM relevance scoring
# ---------------------------------------------------------------------------

class _TaskVerdict(BaseModel):
    id: str = PydanticField(description="The task ID exactly as given")
    is_stale: bool = PydanticField(description="True if this task is likely no longer relevant or actionable")
    confidence: float = PydanticField(description="Confidence in the verdict, 0.0 to 1.0")


class _BatchVerdicts(BaseModel):
    verdicts: list[_TaskVerdict] = PydanticField(description="One verdict per task")


_RELEVANCE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are reviewing open to-do items to identify ones that are likely no longer relevant.

For each task assess whether it is still actionable given how long ago it was created.

Rules:
- Be CONSERVATIVE. Only mark a task stale if you are highly confident it no longer matters.
- Routine personal reminders (call someone, buy something) are likely still relevant regardless of age.
- Event-specific tasks (prepare for X meeting, get ready for Y event) from long ago are likely stale.
- Vague or already-obvious tasks ("go to bed", "brush teeth") that recur daily are likely stale duplicates.
- Return confidence >= 0.85 only when you are quite sure.""",
    ),
    (
        "human",
        "Today's date: {today}\n\nTasks to review:\n{tasks}",
    ),
])

_BATCH_SIZE = 50


def candidates_llm_relevance(uid: str, confidence_threshold: float = 0.85) -> list[dict]:
    """
    Use an LLM to score open tasks for relevance. Tasks the LLM considers stale
    with confidence >= confidence_threshold become candidates.
    Processes tasks in batches of 50 to keep prompts manageable.
    """
    all_items = action_items_db.get_action_items(uid, completed=False)
    if not all_items:
        return []

    llm = get_llm('conv_discard').with_structured_output(_BatchVerdicts)
    chain = _RELEVANCE_PROMPT | llm
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    id_to_item = {item['id']: item for item in all_items}

    def _score_batch(batch: list[dict]) -> list[dict]:
        task_lines = []
        for item in batch:
            created = _parse_dt(item.get('created_at'))
            age = f"{(datetime.now(timezone.utc) - created).days}d ago" if created else "unknown age"
            task_lines.append(f"- id:{item['id']} | {item.get('description', '')} [{age}]")
        try:
            result: _BatchVerdicts = chain.invoke({"today": today, "tasks": "\n".join(task_lines)})
            return [
                {'id': v.id, 'description': id_to_item[v.id].get('description', ''), 'strategy': 'llm_relevance'}
                for v in result.verdicts
                if v.is_stale and v.confidence >= confidence_threshold and v.id in id_to_item
            ]
        except Exception as e:
            logger.warning(f'LLM relevance batch failed: {e}')
            return []

    batches = [all_items[i:i + _BATCH_SIZE] for i in range(0, len(all_items), _BATCH_SIZE)]
    candidates = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        for result in as_completed([pool.submit(_score_batch, b) for b in batches]):
            candidates.extend(result.result())

    logger.info(f'llm_relevance uid={uid} checked={len(all_items)} candidates={len(candidates)}')
    return candidates


# ---------------------------------------------------------------------------
# Strategy: conversation context
# ---------------------------------------------------------------------------

_CONV_CONTEXT_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are reviewing open to-do items. Each task came from a specific conversation.
You will be given the conversation's title, a brief overview, and how long ago it happened,
along with the tasks that were extracted from it.

Assess whether each task is still relevant given the conversation context and how much time has passed.

Rules:
- Be CONSERVATIVE. Only mark a task stale if you are highly confident it is no longer relevant.
- If the conversation was about a specific past event (a meeting, a trip, a service, a deadline),
  tasks about preparing for it are almost certainly stale.
- If the conversation topic is ongoing (a relationship, a project, a recurring role),
  tasks are more likely still relevant.
- Return confidence >= 0.85 only when you are quite sure.""",
    ),
    (
        "human",
        """Today: {today}

Conversation: "{title}"
Summary: {overview}
Happened: {age}

Tasks from this conversation:
{tasks}""",
    ),
])


def candidates_conversation_context(uid: str, confidence_threshold: float = 0.85) -> list[dict]:
    """
    Use conversation title/overview as context to assess task relevance.
    Only operates on tasks with a conversation_id. Groups tasks by conversation
    so each conversation's context is fetched and sent to the LLM once.
    """
    all_items = action_items_db.get_action_items(uid, completed=False)
    linked = [i for i in all_items if i.get('conversation_id')]
    if not linked:
        logger.info('conversation_context: no tasks with conversation_id, skipping')
        return []

    conv_ids = {i['conversation_id'] for i in linked}
    contexts = _fetch_conversation_contexts(uid, conv_ids)
    if not contexts:
        logger.info('conversation_context: no conversations found locally, skipping')
        return []

    # Group tasks by conversation
    by_conv: dict[str, list[dict]] = {}
    for item in linked:
        cid = item['conversation_id']
        if cid in contexts:
            by_conv.setdefault(cid, []).append(item)

    llm = get_llm('conv_discard').with_structured_output(_BatchVerdicts)
    chain = _CONV_CONTEXT_PROMPT | llm
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    now = datetime.now(timezone.utc)

    id_to_item = {item['id']: item for item in linked}

    def _score_conv_batch(cid: str, batch: list[dict]) -> list[dict]:
        ctx = contexts[cid]
        started_at = ctx['started_at']
        age = f"{(now - started_at).days} days ago" if started_at else "unknown"
        task_lines = [f"- id:{i['id']} | {i.get('description', '')}" for i in batch]
        try:
            result: _BatchVerdicts = chain.invoke({
                "today": today,
                "title": ctx['title'] or '(untitled)',
                "overview": ctx['overview'] or '(no summary)',
                "age": age,
                "tasks": "\n".join(task_lines),
            })
            return [
                {'id': v.id, 'description': id_to_item[v.id].get('description', ''), 'strategy': 'conversation_context'}
                for v in result.verdicts
                if v.is_stale and v.confidence >= confidence_threshold and v.id in id_to_item
            ]
        except Exception as e:
            logger.warning(f'conversation_context batch failed for conv {cid}: {e}')
            return []

    all_batches = [
        (cid, items[i:i + _BATCH_SIZE])
        for cid, items in by_conv.items()
        for i in range(0, len(items), _BATCH_SIZE)
    ]
    candidates = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        for result in as_completed([pool.submit(_score_conv_batch, cid, batch) for cid, batch in all_batches]):
            candidates.extend(result.result())

    logger.info(f'conversation_context uid={uid} conversations={len(by_conv)} candidates={len(candidates)}')
    return candidates


# ---------------------------------------------------------------------------
# Strategy: vagueness / context-loss detection
# ---------------------------------------------------------------------------

# Unresolved demonstratives and pronouns as objects
_PRONOUN_PATTERN = re.compile(
    r'\b(it|them|those|these|that|this|the other|the same|the two|the ones?|'
    r'the things?|the stuff|the other one|the rest)\b',
    re.IGNORECASE,
)

# Common imperative verb + dangling reference combos
_DANGLING_PATTERN = re.compile(
    r'^(put|take|send|get|fix|check|do|move|bring|pick up|drop off|return|'
    r'give back|hand|pass|grab|swap|switch|change|clean|clear|sort|set)\s+'
    r'(it|them|those|these|that|this|the\s+\w+)\b',
    re.IGNORECASE,
)

# Speaker placeholders that were never resolved
_SPEAKER_PATTERN = re.compile(r'\bspeaker\s+\d+\b', re.IGNORECASE)


def _is_vague(description: str) -> bool:
    desc = description.strip()
    words = desc.split()

    # Unresolved speaker label
    if _SPEAKER_PATTERN.search(desc):
        return True

    # Short description (≤ 5 words) containing a pronoun/demonstrative
    if len(words) <= 5 and _PRONOUN_PATTERN.search(desc):
        return True

    # Imperative + dangling pronoun regardless of length
    if _DANGLING_PATTERN.match(desc):
        return True

    return False


def candidates_vague(uid: str) -> list[dict]:
    """
    Find open tasks whose descriptions contain unresolved pronouns or references
    that make them meaningless without the original conversational context.
    Examples: "Put those away", "Swap between the two cars", "Attend ultrasound with Speaker 0"
    Rule-based — no LLM calls needed.
    """
    all_items = action_items_db.get_action_items(uid, completed=False)
    candidates = [
        {
            'id': item['id'],
            'description': item.get('description', ''),
            'strategy': 'vague',
        }
        for item in all_items
        if _is_vague(item.get('description', ''))
    ]
    logger.info(f'vague uid={uid} checked={len(all_items)} candidates={len(candidates)}')
    return candidates


# ---------------------------------------------------------------------------
# Merge helpers
# ---------------------------------------------------------------------------

def merge_candidates(lists: list[list[dict]]) -> list[dict]:
    """Merge candidate lists from multiple strategies, deduplicating by ID."""
    seen = set()
    merged = []
    for lst in lists:
        for c in lst:
            if c['id'] not in seen:
                seen.add(c['id'])
                merged.append(c)
    return merged
