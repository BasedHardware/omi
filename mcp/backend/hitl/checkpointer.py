"""
hitl/checkpointer.py
--------------------
MemorySaver by default (works synchronously, no context manager needed).
Set HITL_USE_SQLITE=true in .env to persist state across server restarts.
"""
from __future__ import annotations
import os
import logging

logger = logging.getLogger(__name__)


def get_checkpointer():
    use_sqlite = os.getenv("HITL_USE_SQLITE", "false").strip().lower() == "true"

    if use_sqlite:
        db_path = os.getenv("HITL_SQLITE_PATH", "./hitl_checkpoints.db")
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
            import sqlite3
            conn = sqlite3.connect(db_path, check_same_thread=False)
            cp = SqliteSaver(conn)
            logger.info(f"HITL checkpointer: SqliteSaver ({db_path})")
            return cp
        except Exception as exc:
            logger.warning(f"SqliteSaver failed ({exc}), falling back to MemorySaver")

    from langgraph.checkpoint.memory import MemorySaver
    cp = MemorySaver()
    logger.info("HITL checkpointer: MemorySaver (in-memory)")
    return cp


def make_thread_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}