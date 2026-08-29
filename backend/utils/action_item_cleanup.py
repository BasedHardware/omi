import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, cast

import numpy as np
from concurrent.futures import as_completed
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field as PydanticField

import database.action_items as action_items_db
import database.conversations as conversations_db
from database.vector_db import fetch_action_item_vectors
from utils.executors import llm_executor
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


def _item_visible_for_cleanup(item: dict) -> bool:
    return not item.get('is_locked', False)


def _open_items_for_cleanup(uid: str, scan_cursor: Optional[str] = None) -> tuple[list[dict], Optional[str]]:
    items, next_cursor, _ = action_items_db.list_open_action_items_for_cleanup(uid, cursor=scan_cursor)
    visible = [item for item in items if _item_visible_for_cleanup(item)]
    return visible, next_cursor


def _candidate_from_item(item: dict, strategy: str) -> dict:
    return {
        'id': item['id'],
        'description': item.get('description', ''),
        'strategy': strategy,
    }


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


def candidates_stale_age(
    uid: str, age_days: int = 30, *, scan_cursor: Optional[str] = None
) -> tuple[list[dict], Optional[str]]:
    """
    Return open tasks with no due date whose source conversation is older than
    age_days. Falls back to the task's own created_at for standalone tasks.
    Each result dict has 'id', 'description', 'strategy'.
    """
    now = datetime.now(timezone.utc)
    all_items, next_cursor = _open_items_for_cleanup(uid, scan_cursor)

    conv_ids = {i['conversation_id'] for i in all_items if i.get('conversation_id')}
    conv_dates = _conversation_dates(uid, conv_ids)

    candidates = []
    for item in all_items:
        if item.get('due_at'):
            continue

        cid = item.get('conversation_id')
        if cid:
            ref = conv_dates.get(cid) or _parse_dt(item.get('created_at'))
        else:
            ref = _parse_dt(item.get('created_at'))

        if ref is None:
            continue

        if (now - ref).days >= age_days:
            candidates.append(_candidate_from_item(item, 'stale_age'))

    return candidates, next_cursor


# ---------------------------------------------------------------------------
# Strategy: overdue due dates
# ---------------------------------------------------------------------------


def candidates_overdue(
    uid: str, overdue_days: int = 7, *, scan_cursor: Optional[str] = None
) -> tuple[list[dict], Optional[str]]:
    """
    Return open tasks whose due_at is more than overdue_days in the past.
    These are either done-and-not-marked or permanently missed.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=overdue_days)
    all_items, next_cursor = _open_items_for_cleanup(uid, scan_cursor)
    candidates = []
    for item in all_items:
        due_at = _parse_dt(item.get('due_at'))
        if due_at and due_at <= cutoff:
            candidates.append(_candidate_from_item(item, 'overdue'))
    return candidates, next_cursor


# ---------------------------------------------------------------------------
# Strategy: semantic deduplication
# ---------------------------------------------------------------------------


def candidates_semantic_dedup(
    uid: str, similarity_threshold: float = 0.92, *, scan_cursor: Optional[str] = None
) -> tuple[list[dict], Optional[str]]:
    """
    Find open tasks that are near-duplicates of a newer task using local cosine
    similarity. Fetches all vectors in one Pinecone call, then computes an
    in-memory similarity matrix — O(1) Pinecone calls regardless of task count.
    """
    all_items, next_cursor = _open_items_for_cleanup(uid, scan_cursor)
    if not all_items:
        return [], next_cursor

    ids = [item['id'] for item in all_items]
    vectors = fetch_action_item_vectors(uid, ids)
    if not vectors:
        logger.warning('semantic_dedup: no vectors found, skipping')
        return [], next_cursor

    items_with_vec = [i for i in all_items if i['id'] in vectors]
    if len(items_with_vec) < 2:
        return [], next_cursor

    item_ids = [i['id'] for i in items_with_vec]
    matrix = np.array([vectors[iid] for iid in item_ids], dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    matrix /= norms
    similarity = matrix @ matrix.T

    dates = [_parse_dt(i.get('created_at')) or datetime.min.replace(tzinfo=timezone.utc) for i in items_with_vec]
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
            if dates[i] >= dates[j]:
                dup_id = item_ids[j]
            else:
                dup_id = item_id
                break
            if dup_id not in candidate_ids:
                candidate_ids.add(dup_id)
                candidates.append(_candidate_from_item(id_to_item[dup_id], 'semantic_dedup'))

    logger.info(f'semantic_dedup uid={uid} checked={len(items_with_vec)} duplicates={len(candidates)}')
    return candidates, next_cursor


# ---------------------------------------------------------------------------
# Strategy: LLM relevance scoring
# ---------------------------------------------------------------------------


class _TaskVerdict(BaseModel):
    id: str = PydanticField(description="The task ID exactly as given")
    is_stale: bool = PydanticField(description="True if this task is likely no longer relevant or actionable")
    confidence: float = PydanticField(description="Confidence in the verdict, 0.0 to 1.0")


class _BatchVerdicts(BaseModel):
    verdicts: list[_TaskVerdict] = PydanticField(description="One verdict per task")


_RELEVANCE_PROMPT = ChatPromptTemplate.from_messages(
    [
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
    ]
)

_BATCH_SIZE = 50


def _run_llm_batches(uid: str, batches: list[list[dict]], score_fn) -> list[dict]:
    if not batches:
        return []
    futures = [llm_executor.submit(score_fn, batch) for batch in batches]
    candidates: list[dict] = []
    for future in as_completed(futures):
        try:
            candidates.extend(future.result())
        except Exception as e:
            logger.warning(f'LLM cleanup batch failed uid={uid}: {e}')
    return candidates


def candidates_llm_relevance(
    uid: str, confidence_threshold: float = 0.85, *, scan_cursor: Optional[str] = None
) -> tuple[list[dict], Optional[str]]:
    """
    Use an LLM to score open tasks for relevance. Tasks the LLM considers stale
    with confidence >= confidence_threshold become candidates.
    """
    all_items, next_cursor = _open_items_for_cleanup(uid, scan_cursor)
    if not all_items:
        return [], next_cursor

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
        result = cast(_BatchVerdicts, chain.invoke({"today": today, "tasks": "\n".join(task_lines)}))
        return [
            _candidate_from_item(id_to_item[v.id], 'llm_relevance')
            for v in result.verdicts
            if v.is_stale and v.confidence >= confidence_threshold and v.id in id_to_item
        ]

    batches = [all_items[i : i + _BATCH_SIZE] for i in range(0, len(all_items), _BATCH_SIZE)]
    candidates = _run_llm_batches(uid, batches, _score_batch)
    logger.info(f'llm_relevance uid={uid} checked={len(all_items)} candidates={len(candidates)}')
    return candidates, next_cursor


# ---------------------------------------------------------------------------
# Strategy: conversation context
# ---------------------------------------------------------------------------

_CONV_CONTEXT_PROMPT = ChatPromptTemplate.from_messages(
    [
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
    ]
)


def candidates_conversation_context(
    uid: str, confidence_threshold: float = 0.85, *, scan_cursor: Optional[str] = None
) -> tuple[list[dict], Optional[str]]:
    """
    Use conversation title/overview as context to assess task relevance.
    Only operates on tasks with a conversation_id.
    """
    all_items, next_cursor = _open_items_for_cleanup(uid, scan_cursor)
    linked = [i for i in all_items if i.get('conversation_id')]
    if not linked:
        logger.info('conversation_context: no tasks with conversation_id, skipping')
        return [], next_cursor

    conv_ids = {i['conversation_id'] for i in linked}
    contexts = _fetch_conversation_contexts(uid, conv_ids)
    if not contexts:
        logger.info('conversation_context: no conversations found locally, skipping')
        return [], next_cursor

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

    def _score_conv_batch(batch: list[dict], cid: str) -> list[dict]:
        ctx = contexts[cid]
        started_at = ctx['started_at']
        age = f"{(now - started_at).days} days ago" if started_at else "unknown"
        task_lines = [f"- id:{i['id']} | {i.get('description', '')}" for i in batch]
        result = cast(
            _BatchVerdicts,
            chain.invoke(
                {
                    "today": today,
                    "title": ctx['title'] or '(untitled)',
                    "overview": ctx['overview'] or '(no summary)',
                    "age": age,
                    "tasks": "\n".join(task_lines),
                }
            ),
        )
        return [
            _candidate_from_item(id_to_item[v.id], 'conversation_context')
            for v in result.verdicts
            if v.is_stale and v.confidence >= confidence_threshold and v.id in id_to_item
        ]

    all_batches = [
        (cid, items[i : i + _BATCH_SIZE]) for cid, items in by_conv.items() for i in range(0, len(items), _BATCH_SIZE)
    ]

    def _score_batch_wrapper(args: tuple[str, list[dict]]) -> list[dict]:
        cid, batch = args
        return _score_conv_batch(batch, cid)

    candidates = _run_llm_batches(uid, all_batches, _score_batch_wrapper)
    logger.info(f'conversation_context uid={uid} conversations={len(by_conv)} candidates={len(candidates)}')
    return candidates, next_cursor


# ---------------------------------------------------------------------------
# Strategy: vagueness / context-loss detection
# ---------------------------------------------------------------------------

_PRONOUN_PATTERN = re.compile(
    r'\b(it|them|those|these|that|this|the other|the same|the two|the ones?|'
    r'the things?|the stuff|the other one|the rest)\b',
    re.IGNORECASE,
)

_DANGLING_PATTERN = re.compile(
    r'^(put|take|send|get|fix|check|do|move|bring|pick up|drop off|return|'
    r'give back|hand|pass|grab|swap|switch|change|clean|clear|sort|set)\s+'
    r'(it|them|those|these|that|this)\b',
    re.IGNORECASE,
)

_SPEAKER_PATTERN = re.compile(r'\bspeaker\s+\d+\b', re.IGNORECASE)


def _is_vague(description: str) -> bool:
    desc = description.strip()
    words = desc.split()

    if _SPEAKER_PATTERN.search(desc):
        return True

    if len(words) <= 5 and _PRONOUN_PATTERN.search(desc):
        return True

    if _DANGLING_PATTERN.match(desc):
        return True

    return False


def candidates_vague(uid: str, *, scan_cursor: Optional[str] = None) -> tuple[list[dict], Optional[str]]:
    """Find open tasks whose descriptions contain unresolved pronouns or references."""
    all_items, next_cursor = _open_items_for_cleanup(uid, scan_cursor)
    candidates = [_candidate_from_item(item, 'vague') for item in all_items if _is_vague(item.get('description', ''))]
    logger.info(f'vague uid={uid} checked={len(all_items)} candidates={len(candidates)}')
    return candidates, next_cursor


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
