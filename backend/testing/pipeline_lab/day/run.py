"""Run the day-level stages after the chain, inside the same lab environment.

Daily summary: the cron's per-user worker ``utils.other.notifications._send_summary_notification``
with the replayed instant as its ``at`` argument and the clock set to it, so
"today", the 24 h window and ``scheduled_date`` all resolve to the replayed day.
Its push goes to the FCM capture sink (which reports success: the worker raises
when zero devices are reached). The open-loops pass it requests is run inline.

Goals: read back after the chain (progress is written per conversation by
``utils.llm.goals``). Memory delta: start-state memories vs the portable export at
the end. Chat index: ns1 vectors (and Typesense docs when a checker is passed).

A public seam (``run_daily_summary_for(uid, at)``) would be cleaner than calling a
private worker; see the handoff.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from testing.pipeline_lab.day.outputs import build_day_json, chat_index_readiness, recap_instant, vector_id_checker
from testing.pipeline_lab.sinks.capture import CaptureSinks, capture_scope
from testing.pipeline_lab.stack.clock import LabClock
from testing.pipeline_lab.stack.io import iso, plain, write_json


def run_daily_summary(
    uid: str, day: str, tz_name: str | None, clock: LabClock | None, *, production_at: Any = None
) -> dict[str, Any]:
    from database import daily_summaries as daily_summaries_db
    from database import notifications as notification_db
    from utils.other import notifications as cron

    at, source = recap_instant(day, tz_name, production_at=production_at)
    if clock is not None:
        clock.set(at)
    tokens = notification_db.get_all_tokens(uid)
    recap: dict[str, Any] = {'at': iso(at), 'at_source': source, 'tokens': len(tokens)}
    with capture_scope(None, 'daily_summary'):
        try:
            pass_request = cron._send_summary_notification((uid, tokens, tz_name, at))
            recap['status'] = 'ok'
        except Exception as error:  # noqa: BLE001 - reported, not hidden
            pass_request = None
            recap['status'] = 'failed'
            recap['error'] = type(error).__name__
    if pass_request:
        with capture_scope(None, 'open_loops'):
            try:
                cron._run_open_loops_daily_pass(*pass_request)
                recap['open_loops'] = 'ok'
            except Exception as error:  # noqa: BLE001
                recap['open_loops'] = f'failed:{type(error).__name__}'
    rows = daily_summaries_db.get_daily_summaries(uid, limit=5, start_date=day, end_date=day)
    summary = next((row for row in rows or [] if row.get('date') == day), None)
    return {'recap': recap, 'daily_summary': plain(summary) if summary else None}


def read_goals(uid: str) -> list[dict[str, Any]]:
    from database import goals as goals_db

    return plain(goals_db.get_all_goals(uid, include_inactive=True) or [])


def read_memories(uid: str) -> list[dict[str, Any]]:
    from utils.memory.memory_service import MemoryService

    return plain(list(MemoryService().iter_portability_export_memories(uid, include_archive=True)))


def run_day(
    *,
    uid: str,
    day: str,
    tz_name: str | None,
    run_dir: Path,
    clock: LabClock | None,
    sinks: CaptureSinks,
    memories_before: Iterable[Mapping[str, Any]],
    kept_conversation_ids: Sequence[str],
    vector_index: Any,
    search_checker: Callable[[str], bool] | None = None,
    production_recap_at: Any = None,
    goals_before: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Must run inside the chain's lab environment, after the chain has drained."""
    summary = run_daily_summary(uid, day, tz_name, clock, production_at=production_recap_at)
    goals = read_goals(uid)
    memories_after = read_memories(uid)
    chat = chat_index_readiness(
        list(kept_conversation_ids), has_vector=vector_id_checker(vector_index, uid), has_search_doc=search_checker
    )
    payload = build_day_json(
        daily_summary=summary['daily_summary'],
        goals=goals,
        memories_before=memories_before,
        memories_after=memories_after,
        notifications=sinks.notifications,
        chat_index=chat,
        recap=summary['recap'],
        goals_before=goals_before,
    )
    write_json(Path(run_dir) / 'day.json', payload)
    return payload
