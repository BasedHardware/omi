"""
memory/session_memory.py

Two memory layers:
  1. Global memory  — user preferences (static, 1-2 lines)
  2. Session memory — last 5 raw messages + one aggressive rolling summary

Context passed to orchestrator per turn (target: under 1500 chars total):
  [User preferences: ...]      ← only if set
  [Summary: ...]               ← one compact line, only if exists
  user: ...                    ← last 5 messages max, 150 chars each
  assistant: ...
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)

# ── Knobs ─────────────────────────────────────────────────────────────────────
RECENT_MSG_COUNT    = 5      # raw messages kept verbatim every turn
SUMMARIZE_AFTER     = 10     # summarise when stored message count exceeds this
MAX_MSG_CHARS       = 150    # per-message character cap in context
MAX_CONTEXT_CHARS   = 1_500  # absolute hard cap on full context string
# ─────────────────────────────────────────────────────────────────────────────

_SUMMARY_PROMPT = (
    "Extract ONLY the essential facts from this conversation in 1-2 short sentences. "
    "Keep: names, decisions made, specific tasks requested, key facts stated. "
    "Drop: pleasantries, filler, anything that can be inferred. "
    "Output only the summary, no preamble."
)


def _sb():
    from auth.supabase_client import get_service_client
    return get_service_client()


def _llm():
    from langchain_groq import ChatGroq
    return ChatGroq(
        model=os.getenv("PLANNING_MODEL", "llama-3.3-70b-versatile"),
        temperature=0.0,
        api_key=os.getenv("GROQ_API_KEY"),
        timeout=15,
        max_retries=1,
    )


# ============================================================================
# GLOBAL MEMORY
# ============================================================================

async def get_global_memory(user_id: str) -> str:
    try:
        row = (
            _sb().table("user_memory")
            .select("preferences")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        return (row.data or {}).get("preferences", "")
    except Exception as exc:
        logger.warning(f"get_global_memory: {exc}")
        return ""


async def set_global_memory(user_id: str, preferences: str) -> bool:
    try:
        _sb().table("user_memory").upsert(
            {"user_id": user_id, "preferences": preferences[:500],
             "updated_at": datetime.now(timezone.utc).isoformat()},
            on_conflict="user_id",
        ).execute()
        return True
    except Exception as exc:
        logger.error(f"set_global_memory: {exc}")
        return False


# ============================================================================
# THREAD MANAGEMENT
# ============================================================================

async def create_thread(user_id: str) -> str:
    row = _sb().table("conversation_threads").insert({"user_id": user_id}).execute()
    return row.data[0]["id"]


async def get_thread(thread_id: str, user_id: str) -> Optional[dict]:
    try:
        row = (
            _sb().table("conversation_threads")
            .select("*")
            .eq("id", thread_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        return row.data
    except Exception as exc:
        logger.warning(f"get_thread: {exc}")
        return None


async def list_threads(user_id: str) -> List[dict]:
    try:
        rows = (
            _sb().table("conversation_threads")
            .select("id, created_at, updated_at, message_count, summary")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .limit(50)
            .execute()
        )
        return rows.data or []
    except Exception as exc:
        logger.warning(f"list_threads: {exc}")
        return []


async def delete_thread(thread_id: str, user_id: str) -> bool:
    try:
        _sb().table("conversation_threads").delete() \
            .eq("id", thread_id).eq("user_id", user_id).execute()
        return True
    except Exception as exc:
        logger.error(f"delete_thread: {exc}")
        return False


# ============================================================================
# MESSAGE STORAGE
# ============================================================================

async def add_message(thread_id: str, user_id: str, role: str, content: str) -> bool:
    """Store message, bump counter, trigger summarisation if needed."""
    try:
        sb = _sb()
        sb.table("conversation_messages").insert(
            {"thread_id": thread_id, "user_id": user_id,
             "role": role, "content": content}
        ).execute()
        sb.rpc("increment_message_count", {"p_thread_id": thread_id}).execute()

        thread = await get_thread(thread_id, user_id)
        if thread and thread.get("message_count", 0) > SUMMARIZE_AFTER:
            await _summarize_and_prune(thread_id, user_id, sb)

        return True
    except Exception as exc:
        logger.error(f"add_message({thread_id}): {exc}")
        return False


async def get_messages(thread_id: str, user_id: str) -> List[dict]:
    try:
        rows = (
            _sb().table("conversation_messages")
            .select("id, role, content, created_at")
            .eq("thread_id", thread_id)
            .eq("user_id", user_id)
            .order("created_at", desc=False)
            .execute()
        )
        return rows.data or []
    except Exception as exc:
        logger.warning(f"get_messages: {exc}")
        return []


# ============================================================================
# CONTEXT BUILDER  — called by chat.py before each orchestrator invocation
# ============================================================================

async def build_context(thread_id: str, user_id: str) -> str:
    """
    Returns a tiny context string:
      [User preferences: ...]     (if set)
      [Summary: ...]              (if exists — one compact line)
      user: ...                   (last 5 messages, 150 chars each)
      assistant: ...

    Target: well under 1500 chars. Orchestrator should barely notice it.
    """
    prefs  = await get_global_memory(user_id)
    thread = await get_thread(thread_id, user_id)

    parts: List[str] = []

    if prefs:
        parts.append(f"[User preferences: {prefs[:200]}]")

    summary = (thread or {}).get("summary", "")
    if summary:
        parts.append(f"[Summary: {summary}]")

    try:
        rows = (
            _sb().table("conversation_messages")
            .select("role, content")
            .eq("thread_id", thread_id)
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(RECENT_MSG_COUNT)
            .execute()
        )
        recent = list(reversed(rows.data or []))
    except Exception as exc:
        logger.warning(f"build_context fetch: {exc}")
        recent = []

    for msg in recent:
        text = msg["content"][:MAX_MSG_CHARS]
        parts.append(f"{msg['role']}: {text}")

    context = "\n".join(parts)

    # Absolute safety cap
    if len(context) > MAX_CONTEXT_CHARS:
        context = context[:MAX_CONTEXT_CHARS]

    return context


# ============================================================================
# AGGRESSIVE SUMMARISATION  (internal)
# ============================================================================

async def _summarize_and_prune(thread_id: str, user_id: str, sb) -> None:
    """
    Summarise every message except the newest RECENT_MSG_COUNT ones into
    a single 1-2 sentence string, delete those rows, store the summary.
    Merges with any existing summary so history compresses recursively.
    """
    try:
        all_rows = (
            sb.table("conversation_messages")
            .select("id, role, content, created_at")
            .eq("thread_id", thread_id)
            .eq("user_id", user_id)
            .order("created_at", desc=False)
            .execute()
        ).data or []

        if len(all_rows) <= RECENT_MSG_COUNT:
            return

        to_compress = all_rows[:-RECENT_MSG_COUNT]

        # Build compact transcript — already cap each message
        transcript_lines = [
            f"{r['role']}: {r['content'][:200]}" for r in to_compress
        ]
        transcript = "\n".join(transcript_lines)

        # Prepend existing summary into the transcript so it gets merged
        thread    = await get_thread(thread_id, user_id)
        existing  = (thread or {}).get("summary", "")
        if existing:
            transcript = f"Previous summary: {existing}\n\nNew messages:\n{transcript}"

        from langchain_core.messages import HumanMessage, SystemMessage
        resp = _llm().invoke([
            SystemMessage(content=_SUMMARY_PROMPT),
            HumanMessage(content=transcript[:2500]),
        ])
        new_summary = resp.content.strip()

        # Hard-cap the stored summary to 300 chars — it's a hint, not a transcript
        new_summary = new_summary[:300]

        old_ids = [r["id"] for r in to_compress]

        sb.table("conversation_threads").update(
            {"summary": new_summary}
        ).eq("id", thread_id).execute()

        sb.table("conversation_messages").delete().in_("id", old_ids).execute()

        sb.table("conversation_threads").update(
            {"message_count": len(all_rows) - len(old_ids)}
        ).eq("id", thread_id).execute()

        logger.info(
            f"Pruned {len(old_ids)} msgs for thread {thread_id}. "
            f"Summary: '{new_summary[:80]}...'"
        )
    except Exception as exc:
        logger.error(f"_summarize_and_prune({thread_id}): {exc}")